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
  candles: Candle[];
};
