"""账户与持仓路由。"""
import logging

from fastapi import APIRouter, Depends, HTTPException, Path, Query

from app.models.user import User
from app.mt5.connector import MT5APIError, MT5ConnectionError, get_mt5
from app.schemas.trade import TradeResult
from app.services.jwt_service import get_current_user

logger = logging.getLogger(__name__)

# MT5 订单 Type 值到前端字符串的反向映射
ORDER_TYPE_REVERSE_MAP = {
    2: "BUY_LIMIT",
    3: "SELL_LIMIT",
    4: "BUY_STOP",
    5: "SELL_STOP",
}

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
        # 收集所有品种，批量获取当前价格
        symbols = {order.get("Symbol", "") for order in answer if order.get("Symbol")}
        current_prices: dict[str, str] = {}
        if symbols:
            try:
                tick_data = await mt5.get(
                    "/api/tick/last",
                    params={"symbol": ",".join(symbols)},
                )
                for tick in tick_data.get("answer", []):
                    sym = tick.get("Symbol", "")
                    # 使用 Bid 作为当前市场参考价
                    current_prices[sym] = str(tick.get("Bid", "0"))
            except Exception:
                logger.warning("获取当前价格失败，price_current 将返回 0")

        for order in answer:
            raw_type = int(order.get("Type", 0))
            symbol = order.get("Symbol", "")
            orders.append({
                "ticket": int(order.get("Order", 0)),
                "symbol": symbol,
                "type": ORDER_TYPE_REVERSE_MAP.get(raw_type, str(raw_type)),
                "volume": str(order.get("VolumeInitial", "0")),
                "price_open": str(order.get("PriceOrder", "0")),
                "stop_loss": str(order.get("PriceSL", "0")),
                "take_profit": str(order.get("PriceTP", "0")),
                "price_current": current_prices.get(symbol, "0"),
                "time_setup": int(order.get("TimeSetup", 0)),
                "expiration": int(order.get("Expiration", 0) or 0),
                "comment": order.get("Comment", ""),
            })
    return {"orders": orders}


@router.delete("/orders/{ticket}", response_model=TradeResult)
async def cancel_order(
    ticket: int = Path(description="MT5 订单 ticket"),
    user: User = Depends(get_current_user),
):
    """取消挂单。"""
    from app.routers.trade import _poll_trade_result, _safe_int

    mt5 = get_mt5()

    trade_body = {
        "Action": "201",
        "Login": str(user.mt5_login),
        "Order": str(ticket),
    }

    try:
        resp = await mt5.post("/api/dealer/send_request", body=trade_body)
        answer = resp.get("answer", {})
        request_id = str(answer.get("id", answer.get("ID", "")))
        if not request_id:
            raise HTTPException(
                status_code=502,
                detail={"error": {"code": "TRADE_SUBMIT_FAILED", "message": "未获取到请求 ID"}},
            )

        result = await _poll_trade_result(mt5, request_id)
        if result:
            return TradeResult(
                order=_safe_int(result.get("OrderID", result.get("ResultOrder", 0))),
                deal=_safe_int(result.get("DealID", result.get("ResultDeal", 0))),
                price=str(result.get("Price", result.get("ResultPrice", "0"))),
                volume=str(result.get("Volume", result.get("ResultVolume", ""))),
                retcode=str(result.get("Retcode", result.get("ResultRetcode", "0"))),
                message="挂单已取消",
            )

        return TradeResult(
            order=ticket,
            deal=0,
            price="0",
            volume="",
            retcode="0",
            message=f"取消请求已提交，等待执行 (request_id={request_id})",
        )
    except MT5ConnectionError:
        raise HTTPException(status_code=503, detail={"error": {"code": "MT5_UNAVAILABLE", "message": "MT5 服务不可用"}})
    except MT5APIError as e:
        raise HTTPException(
            status_code=502,
            detail={"error": {"code": "TRADE_FAILED", "message": str(e), "mt5_retcode": e.retcode}},
        )


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
