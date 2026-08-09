from pydantic import BaseModel, ConfigDict, Field


class DataMeta(BaseModel):
    status: str
    environment: str
    model_version: str
    built_at: str | None = None
    snapshot_date: str | None = None
    message: str | None = None


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
    recommendation: str | None = None
    score: float | None = None
    trend_regime: str | None = None
    reasoning: list[str] = Field(default_factory=list)
    technical_score: float | None = None
    fundamental_score: float | None = None
    fundamental_label: str | None = None
    fundamental_reasons: list[str] = Field(default_factory=list)
    history_score: float | None = None
    history_label: str | None = None
    analyst_consensus: str | None = None
    analyst_count: int | None = None
    target_mean: float | None = None
    upside_pct: float | None = None
    next_event: dict | None = None
    news: list[dict] = Field(default_factory=list)
    candles: list[Candle]
    meta: DataMeta


class HealthResponse(BaseModel):
    status: str
    environment: str


class StockSummary(BaseModel):
    ticker: str
    company_name: str
    recommendation: str | None = None
    score: float | None = None
    current_price: float | None = None
    change_pct: float | None = None
    trend_regime: str | None = None
    owned: bool = False
    average_cost: float | None = None
    requires_attention: bool = False


class ActionSummary(BaseModel):
    ticker: str | None = None
    title: str
    detail: str | None = None
    recommendation: str | None = None
    priority: str | None = None
    source: str | None = None


class TodayResponse(BaseModel):
    meta: DataMeta
    attention: list[ActionSummary]
    owned: list[StockSummary]
    watchlist: list[StockSummary]
    candidates: list[StockSummary]


class ExploreResponse(BaseModel):
    meta: DataMeta
    watchlist_ranking: list[StockSummary]
    candidates: list[StockSummary]


class Position(BaseModel):
    ticker: str
    company_name: str
    average_cost: float | None = None
    shares: float | None = None
    current_price: float | None = None
    recommendation: str | None = None
    portfolio_action: str | None = None
    stop_loss: float | None = None
    trailing_stop_loss: float | None = None


class PositionsResponse(BaseModel):
    meta: DataMeta
    positions: list[Position]


class WatchlistGroup(BaseModel):
    name: str
    tickers: list[str]
    editable: bool


class WatchlistsResponse(BaseModel):
    meta: DataMeta
    watchlists: list[WatchlistGroup]


class SearchResult(BaseModel):
    ticker: str
    company_name: str
    owned: bool
    watchlists: list[str]


class SearchResponse(BaseModel):
    meta: DataMeta
    query: str
    results: list[SearchResult]


class RefreshStatusResponse(BaseModel):
    environment: str
    status: str
    status_label: str
    updated_at: str | None = None
    updated_at_source: str
    last_successful_date: str | None = None
    last_error_count: int | None = None


class ModelStatusResponse(BaseModel):
    meta: DataMeta
    refresh: RefreshStatusResponse


class ChatRequest(BaseModel):
    question: str = Field(min_length=1, max_length=1000)


class ChatResponse(BaseModel):
    meta: DataMeta
    answer: str
