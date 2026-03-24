"""Trade routes: open, close, modify, margin check, profit calculation."""
import asyncio
import logging

from fastapi import APIRouter, Depends, HTTPException

from app.models.user import User
from app.mt5.connector import MT5APIError, MT5ConnectionError, get_mt5
from app.schemas.trade import (
    MarginCheckResponse,
    ProfitCalcResponse,
    TradeCloseRequest,
    TradeModifyRequest,
    TradeOpenRequest,
    TradeResult,
)
from app.services.jwt_service import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/trade", tags=["交易"])

DIRECTION_MAP = {"BUY": 0, "SELL": 1}


def _lots_to_volume(lots: str) -> int:
    """Convert lots to MT5 Volume, where 100 = 0.01 lot."""
    return int(float(lots) * 10000)


def _lots_to_volume_ext(lots: str) -> int:
    """Convert lots to MT5 VolumeExt."""
    return int(float(lots) * 100000000)


def _safe_int(val) -> int:
    if not val or val == "":
        return 0
    try:
        return int(float(str(val)))
    except (ValueError, TypeError):
        return 0


def _count_price_digits(price: str) -> int:
    if "." not in price:
        return 0
    return len(price.split(".", 1)[1])


async def _get_market_execution_price(mt5, symbol: str, direction: str) -> tuple[str, int]:
    """Fetch the current executable price for a market order."""
    data = await mt5.get("/api/tick/last", params={"symbol": symbol})
    answer = data.get("answer", [])
    if not isinstance(answer, list) or not answer:
        raise HTTPException(
            status_code=502,
            detail={"error": {"code": "QUOTE_UNAVAILABLE", "message": f"无法获取 {symbol} 最新报价"}},
        )

    tick = answer[0]
    price = str(tick.get("Ask", "0")) if direction == "BUY" else str(tick.get("Bid", "0"))
    if not price or price == "0":
        raise HTTPException(
            status_code=502,
            detail={"error": {"code": "QUOTE_UNAVAILABLE", "message": f"{symbol} 报价无效，无法下单"}},
        )

    return price, _count_price_digits(price)


async def _poll_trade_result(mt5, request_id: str, timeout: float = 5.0) -> dict | None:
    """Poll MT5 dealer request result until completion or timeout."""
    elapsed = 0.0
    interval = 0.3

    while elapsed < timeout:
        await asyncio.sleep(interval)
        elapsed += interval

        try:
            data = await mt5.raw_get(
                "/api/dealer/get_request_result",
                params={"id": request_id},
            )
        except Exception as e:
            logger.debug("Polling trade result failed for %s (%s), continuing", request_id, e)
            continue

        retcode = data.get("retcode", "")
        if not str(retcode).startswith("0"):
            continue

        result_arr = data.get(request_id, []) or data.get("answer", {}).get(request_id, [])
        if not result_arr:
            continue

        for item in result_arr:
            if "result" not in item:
                continue
            res = item["result"]
            rc = str(res.get("Retcode", ""))
            if rc in {"10009", "10008"}:
                logger.info(
                    "Trade %s completed: Retcode=%s Price=%s Volume=%s DealID=%s",
                    request_id,
                    rc,
                    res.get("Price"),
                    res.get("Volume"),
                    res.get("DealID"),
                )
                return res
            if rc == "10006":
                break
            raise MT5APIError(retcode=rc, message=f"交易执行失败: Retcode={rc}")

    return None


@router.post("/open", response_model=TradeResult)
async def trade_open(
    req: TradeOpenRequest,
    user: User = Depends(get_current_user),
):
    """Open a market order."""
    mt5 = get_mt5()
    direction = req.direction.upper()
    order_type = DIRECTION_MAP.get(direction)
    if order_type is None:
        raise HTTPException(
            status_code=400,
            detail={"error": {"code": "INVALID_DIRECTION", "message": "direction 必须是 BUY 或 SELL"}},
        )

    price_order, digits = await _get_market_execution_price(mt5, req.symbol, direction)

    trade_body = {
        "Action": "200",
        "Login": str(user.mt5_login),
        "Symbol": req.symbol,
        "Type": str(order_type),
        "Volume": str(_lots_to_volume(req.lots)),
        "VolumeExt": str(_lots_to_volume_ext(req.lots)),
        "TypeFill": "2",
        "PriceOrder": price_order,
        "Digits": str(digits),
        "PriceDeviation": "100",
    }
    if req.stop_loss:
        trade_body["PriceSL"] = req.stop_loss
    if req.take_profit:
        trade_body["PriceTP"] = req.take_profit

    try:
        resp = await mt5.post("/api/dealer/send_request", body=trade_body)
        answer = resp.get("answer", {})
        request_id = str(answer.get("id", answer.get("ID", "")))
        if not request_id:
            raise HTTPException(
                status_code=502,
                detail={"error": {"code": "TRADE_SUBMIT_FAILED", "message": "未获取到交易请求 ID"}},
            )

        result = await _poll_trade_result(mt5, request_id)
        if result:
            return TradeResult(
                order=_safe_int(result.get("OrderID", result.get("ResultOrder", 0))),
                deal=_safe_int(result.get("DealID", result.get("ResultDeal", 0))),
                price=str(result.get("Price", result.get("ResultPrice", ""))),
                volume=str(result.get("Volume", result.get("ResultVolume", ""))),
                retcode=str(result.get("Retcode", result.get("ResultRetcode", "0"))),
                message="成交成功",
            )

        return TradeResult(
            order=0,
            deal=0,
            price="",
            volume=req.lots,
            retcode="0",
            message=f"交易请求已提交，等待执行 (request_id={request_id})",
        )
    except MT5ConnectionError:
        raise HTTPException(status_code=503, detail={"error": {"code": "MT5_UNAVAILABLE", "message": "MT5 服务不可用"}})
    except MT5APIError as e:
        raise HTTPException(
            status_code=502,
            detail={"error": {"code": "TRADE_FAILED", "message": str(e), "mt5_retcode": e.retcode}},
        )


@router.post("/close", response_model=TradeResult)
async def trade_close(
    req: TradeCloseRequest,
    user: User = Depends(get_current_user),
):
    """Close a position by reversing the trade direction."""
    mt5 = get_mt5()

    # 1. 查询持仓详情（Symbol, Type, Volume）
    pos_data = await mt5.get(
        "/api/position/get_batch",
        params={"login": str(user.mt5_login)},
    )
    positions = pos_data.get("answer", [])
    logger.info("Close position: looking for %s in %d positions", req.position, len(positions) if isinstance(positions, list) else 0)
    target_pos = None
    if isinstance(positions, list):
        for p in positions:
            if str(p.get("Position", "")) == str(req.position):
                target_pos = p
                break

    if target_pos is None:
        logger.warning("Position %s not found. Available: %s", req.position, [p.get('Position') for p in positions] if isinstance(positions, list) else positions)
        raise HTTPException(
            status_code=404,
            detail={"error": {"code": "POSITION_NOT_FOUND", "message": f"未找到持仓 {req.position}"}},
        )

    logger.info("Found position: %s", {k: target_pos.get(k) for k in ['Position', 'Symbol', 'Action', 'Volume', 'VolumeExt']})
    symbol = target_pos.get("Symbol", "")
    pos_type = int(target_pos.get("Action", target_pos.get("Type", 0)))
    # 反向：BUY(0) -> SELL(1), SELL(1) -> BUY(0)
    close_type = 1 if pos_type == 0 else 0
    close_direction = "SELL" if pos_type == 0 else "BUY"

    # 计算平仓手数
    volume_ext = int(target_pos.get("VolumeExt", 0))
    if req.lots:
        volume = _lots_to_volume(req.lots)
        volume_ext_close = _lots_to_volume_ext(req.lots)
    else:
        volume = int(target_pos.get("Volume", 0))
        volume_ext_close = volume_ext

    # 2. 获取反向执行价格
    price_order, digits = await _get_market_execution_price(mt5, symbol, close_direction)

    trade_body = {
        "Action": "200",
        "Login": str(user.mt5_login),
        "Symbol": symbol,
        "Position": str(req.position),
        "Type": str(close_type),
        "Volume": str(volume),
        "VolumeExt": str(volume_ext_close),
        "TypeFill": "2",
        "PriceOrder": price_order,
        "Digits": str(digits),
        "PriceDeviation": "100",
    }
    logger.info("Close position trade body: %s", trade_body)

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
                price=str(result.get("Price", result.get("ResultPrice", ""))),
                volume=str(result.get("Volume", result.get("ResultVolume", ""))),
                retcode=str(result.get("Retcode", result.get("ResultRetcode", "0"))),
                message="平仓成功",
            )
        return TradeResult(
            order=0,
            deal=0,
            price="",
            volume=req.lots or "",
            retcode="0",
            message=f"平仓请求已提交，等待执行 (request_id={request_id})",
        )
    except MT5ConnectionError:
        raise HTTPException(status_code=503, detail={"error": {"code": "MT5_UNAVAILABLE", "message": "MT5 服务不可用"}})
    except MT5APIError as e:
        raise HTTPException(
            status_code=502,
            detail={"error": {"code": "TRADE_FAILED", "message": str(e), "mt5_retcode": e.retcode}},
        )


@router.put("/modify", response_model=TradeResult)
async def trade_modify(
    req: TradeModifyRequest,
    user: User = Depends(get_current_user),
):
    """Modify stop loss / take profit."""
    mt5 = get_mt5()
    trade_body = {
        "Action": "200",
        "Login": str(user.mt5_login),
        "Position": str(req.position),
    }
    if req.stop_loss:
        trade_body["PriceSL"] = req.stop_loss
    if req.take_profit:
        trade_body["PriceTP"] = req.take_profit

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
                price=str(result.get("Price", result.get("ResultPrice", ""))),
                retcode=str(result.get("Retcode", result.get("ResultRetcode", "0"))),
                message="修改成功",
            )
        return TradeResult(
            order=0,
            deal=0,
            price="",
            retcode="0",
            message=f"修改请求已提交，等待执行 (request_id={request_id})",
        )
    except MT5ConnectionError:
        raise HTTPException(status_code=503, detail={"error": {"code": "MT5_UNAVAILABLE", "message": "MT5 服务不可用"}})
    except MT5APIError as e:
        raise HTTPException(
            status_code=502,
            detail={"error": {"code": "TRADE_FAILED", "message": str(e), "mt5_retcode": e.retcode}},
        )


@router.get("/check_margin", response_model=MarginCheckResponse)
async def check_margin(
    symbol: str,
    direction: str,
    lots: str,
    user: User = Depends(get_current_user),
):
    """Check margin requirements."""
    mt5 = get_mt5()
    order_type = DIRECTION_MAP.get(direction.upper(), 0)
    data = await mt5.get(
        "/api/trade/check_margin",
        params={
            "login": str(user.mt5_login),
            "symbol": symbol,
            "type": str(order_type),
            "volume": str(_lots_to_volume_ext(lots)),
        },
    )
    new_state = data.get("answer", {}).get("new", {})
    return MarginCheckResponse(
        margin=str(new_state.get("Margin", "0")),
        free_margin=str(new_state.get("MarginFree", "0")),
        margin_level=str(new_state.get("MarginLevel", "0")),
    )


@router.get("/calc_profit", response_model=ProfitCalcResponse)
async def calc_profit(
    symbol: str,
    direction: str,
    lots: str,
    price_open: str,
    price_close: str,
    user: User = Depends(get_current_user),
):
    """Calculate profit."""
    mt5 = get_mt5()
    user_data = await mt5.get("/api/user/get", params={"login": str(user.mt5_login)})
    group = user_data.get("answer", {}).get("Group", "demo\\retail")

    order_type = DIRECTION_MAP.get(direction.upper(), 0)
    data = await mt5.get(
        "/api/trade/calc_profit",
        params={
            "group": group,
            "symbol": symbol,
            "type": str(order_type),
            "volume": str(_lots_to_volume_ext(lots)),
            "price_open": price_open,
            "price_close": price_close,
        },
    )
    answer = data.get("answer", {})
    return ProfitCalcResponse(
        profit=str(answer.get("Profit", "0")),
        profit_rate=str(answer.get("Profit_rate", "0")),
    )
