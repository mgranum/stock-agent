import type { CompanyDetail, Period } from "./types";

export async function fetchCompanyDetail(
  ticker: string,
  period: Period,
  signal?: AbortSignal,
): Promise<CompanyDetail> {
  const params = new URLSearchParams({ period });
  const response = await fetch(`/api/stocks/${encodeURIComponent(ticker)}?${params}`, { signal });
  if (!response.ok) {
    const body = await response.json().catch(() => null);
    throw new Error(body?.detail || "Kunne ikke hente selskapsdata");
  }
  return response.json();
}
