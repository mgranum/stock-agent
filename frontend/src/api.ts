import type { CompanyDetail, Period, SearchResponse, TodayResponse } from "./types";

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
