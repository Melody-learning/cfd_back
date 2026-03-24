"""Pydantic Schemas — 交易与账户"""
from pydantic import BaseModel, Field


# ──────────────────── 交易请求 ────────────────────

class TradeOpenRequest(BaseModel):
    """市价开仓"""
    symbol: str
    direction: str = Field(description="BUY 或 SELL")
    lots: str = Field(description="手数，如 0.01")
    stop_loss: str | None = None
    take_profit: str | None = None


class TradeCloseRequest(BaseModel):
    """平仓"""
    position: int = Field(description="持仓单号")
    lots: str | None = Field(None, description="部分平仓手数，None 表示全部平仓")


class TradeModifyRequest(BaseModel):
    """修改止损止盈"""
    position: int
    stop_loss: str | None = None
    take_profit: str | None = None


class TradeResult(BaseModel):
    """交易执行结果"""
    order: int = 0
    deal: int = 0
    price: str = ""
    volume: str = ""
    retcode: str = ""
    message: str = ""


# ──────────────────── 保证金与盈利 ────────────────────

class MarginCheckRequest(BaseModel):
    symbol: str
    direction: str
    lots: str


class MarginCheckResponse(BaseModel):
    margin: str = ""
    free_margin: str = ""
    margin_level: str = ""


class ProfitCalcRequest(BaseModel):
    symbol: str
    direction: str
    lots: str
    price_open: str
    price_close: str


class ProfitCalcResponse(BaseModel):
    profit: str = ""
    profit_rate: str = ""


# ──────────────────── 账户信息 ────────────────────

class AccountInfo(BaseModel):
    login: int
    group: str = ""
    balance: str = "0.00"
    credit: str = "0.00"
    equity: str = "0.00"
    margin: str = "0.00"
    free_margin: str = "0.00"
    margin_level: str = "0.00"
    leverage: int = 0
    currency: str = "USD"


# ──────────────────── 持仓 ────────────────────

class PositionInfo(BaseModel):
    position: int = 0
    symbol: str = ""
    direction: str = ""
    lots: str = "0"
    price_open: str = "0"
    price_current: str = "0"
    profit: str = "0"
    stop_loss: str = "0"
    take_profit: str = "0"
    time_create: int = 0


class PositionListResponse(BaseModel):
    positions: list[PositionInfo]
