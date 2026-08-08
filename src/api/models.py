from pydantic import BaseModel, ConfigDict


class Candle(BaseModel):
    time: str
    open: float | None
    high: float | None
    low: float | None
    close: float | None
    volume: float | None
    sma20: float | None
    sma50: float | None


class CompanyDetailResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    ticker: str
    company_name: str
    period: str
    currency: str | None
    as_of: str
    current_price: float
    period_change_pct: float
    candles: list[Candle]


class HealthResponse(BaseModel):
    status: str
    environment: str
