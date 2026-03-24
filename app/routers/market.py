"""行情路由: 品种列表 / 实时报价 / 统计 / WebSocket 推送"""
import asyncio
import json
import logging

from fastapi import APIRouter, Depends, Query, WebSocket, WebSocketDisconnect

from app.models.user import User
from app.mt5.connector import get_mt5
from app.services.jwt_service import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/market", tags=["行情"])


@router.get("/symbols")
async def get_symbols(
    user: User = Depends(get_current_user),
):
    """获取可用品种列表"""
    mt5 = get_mt5()
    data = await mt5.get("/api/symbol/list")
    # MT5 返回 {"retcode":"0 Done","answer":"EURUSD|GBPUSD|..."}
    answer = data.get("answer", "")
    symbols = []
    if isinstance(answer, str):
        for name in answer.split("|"):
            name = name.strip()
            if name:
                symbols.append({"symbol": name})
    elif isinstance(answer, list):
        symbols = [{"symbol": s} for s in answer if s]
    return {"symbols": symbols}


@router.get("/quotes")
async def get_quotes(
    symbols: str = Query(description="逗号分隔的品种列表，如 EURUSD,GBPUSD"),
    user: User = Depends(get_current_user),
):
    """获取指定品种的当前报价"""
    mt5 = get_mt5()
    data = await mt5.get("/api/tick/last", params={"symbol": symbols})
    answer = data.get("answer", [])
    quotes = []
    if isinstance(answer, list):
        for tick in answer:
            quotes.append({
                "symbol": tick.get("Symbol", ""),
                "bid": str(tick.get("Bid", "0")),
                "ask": str(tick.get("Ask", "0")),
                "last": str(tick.get("Last", "0")),
                "volume": str(tick.get("Volume", "0")),
                "datetime": int(tick.get("Datetime", 0)),
            })
    return {"quotes": quotes}


@router.get("/tick_stat")
async def get_tick_stat(
    symbols: str = Query(description="逗号分隔的品种列表"),
    user: User = Depends(get_current_user),
):
    """获取品种统计数据（日最高/最低价等）"""
    mt5 = get_mt5()
    data = await mt5.get("/api/tick/stat", params={"symbol": symbols})
    answer = data.get("answer", [])
    stats = []
    if isinstance(answer, list):
        for s in answer:
            stats.append({
                "symbol": s.get("Symbol", ""),
                "bid": str(s.get("Bid", "0")),
                "ask": str(s.get("Ask", "0")),
                "last": str(s.get("Last", "0")),
                "high": str(s.get("BidHigh", s.get("LastHigh", "0"))),
                "low": str(s.get("BidLow", s.get("LastLow", "0"))),
                "volume": str(s.get("Volume", "0")),
                "price_change": str(s.get("PriceChange", "0")),
                "datetime": int(s.get("Datetime", 0)),
            })
    return {"stats": stats}


# ──────────────────── WebSocket 行情推送 ────────────────────


class ConnectionManager:
    """WebSocket 连接管理器"""

    def __init__(self):
        self.active_connections: dict[WebSocket, set[str]] = {}  # ws → 订阅的品种

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections[websocket] = set()

    def disconnect(self, websocket: WebSocket):
        self.active_connections.pop(websocket, None)

    def subscribe(self, websocket: WebSocket, symbols: list[str]):
        if websocket in self.active_connections:
            self.active_connections[websocket].update(symbols)

    def unsubscribe(self, websocket: WebSocket, symbols: list[str]):
        if websocket in self.active_connections:
            self.active_connections[websocket] -= set(symbols)

    def get_all_subscribed_symbols(self) -> set[str]:
        """获取所有客户端订阅的品种（去重）"""
        all_symbols: set[str] = set()
        for symbols in self.active_connections.values():
            all_symbols.update(symbols)
        return all_symbols

    async def broadcast_quote(self, symbol: str, quote_data: dict):
        """向所有订阅了该品种的客户端推送"""
        disconnected = []
        for ws, symbols in self.active_connections.items():
            if symbol in symbols:
                try:
                    await ws.send_json({"type": "quote", "data": quote_data})
                except Exception:
                    disconnected.append(ws)
        for ws in disconnected:
            self.disconnect(ws)


ws_manager = ConnectionManager()
_poll_task: asyncio.Task | None = None


async def _poll_and_broadcast():
    """后台轮询 MT5 报价并广播给 WebSocket 客户端"""
    mt5 = get_mt5()
    last_quotes: dict[str, dict] = {}  # 差值推送缓存

    while True:
        try:
            await asyncio.sleep(0.5)  # 500ms 轮询间隔

            symbols = ws_manager.get_all_subscribed_symbols()
            if not symbols or not mt5.is_connected:
                continue

            symbol_str = ",".join(symbols)
            data = await mt5.get("/api/tick/last", params={"symbol": symbol_str})
            answer = data.get("answer", [])

            if isinstance(answer, list):
                for tick in answer:
                    sym = tick.get("Symbol", "")
                    quote = {
                        "symbol": sym,
                        "bid": str(tick.get("Bid", "0")),
                        "ask": str(tick.get("Ask", "0")),
                        "last": str(tick.get("Last", "0")),
                        "volume": str(tick.get("Volume", "0")),
                        "datetime": int(tick.get("Datetime", 0)),
                    }
                    # 差值推送：价格无变化则跳过
                    prev = last_quotes.get(sym)
                    if prev and prev["bid"] == quote["bid"] and prev["ask"] == quote["ask"]:
                        continue
                    last_quotes[sym] = quote
                    await ws_manager.broadcast_quote(sym, quote)

        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error("行情轮询异常: %s", e)
            await asyncio.sleep(2)


def _ensure_poll_task():
    """确保轮询任务在运行"""
    global _poll_task
    if _poll_task is None or _poll_task.done():
        _poll_task = asyncio.create_task(_poll_and_broadcast())


@router.websocket("/stream")
async def websocket_market_stream(websocket: WebSocket):
    """
    WebSocket 行情推送端点。

    客户端发送:
        {"action": "subscribe", "symbols": ["EURUSD", "GBPUSD"]}
        {"action": "unsubscribe", "symbols": ["GBPUSD"]}

    服务端推送:
        {"type": "quote", "data": {"symbol": "EURUSD", "bid": "1.08550", ...}}
    """
    await ws_manager.connect(websocket)
    _ensure_poll_task()

    try:
        while True:
            raw = await websocket.receive_text()
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                await websocket.send_json({"type": "error", "message": "Invalid JSON"})
                continue

            action = msg.get("action")
            symbols = msg.get("symbols", [])

            if action == "subscribe":
                ws_manager.subscribe(websocket, symbols)
                await websocket.send_json({
                    "type": "subscribed",
                    "symbols": list(ws_manager.active_connections.get(websocket, set())),
                })
            elif action == "unsubscribe":
                ws_manager.unsubscribe(websocket, symbols)
                await websocket.send_json({
                    "type": "unsubscribed",
                    "symbols": symbols,
                })
            else:
                await websocket.send_json({"type": "error", "message": f"Unknown action: {action}"})
    except WebSocketDisconnect:
        ws_manager.disconnect(websocket)
