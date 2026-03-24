"""MT5 Web API 连接管理器 v5

核心设计（符合 MT5 文档规范）：
  MT5 是有状态服务，会话绑定在 TCP 连接上。
  
  关键要求（来自官方文档）：
  1. 所有请求带 Connection: keep-alive 头
  2. 使用单一持久 TCP 连接（maxSockets=1）
  3. 认证一次后保持连接，断连才重新认证
  4. 每 20 秒发 ping (/api/test/access) 维持连接
  5. 180 秒无数据服务器主动断开
"""
import asyncio
import logging
import time

import httpx

from app.config import get_settings
from app.mt5.auth import (
    compute_srv_rand_answer,
    generate_cli_rand,
    verify_cli_rand_answer,
)

logger = logging.getLogger(__name__)

PING_INTERVAL = 20  # 秒，MT5 文档推荐值


class MT5ConnectionError(Exception):
    """MT5 连接或认证失败"""
    pass


class MT5APIError(Exception):
    """MT5 API 返回非 0 retcode"""

    def __init__(self, retcode: str, message: str = ""):
        self.retcode = retcode
        self.message = message
        super().__init__(f"MT5 API error: retcode={retcode} {message}")


class MT5Connector:
    """MT5 Web API 连接管理器（单例）"""

    def __init__(self):
        self._client: httpx.AsyncClient | None = None
        self._connected: bool = False
        self._lock: asyncio.Lock = asyncio.Lock()
        self._ping_task: asyncio.Task | None = None
        self._settings = get_settings()
        self.server_time_offset_sec: int = 0  # MT5服务器时间与 UTC 的偏移(秒)

    @property
    def is_connected(self) -> bool:
        return self._connected

    @property
    def base_url(self) -> str:
        host = self._settings.MT5_SERVER_HOST
        port = self._settings.MT5_SERVER_PORT
        return f"https://{host}:{port}"

    def _create_client(self) -> httpx.AsyncClient:
        """创建 httpx 客户端 — 单连接 keep-alive"""
        return httpx.AsyncClient(
            base_url=self.base_url,
            # 单连接，keep-alive 复用
            limits=httpx.Limits(
                max_connections=1,
                max_keepalive_connections=1,
                keepalive_expiry=300,  # 5 分钟 keep-alive 超时
            ),
            headers={
                "Connection": "keep-alive",
                "User-Agent": "AstralW Gateway/1.0",
            },
            verify=self._settings.MT5_USE_SSL_VERIFY,
            timeout=httpx.Timeout(30.0, connect=10.0),
            proxy=None,
            trust_env=False,
        )

    # ──────────────────── 生命周期 ────────────────────

    async def connect(self) -> None:
        """连接并认证 MT5 服务器，启动 ping 心跳"""
        settings = self._settings
        logger.info(
            "正在连接 MT5 服务器 %s:%s (login=%s)...",
            settings.MT5_SERVER_HOST,
            settings.MT5_SERVER_PORT,
            settings.MT5_MANAGER_LOGIN,
        )
        self._client = self._create_client()
        await self._authenticate()
        await self._detect_server_time_offset()
        self._start_ping()
        logger.info("✅ MT5 已连接（keep-alive 单连接，%ds ping，server_offset=%ds）", PING_INTERVAL, self.server_time_offset_sec)

    async def disconnect(self) -> None:
        """关闭连接"""
        self._connected = False
        self._stop_ping()
        if self._client:
            try:
                await self._client.aclose()
            except Exception:
                pass
            self._client = None
        logger.info("MT5 连接已关闭")

    async def _reconnect(self) -> None:
        """断连后重建连接并重新认证"""
        logger.warning("MT5 连接断开，正在重连...")
        self._connected = False
        self._stop_ping()
        if self._client:
            try:
                await self._client.aclose()
            except Exception:
                pass
        self._client = self._create_client()
        await self._authenticate()
        self._start_ping()
        logger.info("✅ MT5 重连成功")

    # ──────────────────── 认证 ────────────────────

    async def _authenticate(self) -> None:
        """执行 auth/start + auth/answer 双向认证"""
        settings = self._settings
        password = settings.MT5_WEBAPI_PASSWORD or settings.MT5_MANAGER_PASSWORD

        if not self._client:
            raise MT5ConnectionError("httpx 客户端未初始化")

        # --- auth/start ---
        start_resp = await self._client.get("/api/auth/start", params={
            "version": "3470",
            "agent": "AstralWGateway",
            "login": str(settings.MT5_MANAGER_LOGIN),
            "type": "manager",
        })
        start_resp.raise_for_status()
        start_data = start_resp.json()

        retcode = start_data.get("retcode", "")
        if not str(retcode).startswith("0"):
            raise MT5ConnectionError(f"auth/start 失败: retcode={retcode}")

        srv_rand = start_data["srv_rand"]

        # --- 计算应答 ---
        srv_rand_answer = compute_srv_rand_answer(password, srv_rand)
        cli_rand_bytes, cli_rand_hex = generate_cli_rand()

        # --- auth/answer ---
        answer_resp = await self._client.get("/api/auth/answer", params={
            "srv_rand_answer": srv_rand_answer,
            "cli_rand": cli_rand_hex,
        })
        answer_resp.raise_for_status()
        answer_data = answer_resp.json()

        retcode = answer_data.get("retcode", "")
        if not str(retcode).startswith("0"):
            raise MT5ConnectionError(f"auth/answer 失败: retcode={retcode}")

        # --- 验证服务器身份 ---
        cli_rand_answer = answer_data.get("cli_rand_answer", "")
        if not verify_cli_rand_answer(password, cli_rand_bytes, cli_rand_answer):
            raise MT5ConnectionError("服务器身份验证失败")

        self._connected = True
        logger.debug("认证完成 (版本: %s)", answer_data.get("version_trade", "?"))

    async def _detect_server_time_offset(self) -> None:
        """检测 MT5 服务器时间与 UTC 的偏移量"""
        try:
            resp = await self._client.get("/api/common/get")
            data = resp.json()
            server_time = int(data.get("answer", {}).get("TradeServerTimeMSec", 0)) // 1000
            if server_time == 0:
                server_time = int(data.get("answer", {}).get("Time", 0))
            if server_time > 0:
                utc_now = int(time.time())
                self.server_time_offset_sec = server_time - utc_now
                logger.info(
                    "MT5 服务器时间偏移检测: server_time=%d, utc=%d, offset=%+d秒 (%+.1f小时)",
                    server_time, utc_now, self.server_time_offset_sec,
                    self.server_time_offset_sec / 3600,
                )
            else:
                logger.warning("MT5 服务器时间获取失败，使用默认 offset=0")
        except Exception as e:
            logger.warning("检测服务器时间偏移失败: %s", e)

    # ──────────────────── Ping 心跳 ────────────────────

    def _start_ping(self) -> None:
        """启动 20 秒 ping 心跳"""
        self._stop_ping()
        self._ping_task = asyncio.create_task(self._ping_loop())

    def _stop_ping(self) -> None:
        """停止 ping 心跳"""
        if self._ping_task and not self._ping_task.done():
            self._ping_task.cancel()
            self._ping_task = None

    async def _ping_loop(self) -> None:
        """ping 循环：每 20 秒发一次 /api/test/access"""
        while True:
            try:
                await asyncio.sleep(PING_INTERVAL)
                if self._client and self._connected:
                    async with self._lock:
                        resp = await self._client.get("/api/test/access")
                        if resp.status_code == 200:
                            logger.debug("ping OK")
                        else:
                            logger.warning("ping 返回 %d，尝试重连...", resp.status_code)
                            await self._reconnect()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.warning("ping 失败 (%s)，尝试重连...", e)
                try:
                    async with self._lock:
                        await self._reconnect()
                except Exception as re:
                    logger.error("重连失败: %s，%ds 后重试", re, PING_INTERVAL)

    # ──────────────────── 请求方法 ────────────────────

    async def get(self, path: str, params: dict | None = None) -> dict:
        """发送 GET 请求（同一 keep-alive 连接）"""
        async with self._lock:
            return await self._request_with_retry("GET", path, params=params)

    async def post(self, path: str, body: dict | None = None, params: dict | None = None) -> dict:
        """发送 POST 请求（同一 keep-alive 连接）"""
        async with self._lock:
            return await self._request_with_retry("POST", path, body=body, params=params)

    async def _request_with_retry(
        self,
        method: str,
        path: str,
        body: dict | None = None,
        params: dict | None = None,
    ) -> dict:
        """发送请求，失败时重连后重试一次"""
        try:
            data = await self._do_request(method, path, body=body, params=params)
            self._check_retcode(data)
            return data
        except Exception as first_err:
            logger.warning("%s %s 失败 (%s)，重连重试...", method, path, first_err)

        # 重连后重试
        try:
            await self._reconnect()
            data = await self._do_request(method, path, body=body, params=params)
            self._check_retcode(data)
            return data
        except Exception as e:
            logger.error("%s %s 重试后仍失败: %s", method, path, e)
            raise MT5ConnectionError(f"请求 {path} 失败: {e}") from e

    async def _do_request(
        self,
        method: str,
        path: str,
        body: dict | None = None,
        params: dict | None = None,
    ) -> dict:
        """执行单次 HTTP 请求"""
        if not self._client:
            raise MT5ConnectionError("未连接")

        if method == "GET":
            resp = await self._client.get(path, params=params)
        else:
            resp = await self._client.post(path, params=params, json=body)

        resp.raise_for_status()
        return resp.json()

    async def raw_get(self, path: str, params: dict | None = None) -> dict:
        """发送 GET 请求（不加锁、不重试、不检查 retcode）。用于交易结果轮询。"""
        if not self._client:
            raise MT5ConnectionError("未连接")
        resp = await self._client.get(path, params=params)
        resp.raise_for_status()
        return resp.json()

    # ──────────────────── 内部方法 ────────────────────

    @staticmethod
    def _check_retcode(data: dict) -> None:
        """检查 MT5 响应的 retcode"""
        retcode = data.get("retcode", "")
        if isinstance(retcode, str) and retcode.startswith("0"):
            return
        raise MT5APIError(retcode=str(retcode))


# ──────────────────── 全局单例 ────────────────────

_connector: MT5Connector | None = None


def get_mt5() -> MT5Connector:
    """获取全局 MT5 连接器实例"""
    global _connector
    if _connector is None:
        _connector = MT5Connector()
    return _connector
