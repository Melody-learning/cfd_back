"""账户与持仓路由。"""
import logging

from fastapi import APIRouter, Depends, Query

from app.models.user import User
from app.mt5.connector import get_mt5
from app.services.jwt_service import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["账户"])


def _deal_action_to_direction(action: int) -> str:
    """Map MT5 deal action to frontend-friendly direction."""
    if action == 0:
        return "BUY"
    if action == 1:
        return "SELL"
    return ""


def _map_history_deal(item: dict) -> dict:
    """Normalize MT5 deal history payload for frontend use."""
    action = int(item.get("Action", 0) or 0)
    return {
        "deal": int(item.get("Deal", 0) or 0),
        "order": int(item.get("Order", 0) or 0),
        "symbol": item.get("Symbol", ""),
        "type": action,
        "direction": _deal_action_to_direction(action),
        # Keep MT5 internal volume format for consistency with existing trade APIs.
        "volume": str(item.get("Volume", "0")),
        "price": str(item.get("Price", "0")),
        "profit": str(item.get("Profit", "0")),
        "commission": str(item.get("Commission", "0")),
        "swap": str(item.get("Storage", item.get("Swap", "0"))),
        "time": int(item.get("Time", 0) or 0),
        "comment": item.get("Comment", ""),
    }


@router.get("/account/info")
async def get_account_info(
    user: User = Depends(get_current_user),
):
    """获取账户信息。"""
    mt5 = get_mt5()
    data = await mt5.get(
        "/api/user/account/get",
        params={"login": str(user.mt5_login)},
    )
    acc = data.get("answer", {})
    return {
        "login": user.mt5_login,
        "group": acc.get("Group", ""),
        "balance": str(acc.get("Balance", "0")),
        "credit": str(acc.get("Credit", "0")),
        "equity": str(acc.get("Equity", "0")),
        "margin": str(acc.get("Margin", "0")),
        "free_margin": str(acc.get("MarginFree", "0")),
        "margin_level": str(acc.get("MarginLevel", "0")),
        "leverage": int(acc.get("Leverage", 0)),
        "currency": acc.get("Currency", "USD"),
    }


@router.get("/positions")
async def get_positions(
    user: User = Depends(get_current_user),
):
    """获取当前持仓列表。"""
    mt5 = get_mt5()
    data = await mt5.get(
        "/api/position/get_batch",
        params={"login": str(user.mt5_login)},
    )
    answer = data.get("answer", [])
    positions = []
    offset = mt5.server_time_offset_sec  # MT5 服务器时间偏移
    if isinstance(answer, list):
        for pos in answer:
            action = int(pos.get("Action", 0))
            raw_time = int(pos.get("TimeCreate", 0))
            # 修正 MT5 服务器时间为 UTC 时间戳
            utc_time = raw_time - offset if raw_time > 0 else 0
            positions.append({
                "position": int(pos.get("Position", 0)),
                "symbol": pos.get("Symbol", ""),
                "direction": "BUY" if action == 0 else "SELL",
                "lots": str(int(pos.get("Volume", 0)) / 10000),
                "price_open": str(pos.get("PriceOpen", "0")),
                "price_current": str(pos.get("PriceCurrent", "0")),
                "profit": str(pos.get("Profit", "0")),
                "stop_loss": str(pos.get("PriceSL", "0")),
                "take_profit": str(pos.get("PriceTP", "0")),
                "time_create": utc_time,
            })
    return {"positions": positions}


@router.get("/orders")
async def get_orders(
    user: User = Depends(get_current_user),
):
    """获取当前挂单列表。"""
    mt5 = get_mt5()
    data = await mt5.get(
        "/api/order/get_batch",
        params={"login": str(user.mt5_login)},
    )
    answer = data.get("answer", [])
    orders = []
    if isinstance(answer, list):
        for order in answer:
            orders.append({
                "order": int(order.get("Order", 0)),
                "symbol": order.get("Symbol", ""),
                "type": int(order.get("Type", 0)),
                "lots": str(int(order.get("VolumeInitial", 0)) / 10000),
                "price_order": str(order.get("PriceOrder", "0")),
                "stop_loss": str(order.get("PriceSL", "0")),
                "take_profit": str(order.get("PriceTP", "0")),
                "time_setup": int(order.get("TimeSetup", 0)),
                "state": int(order.get("State", 0)),
            })
    return {"orders": orders}


@router.get("/history/deals")
async def get_history_deals(
    from_ts: int = Query(alias="from", description="起始时间 Unix 秒"),
    to_ts: int = Query(alias="to", description="结束时间 Unix 秒"),
    user: User = Depends(get_current_user),
):
    """获取历史成交。"""
    mt5 = get_mt5()
    data = await mt5.get(
        "/api/history/get",
        params={
            "login": str(user.mt5_login),
            "from": str(from_ts),
            "to": str(to_ts),
            "type": "deal",
        },
    )
    answer = data.get("answer", [])
    deals = []
    if isinstance(answer, list):
        deals = [_map_history_deal(item) for item in answer]
    elif isinstance(answer, dict):
        deals = [_map_history_deal(answer)]
    return {"deals": deals}


@router.get("/history/orders")
async def get_history_orders(
    from_ts: int = Query(alias="from", description="起始时间 Unix 秒"),
    to_ts: int = Query(alias="to", description="结束时间 Unix 秒"),
    user: User = Depends(get_current_user),
):
    """获取历史订单。"""
    mt5 = get_mt5()
    data = await mt5.get(
        "/api/history/get",
        params={
            "login": str(user.mt5_login),
            "from": str(from_ts),
            "to": str(to_ts),
            "type": "order",
        },
    )
    return {"orders": data.get("answer", [])}
