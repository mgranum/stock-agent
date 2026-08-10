import { FormEvent, useEffect, useMemo, useRef, useState } from "react";

import { fetchAdmin, fetchCompanyDetail, fetchExplore, fetchModelData, fetchToday, searchCompanies } from "./api";
import { AdminPage } from "./components/AdminPage";
import { ChatPanel } from "./components/ChatPanel";
import { ExplorePage } from "./components/ExplorePage";
import { ModelDataPage } from "./components/ModelDataPage";
import { PriceChart } from "./components/PriceChart";
import { StockEditor } from "./components/StockEditor";
import { stockPath, tickerFromPath } from "./routing";
import type { AdminState, CompanyDetail, ExploreResponse, ModelDataResponse, Period, SearchResult, StockMutation, StockSummary, TodayResponse } from "./types";

const PERIODS: Period[] = ["1u", "1m", "3m", "6m", "i år", "1 år", "3 år", "maks"];

function currentPeriod(): Period {
  const value = new URLSearchParams(window.location.search).get("period") as Period | null;
  return value && PERIODS.includes(value) ? value : "3m";
}

function formatNumber(value: number | null | undefined, digits = 2) {
  return value == null ? "–" : value.toLocaleString("nb-NO", { maximumFractionDigits: digits });
}

function tone(value: number | null | undefined) {
  if (value == null || value === 0) return "neutral";
  return value > 0 ? "positive" : "negative";
}

function signed(value: number | null | undefined, suffix = "%") {
  if (value == null) return "–";
  const prefix = value > 0 ? "+" : "";
  return `${prefix}${formatNumber(value)} ${suffix}`;
}

function PeriodSelector({ period, onChange }: { period: Period; onChange: (period: Period) => void }) {
  return <div className="periods" aria-label="Velg tidsperiode">{PERIODS.map((value) => (
    <button key={value} type="button" className={period === value ? "active" : ""} aria-pressed={period === value} onClick={() => onChange(value)}>{value}</button>
  ))}</div>;
}

function Sparkline({ detail }: { detail: CompanyDetail }) {
  const values = detail.candles.map((row) => row.close).filter((value): value is number => value != null);
  if (values.length < 2) return <span className="spark-empty">–</span>;
  const sampled = values.filter((_, index) => index % Math.max(1, Math.floor(values.length / 24)) === 0).slice(-25);
  const low = Math.min(...sampled);
  const high = Math.max(...sampled);
  const points = sampled.map((value, index) => `${(index / (sampled.length - 1)) * 112},${32 - ((value - low) / Math.max(high - low, 1)) * 28}`).join(" ");
  return <svg className={`spark ${tone(detail.period_change_pct)}`} viewBox="0 0 112 36" role="img" aria-label={`Kursutvikling ${detail.period_change_pct.toFixed(1)} prosent`}><polyline points={points} /></svg>;
}

function Performance({ ticker, period }: { ticker: string; period: Period }) {
  const [detail, setDetail] = useState<CompanyDetail | null>(null);
  const [failed, setFailed] = useState(false);
  useEffect(() => {
    const controller = new AbortController();
    setDetail(null); setFailed(false);
    fetchCompanyDetail(ticker, period, controller.signal).then(setDetail).catch(() => { if (!controller.signal.aborted) { setDetail(null); setFailed(true); } });
    return () => controller.abort();
  }, [ticker, period]);
  if (failed) return <div className="performance performance-missing"><span>Kurve utilgjengelig</span></div>;
  if (!detail) return <div className="performance loading-mini"><span /><small>Henter…</small></div>;
  return <div className="performance"><Sparkline detail={detail} /><strong className={tone(detail.period_change_pct)}>{detail.period_change_pct >= 0 ? "+" : ""}{formatNumber(detail.period_change_pct)} %</strong></div>;
}

function StockRow({ stock, period, onOpen, onEdit }: { stock: StockSummary; period: Period; onOpen: (ticker: string) => void; onEdit: (ticker: string, companyName?: string) => void }) {
  return <article className={`stock-row ${stock.requires_attention ? "needs-attention" : ""}`}>
    <button className="stock-identity" onClick={() => onOpen(stock.ticker)}>
      <span className="ticker-avatar">{stock.ticker.slice(0, 2)}</span><span><strong>{stock.ticker} · {stock.company_name}</strong><small>Kurs {formatNumber(stock.current_price)} {stock.currency ?? ""}</small></span>
    </button>
    <div className={`recommendation ${stock.changed_today ? "changed" : ""}`}><span className="signal-dot" /> <strong>{stock.action_label ?? stock.recommendation ?? "Ikke vurdert"}</strong><small>{stock.change_label ?? stock.rationale ?? stock.trend_regime ?? "Begrunnelse mangler"}</small></div>
    <Performance ticker={stock.ticker} period={period} />
    {stock.owned ? <div className="decision-signal owned-signal"><strong className={tone(stock.distance_to_stop_pct)}>{stock.distance_to_stop_pct == null ? "–" : `${formatNumber(Math.abs(stock.distance_to_stop_pct))} %`}</strong><small>{stock.distance_to_stop_pct == null ? "Stop mangler" : `${stock.distance_to_stop_pct > 0 ? "over" : stock.distance_to_stop_pct < 0 ? "under" : "ved"} ${stock.stop_kind ?? "stop"} ${formatNumber(stock.stop_level)}`}</small><span>GAV {formatNumber(stock.average_cost)} · <b className={tone(stock.gain_pct)}>{signed(stock.gain_pct)}</b></span></div> : <div className="decision-signal watch-signal"><strong className={tone(stock.relative_strength_pct)}>{signed(stock.relative_strength_pct)}</strong><small>mot {stock.benchmark ?? "benchmark"}</small><span>Trend: {stock.trend_regime?.toLocaleLowerCase("nb-NO") ?? "mangler"}</span></div>}
    <div className="score"><small>Score</small><strong>{formatNumber(stock.score, 0)}</strong></div>
    <button className="arrow-button edit-row-button" aria-label={`Administrer ${stock.ticker}`} onClick={() => onEdit(stock.ticker, stock.company_name)}>✎</button>
  </article>;
}

function StockSection({ title, items, period, onOpen, onEdit, attentionFilter = false }: { title: string; items: StockSummary[]; period: Period; onOpen: (ticker: string) => void; onEdit: (ticker: string, companyName?: string) => void; attentionFilter?: boolean }) {
  const [expanded, setExpanded] = useState(false);
  const [onlyAttention, setOnlyAttention] = useState(false);
  const relevant = onlyAttention ? items.filter((item) => item.requires_attention) : items;
  const visible = expanded || onlyAttention ? relevant : relevant.slice(0, 3);
  const attentionCount = items.filter((item) => item.requires_attention).length;
  return <section className="list-section">
    <div className="section-heading"><div><h2>{title}</h2><span className="count">{items.length}</span>{attentionCount > 0 && <button className={`attention-filter ${onlyAttention ? "selected" : ""}`} onClick={() => { setOnlyAttention(!onlyAttention); setExpanded(true); }}>{attentionCount} krever oppmerksomhet</button>}</div><small>{attentionFilter ? "GAV brukes kun til beslutningsstøtte" : "Klikk ticker for full analyse"}</small></div>
    <div className="stock-table"><div className="table-labels"><span>Aksje</span><span>Agent</span><span>Utvikling</span><span>{attentionFilter ? "Nøkkelnivå" : "Beslutningssignal"}</span><span>Score</span><span /></div>
      {visible.map((stock) => <StockRow key={stock.ticker} stock={stock} period={period} onOpen={onOpen} onEdit={onEdit} />)}
      {!visible.length && <div className="list-empty">Ingen aksjer i denne visningen.</div>}
    </div>
    {relevant.length > 3 && !onlyAttention && <button className="expand-button" onClick={() => setExpanded(!expanded)}>{expanded ? "Vis de første 3 ↑" : `Vis alle ${relevant.length} ↓`}</button>}
  </section>;
}

function CandidateCards({ items, period, onOpen }: { items: StockSummary[]; period: Period; onOpen: (ticker: string) => void }) {
  return <section className="list-section"><div className="section-heading"><div><h2>Nye kandidater</h2><span className="count">{items.length}</span></div><small>Ikke i watchlist · kvalifisert av dagens screening</small></div>
    {items.length ? <div className="candidate-grid">{items.slice(0, 3).map((stock, index) => <article className="candidate-card" key={stock.ticker}><div className="candidate-head"><span className="rank">#{index + 1}</span><button onClick={() => onOpen(stock.ticker)}><strong>{stock.ticker}</strong><small>{stock.company_name}</small></button><span className="candidate-score">{formatNumber(stock.score, 0)}</span></div><Performance ticker={stock.ticker} period={period} /><p>{stock.trend_regime ?? "Trenddata mangler"}</p><button className="text-link" onClick={() => onOpen(stock.ticker)}>Se analyse →</button></article>)}</div> : <div className="list-empty">Ingen nye kandidater i siste screening.</div>}
  </section>;
}

function SearchBox({ onOpen, onEdit }: { onOpen: (ticker: string) => void; onEdit: (ticker: string, companyName?: string) => void }) {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<SearchResult[]>([]);
  const [open, setOpen] = useState(false);
  const wrapper = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (query.trim().length < 1) { setResults([]); return; }
    const controller = new AbortController();
    const timer = window.setTimeout(() => searchCompanies(query, controller.signal).then((data) => { setResults(data.results); setOpen(true); }).catch(() => setResults([])), 180);
    return () => { window.clearTimeout(timer); controller.abort(); };
  }, [query]);
  useEffect(() => { const close = (event: MouseEvent) => { if (!wrapper.current?.contains(event.target as Node)) setOpen(false); }; document.addEventListener("mousedown", close); return () => document.removeEventListener("mousedown", close); }, []);
  const directTicker = /^[A-Za-z0-9^][A-Za-z0-9.^-]{0,19}$/.test(query.trim()) ? query.trim().toUpperCase() : null;
  const openTicker = (ticker: string) => { onOpen(ticker); setQuery(""); setResults([]); setOpen(false); };
  const submit = (event: FormEvent) => { event.preventDefault(); const ticker = results[0]?.ticker ?? directTicker; if (ticker) openTicker(ticker); };
  return <div className="search-wrap" ref={wrapper}><form className="global-search" onSubmit={submit} role="search"><span aria-hidden="true">⌕</span><label className="sr-only" htmlFor="company-search">Søk selskap eller ticker</label><input id="company-search" value={query} onFocus={() => setOpen(true)} onChange={(event) => setQuery(event.target.value)} placeholder="Søk selskap eller ticker" autoComplete="off" /></form>{open && query && <div className="search-results" role="listbox">{results.map((result) => <div className="search-result-row" key={result.ticker}><button onClick={() => openTicker(result.ticker)}><span className="ticker-avatar">{result.ticker.slice(0, 2)}</span><span><strong>{result.ticker}</strong><small>{result.company_name}</small></span><span className="search-tags">{result.owned ? "Eid" : result.watchlists[0] ?? ""}</span></button><button className="search-edit" aria-label={`Administrer ${result.ticker}`} onClick={() => { onEdit(result.ticker, result.company_name); setOpen(false); setQuery(""); }}>✎</button></div>)}{!results.length && <p>{directTicker ? `Trykk Enter for å åpne ${directTicker}.` : "Ingen treff i portefølje eller watchlists."}</p>}</div>}</div>;
}

function TodayPage({ data, period, setPeriod, onOpen, onEdit }: { data: TodayResponse | null; period: Period; setPeriod: (period: Period) => void; onOpen: (ticker: string) => void; onEdit: (ticker: string, companyName?: string) => void }) {
  if (!data) return <div className="page-loading">Henter dagens oversikt…</div>;
  return <><div className="page-heading"><div><span className="eyebrow">Beslutningsstøtte</span><h1>Dagens aksjer</h1><p>Eide aksjer først, deretter watchlist og nye kandidater.</p></div><div className="page-controls"><span className={`data-status ${data.meta.status}`}>{data.meta.status === "fresh" ? "Oppdatert" : data.meta.message ?? data.meta.status}</span><PeriodSelector period={period} onChange={setPeriod} /></div></div>
    <StockSection title="Eide aksjer" items={data.owned} period={period} onOpen={onOpen} onEdit={onEdit} attentionFilter />
    <StockSection title="Watchlist" items={data.watchlist} period={period} onOpen={onOpen} onEdit={onEdit} />
    <CandidateCards items={data.candidates} period={period} onOpen={onOpen} />
  </>;
}

function DetailPage({ ticker, period, setPeriod, detail, loading, error, onEdit }: { ticker: string; period: Period; setPeriod: (period: Period) => void; detail: CompanyDetail | null; loading: boolean; error: string | null; onEdit: (ticker: string, companyName?: string) => void }) {
  const [showVolume, setShowVolume] = useState(true); const [showSma20, setShowSma20] = useState(true); const [showSma50, setShowSma50] = useState(false);
  const event = detail?.next_event ?? null;
  const primaryRecommendation = detail?.owned ? detail.action_label ?? detail.recommendation : detail?.recommendation;
  const primaryReason = detail?.owned ? detail.action_reason ?? detail.reasoning[0] ?? detail.trend_regime : detail?.reasoning[0] ?? detail?.trend_regime;
  const modelContext = detail?.owned && detail.action_label && detail.recommendation ? `Grunnmodell: ${detail.recommendation}` : null;
  return <><section className="company-heading"><div><span className="eyebrow">Selskapsdetaljer</span><h1>{detail?.company_name ?? ticker}</h1><span className="ticker-label">{ticker}</span></div>{detail && <div className="detail-heading-actions"><div className="quote"><strong>{formatNumber(detail.current_price)}</strong><span className={tone(detail.period_change_pct)}>{detail.period_change_pct >= 0 ? "+" : ""}{formatNumber(detail.period_change_pct)} %</span></div><button className="manage-button" onClick={() => onEdit(ticker, detail.company_name)}>Administrer aksje</button></div>}</section>
    {detail && <section className="agent-strip"><div><span className="eyebrow">Agentvurdering</span><strong>{primaryRecommendation ?? "Ikke vurdert"}</strong><small>{primaryReason ?? "Ingen begrunnelse tilgjengelig"}{modelContext ? ` · ${modelContext}` : ""}</small></div><div className="total-score"><strong>{formatNumber(detail.score, 0)}</strong><small>total score</small></div>{[["Teknisk", detail.technical_score], ["Fundamentalt", detail.fundamental_score], ["Historikk", detail.history_score]].map(([label, value]) => <div className="subscore" key={String(label)}><span>{label}</span><strong>{formatNumber(value as number | null, 0)}</strong><i><b style={{ width: `${Math.max(0, Math.min(100, Number(value) || 0))}%` }} /></i></div>)}</section>}
    <section className="chart-card"><div className="chart-toolbar"><PeriodSelector period={period} onChange={setPeriod} /><div className="indicators"><label><input type="checkbox" checked={showVolume} onChange={(e) => setShowVolume(e.target.checked)} /> Volum</label><label><input type="checkbox" checked={showSma20} onChange={(e) => setShowSma20(e.target.checked)} /> SMA20</label><label><input type="checkbox" checked={showSma50} onChange={(e) => setShowSma50(e.target.checked)} /> SMA50</label></div></div>{loading && <div className="chart-placeholder">Henter kursdata…</div>}{error && <div className="error" role="alert">{error}</div>}{!loading && !error && detail && <PriceChart candles={detail.candles} showVolume={showVolume} showSma20={showSma20} showSma50={showSma50} />}</section>
    {detail && <><div className="detail-grid"><section className="detail-panel"><div className="panel-title"><h2>Selskapsvurdering</h2><span>{detail.trend_regime ?? "Ukjent trend"}</span></div><ul>{detail.reasoning.slice(0, 5).map((reason) => <li key={reason}>{reason}</li>)}{!detail.reasoning.length && <li>Ingen detaljert vurdering tilgjengelig.</li>}</ul></section><section className="detail-panel"><div className="panel-title"><h2>Fundamentalt</h2><span>{detail.fundamental_label ?? "Ikke vurdert"}</span></div><ul>{detail.fundamental_reasons.slice(0, 4).map((reason) => <li key={reason}>{reason}</li>)}</ul><div className="analyst-row"><span>Analytikere</span><strong>{detail.analyst_consensus?.replaceAll("_", " ") ?? "–"}</strong><span>{detail.analyst_count ?? 0} dekker · kursmål {formatNumber(detail.target_mean)} · {formatNumber(detail.upside_pct)} % oppside</span></div></section></div><section className="detail-panel news-panel"><div className="panel-title"><h2>Nyheter og hendelser</h2><span>Beslutningsrelevante oppdateringer</span></div>{event && <div className="event-row"><span className="event-icon">◷</span><div><strong>Neste hendelse</strong><small>{String(event.event_label ?? event.event_type ?? event.earnings_date ?? "Kommende rapport")}</small></div></div>}{detail.news.length ? detail.news.map((item, index) => <a className="news-row" key={`${item.url}-${index}`} href={item.url} target="_blank" rel="noreferrer"><span><strong>{item.headline ?? "Nyhet"}</strong><small>{item.publisher ?? "Ukjent kilde"} · {item.published_at ? new Date(item.published_at).toLocaleDateString("nb-NO") : ""}</small></span><b>{item.sentiment ?? ""}</b></a>) : <div className="list-empty">Ingen relevante nyheter i siste snapshot.</div>}</section></>}
  </>;
}

export default function App() {
  type View = "today" | "detail" | "explore" | "admin" | "model";
  const viewFromPath = (): View => window.location.pathname === "/admin" ? "admin" : window.location.pathname === "/explore" ? "explore" : window.location.pathname === "/model-data" ? "model" : tickerFromPath(window.location.pathname) ? "detail" : "today";
  const [view, setView] = useState<View>(viewFromPath);
  const [ticker, setTicker] = useState(() => tickerFromPath(window.location.pathname)); const [period, setPeriod] = useState<Period>(currentPeriod); const [today, setToday] = useState<TodayResponse | null>(null); const [admin, setAdmin] = useState<AdminState | null>(null); const [explore, setExplore] = useState<ExploreResponse | null>(null); const [modelData, setModelData] = useState<ModelDataResponse | null>(null); const [chatOpen, setChatOpen] = useState(false); const [editor, setEditor] = useState<{ ticker: string; companyName: string } | null>(null); const [detail, setDetail] = useState<CompanyDetail | null>(null); const [loading, setLoading] = useState(false); const [error, setError] = useState<string | null>(null);
  const detailRequest = useRef(0);
  const routeKey = useMemo(() => `${ticker ?? "today"}:${period}`, [ticker, period]);
  const refreshReadData = async () => {
    const [nextToday, nextAdmin, nextExplore, nextModelData] = await Promise.all([fetchToday(), fetchAdmin(), fetchExplore(), fetchModelData()]);
    setToday(nextToday);
    setAdmin(nextAdmin);
    setExplore(nextExplore);
    setModelData(nextModelData);
  };
  useEffect(() => { const controller = new AbortController(); Promise.all([fetchToday(controller.signal), fetchAdmin(controller.signal), fetchExplore(controller.signal), fetchModelData(controller.signal)]).then(([nextToday, nextAdmin, nextExplore, nextModelData]) => { setToday(nextToday); setAdmin(nextAdmin); setExplore(nextExplore); setModelData(nextModelData); }).catch((reason) => { if (!controller.signal.aborted) setError(reason.message); }); return () => controller.abort(); }, []);
  useEffect(() => { const onPop = () => { setTicker(tickerFromPath(window.location.pathname)); setView(viewFromPath()); setPeriod(currentPeriod()); }; window.addEventListener("popstate", onPop); return () => window.removeEventListener("popstate", onPop); }, []);
  useEffect(() => { if (!ticker) { setDetail(null); return; } const request = ++detailRequest.current; const controller = new AbortController(); setLoading(true); setError(null); fetchCompanyDetail(ticker, period, controller.signal).then((data) => { if (request === detailRequest.current) { setDetail(data); setError(null); } }).catch((reason) => { if (request === detailRequest.current && !controller.signal.aborted) setError(reason.message); }).finally(() => { if (request === detailRequest.current) setLoading(false); }); return () => controller.abort(); }, [routeKey, ticker, period]);
  const navigate = (nextTicker: string | null, nextPeriod: Period = period, replace = false) => { const path = nextTicker ? `${stockPath(nextTicker)}?${new URLSearchParams({ period: nextPeriod })}` : "/"; window.history[replace ? "replaceState" : "pushState"]({}, "", path); setTicker(nextTicker?.toUpperCase() ?? null); setView(nextTicker ? "detail" : "today"); setPeriod(nextPeriod); window.scrollTo({ top: 0 }); };
  const navigateAdmin = () => { window.history.pushState({}, "", "/admin"); setTicker(null); setView("admin"); window.scrollTo({ top: 0 }); };
  const navigatePage = (nextView: "explore" | "model") => { window.history.pushState({}, "", nextView === "explore" ? "/explore" : "/model-data"); setTicker(null); setView(nextView); window.scrollTo({ top: 0 }); };
  const choosePeriod = (next: Period) => { if (ticker) navigate(ticker, next, true); else setPeriod(next); };
  const openEditor = (value: string, companyName?: string) => setEditor({ ticker: value.toUpperCase(), companyName: companyName ?? value.toUpperCase() });
  const saved = async (_result: StockMutation) => { await refreshReadData(); };
  const readError = error && view !== "detail" && ((view === "today" && !today) || (view === "admin" && !admin) || (view === "explore" && !explore) || (view === "model" && !modelData));
  const page = readError ? <section className="error-page" role="alert"><span>!</span><h1>Dataene kunne ikke lastes</h1><p>{error}</p><button onClick={() => window.location.reload()}>Prøv igjen</button></section> : view === "admin" ? <AdminPage admin={admin} onEdit={openEditor} /> : view === "explore" ? <ExplorePage data={explore} onOpen={(value) => navigate(value)} onEdit={openEditor} /> : view === "model" ? <ModelDataPage data={modelData} /> : view === "detail" && ticker ? <DetailPage ticker={ticker} period={period} setPeriod={choosePeriod} detail={detail} loading={loading} error={error} onEdit={openEditor} /> : <TodayPage data={today} period={period} setPeriod={choosePeriod} onOpen={(value) => navigate(value)} onEdit={openEditor} />;
  return <div className="app-shell"><header className="topbar"><button className="brand" onClick={() => navigate(null)} aria-label="Stock Agent startside"><span className="brand-mark">SA</span><span>Stock Agent</span></button><nav><button className={view === "today" ? "active" : ""} onClick={() => navigate(null)}>I dag</button><button className={view === "explore" ? "active" : ""} onClick={() => navigatePage("explore")}>Utforsk</button><button className={view === "admin" ? "active" : ""} onClick={navigateAdmin}>Administrer</button><button className={view === "model" ? "active" : ""} onClick={() => navigatePage("model")}>Modell og data</button></nav><SearchBox onOpen={(value) => navigate(value)} onEdit={openEditor} /><button className="agent-button" onClick={() => setChatOpen(true)}>✦ Spør agenten</button><span className="environment">{today?.meta.environment.toUpperCase() ?? "…"}</span></header><main>{page}</main>{chatOpen && <ChatPanel context={{ view, ticker, companyName: detail?.company_name }} onClose={() => setChatOpen(false)} />}{editor && admin && <StockEditor ticker={editor.ticker} companyName={editor.companyName} admin={admin} onClose={() => setEditor(null)} onSaved={saved} />}</div>;
}
