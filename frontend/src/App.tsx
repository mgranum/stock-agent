import { FormEvent, useEffect, useState } from "react";

import { fetchCompanyDetail } from "./api";
import { PriceChart } from "./components/PriceChart";
import { stockPath, tickerFromPath } from "./routing";
import type { CompanyDetail, Period } from "./types";

export const PERIODS: Period[] = ["1u", "1m", "3m", "6m", "i år", "1 år", "3 år", "maks"];

function currentPeriod(): Period {
  const value = new URLSearchParams(window.location.search).get("period") as Period | null;
  return value && PERIODS.includes(value) ? value : "3m";
}

export default function App() {
  const [ticker, setTicker] = useState(() => tickerFromPath(window.location.pathname));
  const [period, setPeriod] = useState<Period>(currentPeriod);
  const [search, setSearch] = useState(ticker ?? "");
  const [detail, setDetail] = useState<CompanyDetail | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [showVolume, setShowVolume] = useState(true);
  const [showSma20, setShowSma20] = useState(true);
  const [showSma50, setShowSma50] = useState(false);

  useEffect(() => {
    const onPopState = () => {
      const nextTicker = tickerFromPath(window.location.pathname);
      setTicker(nextTicker);
      setSearch(nextTicker ?? "");
      setPeriod(currentPeriod());
    };
    window.addEventListener("popstate", onPopState);
    return () => window.removeEventListener("popstate", onPopState);
  }, []);

  useEffect(() => {
    if (!ticker) {
      setDetail(null);
      return;
    }
    const controller = new AbortController();
    setLoading(true);
    setError(null);
    fetchCompanyDetail(ticker, period, controller.signal)
      .then(setDetail)
      .catch((reason) => {
        if (reason.name !== "AbortError") setError(reason.message);
      })
      .finally(() => setLoading(false));
    return () => controller.abort();
  }, [ticker, period]);

  const navigate = (nextTicker: string, nextPeriod: Period = period) => {
    const normalized = nextTicker.trim().toUpperCase();
    if (!normalized) return;
    const params = new URLSearchParams({ period: nextPeriod });
    window.history.pushState({}, "", `${stockPath(normalized)}?${params}`);
    setTicker(normalized);
    setSearch(normalized);
    setPeriod(nextPeriod);
  };

  const submitSearch = (event: FormEvent) => {
    event.preventDefault();
    navigate(search);
  };

  const choosePeriod = (nextPeriod: Period) => {
    if (!ticker) return;
    navigate(ticker, nextPeriod);
  };

  return (
    <div className="app-shell">
      <header className="topbar">
        <a className="brand" href="/" aria-label="Stock Agent startside">
          <span className="brand-mark">SA</span>
          <span>Stock Agent</span>
        </a>
        <form className="ticker-search" onSubmit={submitSearch} role="search">
          <label className="sr-only" htmlFor="ticker-search">Søk etter ticker</label>
          <input
            id="ticker-search"
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            placeholder="Søk ticker, f.eks. NVDA"
            autoComplete="off"
          />
          <button type="submit">Vis aksje</button>
        </form>
        <span className="environment">ARKITEKTURSPIKE</span>
      </header>

      <main>
        {!ticker && (
          <section className="empty-state">
            <span className="eyebrow">Selskapsdetaljer</span>
            <h1>Finn en aksje</h1>
            <p>Søk etter en ticker for å åpne den nye skrivebeskyttede detaljflaten.</p>
          </section>
        )}

        {ticker && (
          <>
            <section className="company-heading">
              <div>
                <span className="eyebrow">Selskapsdetaljer</span>
                <h1>{detail?.company_name ?? ticker}</h1>
                <span className="ticker-label">{ticker}</span>
              </div>
              {detail && (
                <div className="quote" aria-label="Siste kurs og utvikling">
                  <strong>{detail.current_price.toLocaleString("nb-NO", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</strong>
                  <span className={detail.period_change_pct >= 0 ? "positive" : "negative"}>
                    {detail.period_change_pct >= 0 ? "+" : ""}{detail.period_change_pct.toFixed(2)}%
                  </span>
                </div>
              )}
            </section>

            <section className="chart-card">
              <div className="chart-toolbar">
                <div className="periods" aria-label="Velg tidsperiode">
                  {PERIODS.map((value) => (
                    <button
                      key={value}
                      className={period === value ? "active" : ""}
                      aria-pressed={period === value}
                      onClick={() => choosePeriod(value)}
                    >
                      {value}
                    </button>
                  ))}
                </div>
                <div className="indicators" aria-label="Grafverktøy">
                  <label><input type="checkbox" checked={showVolume} onChange={(event) => setShowVolume(event.target.checked)} /> Volum</label>
                  <label><input type="checkbox" checked={showSma20} onChange={(event) => setShowSma20(event.target.checked)} /> SMA20</label>
                  <label><input type="checkbox" checked={showSma50} onChange={(event) => setShowSma50(event.target.checked)} /> SMA50</label>
                </div>
              </div>

              {loading && <div className="chart-placeholder">Henter kursdata…</div>}
              {error && <div className="error" role="alert">{error}</div>}
              {!loading && !error && detail && <PriceChart candles={detail.candles} showVolume={showVolume} showSma20={showSma20} showSma50={showSma50} />}
              {detail && <p className="data-caption">Sist oppdatert {new Date(detail.as_of).toLocaleString("nb-NO")}</p>}
            </section>

            <section className="spike-note">
              <span>Avgrenset migrasjonstest</span>
              <p>Denne flaten viser kursdata og grafverktøy. Agentvurdering, fundamentalt og nyheter kobles på etter at arkitekturen er godkjent.</p>
            </section>
          </>
        )}
      </main>
    </div>
  );
}
