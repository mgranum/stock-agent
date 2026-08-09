import type { AdminState, CompanyDetail, Period, SearchResponse, StockMutation, TodayResponse } from "./types";

async function readJson<T>(response: Response, fallback: string): Promise<T> {
  if (!response.ok) {
    const body = await response.json().catch(() => null);
    throw new Error(body?.detail || fallback);
  }
  return response.json();
}

export async function fetchCompanyDetail(
  ticker: string,
  period: Period,
  signal?: AbortSignal,
): Promise<CompanyDetail> {
  const params = new URLSearchParams({ period });
  const response = await fetch(`/api/stocks/${encodeURIComponent(ticker)}?${params}`, { signal });
  return readJson(response, "Kunne ikke hente selskapsdata");
}

export async function fetchToday(signal?: AbortSignal): Promise<TodayResponse> {
  return readJson(await fetch("/api/today", { signal }), "Kunne ikke hente dagens oversikt");
}

export async function searchCompanies(query: string, signal?: AbortSignal): Promise<SearchResponse> {
  const params = new URLSearchParams({ q: query });
  return readJson(await fetch(`/api/search?${params}`, { signal }), "Søket feilet");
}

export async function fetchAdmin(signal?: AbortSignal): Promise<AdminState> {
  return readJson(await fetch("/api/admin", { signal }), "Kunne ikke hente administrasjonsdata");
}

export async function updateStock(
  ticker: string,
  values: { owned: boolean; average_cost: number | null; watchlists: string[] },
): Promise<StockMutation> {
  return readJson(
    await fetch(`/api/admin/stocks/${encodeURIComponent(ticker)}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(values),
    }),
    "Kunne ikke lagre endringene",
  );
}
