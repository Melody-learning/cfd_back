"""K 线历史路由"""
import logging

from fastapi import APIRouter, Depends, Query

from app.models.user import User
from app.mt5.connector import get_mt5
from app.services.jwt_service import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/chart", tags=["K线"])

# MT5 timeframe 映射（分钟数）
TIMEFRAME_MINUTES = {
    "M1": 1,
    "M5": 5,
    "M15": 15,
    "M30": 30,
    "H1": 60,
    "H4": 240,
    "D1": 1440,
}


def _aggregate_candles(m1_candles: list, target_minutes: int) -> list:
    """
    将 M1 蜡烛聚合为更高时间周期。

    Args:
        m1_candles: M1 蜡烛列表，每个元素为 [timestamp, open, high, low, close, tick_vol, volume]
        target_minutes: 目标时间周期的分钟数

    Returns:
        聚合后的蜡烛列表
    """
    if target_minutes <= 1:
        return m1_candles

    target_seconds = target_minutes * 60
    aggregated = []
    current_group: list = []
    current_period_start: int | None = None

    for bar in m1_candles:
        ts = bar[0]
        period_start = (ts // target_seconds) * target_seconds

        if current_period_start is None:
            current_period_start = period_start

        if period_start != current_period_start:
            # 输出当前聚合的蜡烛
            if current_group:
                aggregated.append(_merge_group(current_period_start, current_group))
            current_group = [bar]
            current_period_start = period_start
        else:
            current_group.append(bar)

    # 最后一组
    if current_group and current_period_start is not None:
        aggregated.append(_merge_group(current_period_start, current_group))

    return aggregated


def _merge_group(period_start: int, bars: list) -> dict:
    """合并一组 M1 蜡烛为一根"""
    o = bars[0][1]  # 第一根的 open
    h = max(b[2] for b in bars)
    l_ = min(b[3] for b in bars)
    c = bars[-1][4]  # 最后一根的 close
    # 成交量求和（如果有第 5 和第 6 列）
    vol = sum(b[5] if len(b) > 5 else 0 for b in bars)
    return {
        "timestamp": period_start,
        "open": str(o),
        "high": str(h),
        "low": str(l_),
        "close": str(c),
        "volume": str(vol),
    }


@router.get("/candles")
async def get_candles(
    symbol: str = Query(description="品种名称"),
    timeframe: str = Query(default="M1", description="时间周期: M1/M5/M15/M30/H1/H4/D1"),
    from_ts: int | None = Query(default=None, alias="from", description="起始时间 Unix 秒"),
    to_ts: int | None = Query(default=None, alias="to", description="结束时间 Unix 秒"),
    count: int = Query(default=100, description="返回蜡烛数量（当不指定 from/to 时使用）"),
    user: User = Depends(get_current_user),
):
    """获取 K 线数据（支持 M1~D1 聚合）"""
    import time as _time

    mt5 = get_mt5()

    target_minutes = TIMEFRAME_MINUTES.get(timeframe.upper(), 1)

    # 如果未指定 from/to，根据 count 自动计算
    now = int(_time.time())
    if to_ts is None:
        to_ts = now
    if from_ts is None:
        # 多取 20% 的 M1 数据，确保聚合后有足够的蜡烛
        needed_minutes = count * target_minutes
        from_ts = to_ts - (needed_minutes + needed_minutes // 5 + 60) * 60

    # 向 MT5 请求 M1 原始数据
    all_bars = []
    current_from = from_ts

    while True:
        data = await mt5.get(
            "/api/chart/get",
            params={
                "symbol": symbol,
                "from": str(current_from),
                "to": str(to_ts),
                "data": "dohlctv",
            },
        )

        answer = data.get("answer", [])
        if not answer:
            break

        all_bars.extend(answer)

        # 检查是否需要分页（retcode 14 = 数据未完整）
        retcode = data.get("retcode", "")
        if isinstance(retcode, str) and retcode.startswith("14"):
            # 用最后一条的时间戳继续拉取
            last_ts = answer[-1][0] if answer else to_ts
            current_from = last_ts
            continue
        break

    # 聚合
    if target_minutes > 1:
        candles = _aggregate_candles(all_bars, target_minutes)
    else:
        # M1 直接转格式
        candles = []
        for bar in all_bars:
            candles.append({
                "timestamp": bar[0],
                "open": str(bar[1]),
                "high": str(bar[2]),
                "low": str(bar[3]),
                "close": str(bar[4]),
                "volume": str(bar[5] if len(bar) > 5 else 0),
            })

    return {"symbol": symbol, "timeframe": timeframe.upper(), "candles": candles}
