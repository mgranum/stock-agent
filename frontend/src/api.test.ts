import { afterEach, describe, expect, it, vi } from "vitest";

import { fetchCompanyDetail, fetchToday, searchCompanies } from "./api";

afterEach(() => vi.unstubAllGlobals());

describe("read API client", () => {
  it("uses the selected non-intraday period for company details", async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({ ticker: "NVDA" }), { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);

    await fetchCompanyDetail("NVDA", "1u");

    expect(fetchMock).toHaveBeenCalledWith("/api/stocks/NVDA?period=1u", { signal: undefined });
  });

  it("loads today and encodes company searches", async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(new Response(JSON.stringify({ owned: [] }), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ results: [] }), { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);

    await fetchToday();
    await searchCompanies("Novo B");

    expect(fetchMock.mock.calls[0][0]).toBe("/api/today");
    expect(fetchMock.mock.calls[1][0]).toBe("/api/search?q=Novo+B");
  });

  it("surfaces the API error message", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify({ detail: "Ugyldig ticker" }), { status: 422 })));

    await expect(fetchCompanyDetail("?", "3m")).rejects.toThrow("Ugyldig ticker");
  });
});
