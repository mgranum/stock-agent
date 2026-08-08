import { stockPath, tickerFromPath } from "./routing";
import { describe, expect, it } from "vitest";

describe("ticker routing", () => {
  it("loads ticker from a direct company URL", () => {
    expect(tickerFromPath("/stocks/nvda")).toBe("NVDA");
    expect(tickerFromPath("/stocks/NOVO-B.CO/")).toBe("NOVO-B.CO");
  });

  it("does not invent a ticker on other routes", () => {
    expect(tickerFromPath("/")).toBeNull();
    expect(tickerFromPath("/explore")).toBeNull();
  });

  it("creates a canonical encoded path", () => {
    expect(stockPath(" novo-b.co ")).toBe("/stocks/NOVO-B.CO");
  });
});
