export type Period = "1u" | "1m" | "3m" | "6m" | "i år" | "1 år" | "3 år" | "maks";

export type Candle = {
  time: string;
  open: number | null;
  high: number | null;
  low: number | null;
  close: number | null;
  volume: number | null;
  sma20: number | null;
  sma50: number | null;
};

export type CompanyDetail = {
  ticker: string;
  company_name: string;
  period: Period;
  currency: string | null;
  as_of: string;
  current_price: number;
  period_change_pct: number;
  recommendation: string | null;
  score: number | null;
  trend_regime: string | null;
  reasoning: string[];
  technical_score: number | null;
  fundamental_score: number | null;
  fundamental_label: string | null;
  fundamental_reasons: string[];
  history_score: number | null;
  history_label: string | null;
  analyst_consensus: string | null;
  analyst_count: number | null;
  target_mean: number | null;
  upside_pct: number | null;
  next_event: Record<string, unknown> | null;
  news: NewsItem[];
  candles: Candle[];
  meta: DataMeta;
};

export type DataMeta = {
  status: "fresh" | "stale" | "missing" | "invalid";
  environment: string;
  model_version: string;
  built_at: string | null;
  snapshot_date: string | null;
  message: string | null;
};

export type StockSummary = {
  ticker: string;
  company_name: string;
  recommendation: string | null;
  score: number | null;
  current_price: number | null;
  change_pct: number | null;
  trend_regime: string | null;
  owned: boolean;
  average_cost: number | null;
  requires_attention: boolean;
  currency: string | null;
  rationale: string | null;
  action_label: string | null;
  stop_level: number | null;
  stop_kind: string | null;
  distance_to_stop_pct: number | null;
  gain_pct: number | null;
  benchmark: string | null;
  relative_strength_pct: number | null;
  changed_today: boolean;
  change_label: string | null;
};

export type ActionSummary = {
  ticker: string | null;
  title: string;
  detail: string | null;
  recommendation: string | null;
  priority: string | null;
  source: string | null;
};

export type TodayResponse = {
  meta: DataMeta;
  attention: ActionSummary[];
  owned: StockSummary[];
  watchlist: StockSummary[];
  candidates: StockSummary[];
};

export type SearchResult = {
  ticker: string;
  company_name: string;
  owned: boolean;
  watchlists: string[];
};

export type SearchResponse = { meta: DataMeta; query: string; results: SearchResult[] };

export type NewsItem = {
  ticker?: string;
  headline?: string;
  url?: string;
  publisher?: string;
  published_at?: string;
  sentiment?: string;
};

export type Position = {
  ticker: string;
  company_name: string;
  average_cost: number | null;
  shares: number | null;
  current_price: number | null;
  recommendation: string | null;
  portfolio_action: string | null;
  stop_loss: number | null;
  trailing_stop_loss: number | null;
};

export type WatchlistGroup = {
  name: string;
  tickers: string[];
  editable: boolean;
};

export type AdminState = {
  meta: DataMeta;
  writable: boolean;
  positions: Position[];
  watchlists: WatchlistGroup[];
};

export type StockMutation = {
  ticker: string;
  owned: boolean;
  average_cost: number | null;
  watchlists: string[];
  backup_id: string;
};
