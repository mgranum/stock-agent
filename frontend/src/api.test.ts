import { afterEach, describe, expect, it, vi } from "vitest";

import { askChat, fetchAdmin, fetchCompanyDetail, fetchExplore, fetchModelData, fetchToday, searchCompanies, updateStock } from "./api";

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

  it("loads admin state and sends a typed stock mutation", async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(new Response(JSON.stringify({ positions: [] }), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ ticker: "NVDA" }), { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);

    await fetchAdmin();
    await updateStock("NVDA", { owned: true, average_cost: 125.5, watchlists: ["USA"] });

    expect(fetchMock.mock.calls[0][0]).toBe("/api/admin");
    expect(fetchMock.mock.calls[1][0]).toBe("/api/admin/stocks/NVDA");
    expect(fetchMock.mock.calls[1][1]).toMatchObject({ method: "PUT" });
    expect(JSON.parse(fetchMock.mock.calls[1][1].body)).toEqual({
      owned: true,
      average_cost: 125.5,
      watchlists: ["USA"],
    });
  });

  it("loads explore and model status from their presentation endpoints", async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(new Response(JSON.stringify({ watchlist_ranking: [] }), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ snapshots: {} }), { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);

    await fetchExplore();
    await fetchModelData();

    expect(fetchMock.mock.calls[0][0]).toBe("/api/explore");
    expect(fetchMock.mock.calls[1][0]).toBe("/api/model-data");
  });

  it("sends chat questions as JSON to the existing agent endpoint", async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({ answer: "Svar" }), { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);

    await askChat("Hva bør jeg følge med på?", { view: "detail", ticker: "AAPL", companyName: "Apple Inc." });

    expect(fetchMock).toHaveBeenCalledWith("/api/chat", expect.objectContaining({ method: "POST" }));
    expect(JSON.parse(fetchMock.mock.calls[0][1].body)).toEqual({
      question: "Hva bør jeg følge med på?",
      view: "detail",
      ticker: "AAPL",
      company_name: "Apple Inc.",
    });
  });
});
