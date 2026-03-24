"""Pydantic Schemas — 行情数据"""
from pydantic import BaseModel


class QuoteData(BaseModel):
    """单个品种报价"""
    symbol: str
    bid: str
    ask: str
    last: str
    volume: str = "0"
    datetime: int  # 毫秒时间戳


class QuoteResponse(BaseModel):
    """报价查询响应"""
    quotes: list[QuoteData]


class TickStatData(BaseModel):
    """品种统计数据"""
    symbol: str
    high: str = "0"
    low: str = "0"
    last: str = "0"
    volume: str = "0"
    buy_count: str = "0"
    sell_count: str = "0"


class TickStatResponse(BaseModel):
    """统计数据响应"""
    stats: list[TickStatData]


class SymbolInfo(BaseModel):
    """品种简要信息"""
    symbol: str
    path: str = ""
    description: str = ""
    digits: int = 5
    currency_base: str = ""
    currency_profit: str = ""
    trade_mode: int = 0


class SymbolListResponse(BaseModel):
    """品种列表响应"""
    symbols: list[SymbolInfo]


class CandleData(BaseModel):
    """K 线蜡烛"""
    timestamp: int
    open: str
    high: str
    low: str
    close: str
    volume: str = "0"


class CandleResponse(BaseModel):
    """K 线响应"""
    symbol: str
    timeframe: str
    candles: list[CandleData]
