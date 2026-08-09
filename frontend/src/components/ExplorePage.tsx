import { useState } from "react";

import type { ExploreResponse, StockSummary } from "../types";

type Props = { data: ExploreResponse | null; onOpen: (ticker: string) => void; onEdit: (ticker: string, name?: string) => void };

function value(number: number | null, digits = 0) {
  return number == null ? "–" : number.toLocaleString("nb-NO", { maximumFractionDigits: digits });
}

function ExploreRow({ stock, rank, onOpen }: { stock: StockSummary; rank: number; onOpen: (ticker: string) => void }) {
  return <button className="explore-row" onClick={() => onOpen(stock.ticker)}><span className="explore-rank">{rank}</span><span><strong>{stock.ticker}</strong><small>{stock.company_name}</small></span><span><strong>{stock.recommendation ?? "Ikke vurdert"}</strong><small>{stock.rationale ?? stock.trend_regime ?? ""}</small></span><span className={stock.relative_strength_pct != null && stock.relative_strength_pct >= 0 ? "positive" : "negative"}>{stock.relative_strength_pct == null ? "–" : `${stock.relative_strength_pct > 0 ? "+" : ""}${value(stock.relative_strength_pct, 2)} %`}</span><span className="explore-score">{value(stock.score)}</span><span>→</span></button>;
}

export function ExplorePage({ data, onOpen, onEdit }: Props) {
  const [profile, setProfile] = useState("ALL");
  if (!data) return <div className="page-loading">Henter Utforsk…</div>;
  const active = data.profiles.find((item) => item.key === profile);
  const stocks = active ? active.stocks : data.watchlist_ranking;
  return <><div className="page-heading"><div><span className="eyebrow">Screening og rangering</span><h1>Utforsk</h1><p>Finn hvilke aksjer som fortjener nærmere analyse. Råd og score kommer fra eksisterende modell.</p></div><span className={`data-status ${data.meta.status}`}>{data.meta.message ?? `${data.watchlist_ranking.length} vurderte aksjer`}</span></div>
    <section className="explore-section screening-section"><div className="section-heading"><div><h2>Nye kandidater fra screening</h2><span className="count">{data.candidates.length}</span></div><small>{data.candidate_source.label ?? "Siste screening"}{data.candidate_source.date ? ` · ${data.candidate_source.date}` : ""} · ikke i watchlist</small></div>{data.candidates.length ? <div className="explore-candidates">{data.candidates.slice(0, 3).map((stock, index) => <article key={stock.ticker}><span className="rank">#{index + 1}</span><div><button onClick={() => onOpen(stock.ticker)}><strong>{stock.ticker}</strong><small>{stock.company_name}</small></button><strong className="candidate-big-score">{value(stock.score)}</strong></div><p>{stock.trend_regime ?? stock.rationale ?? "Analyse tilgjengelig i selskapsdetaljer"}</p><div><button className="text-link" onClick={() => onOpen(stock.ticker)}>Se analyse →</button><button className="manage-button" onClick={() => onEdit(stock.ticker, stock.company_name)}>+ Watchlist</button></div></article>)}</div> : <div className="explore-empty"><strong>Ingen aksjer kvalifiserte i siste screening</strong><p>Utforsk viser ikke kandidater bare for å fylle flaten.</p></div>}</section>
    <section className="explore-section"><div className="section-heading"><div><h2>Rangering av watchlist</h2><span className="count">{stocks.length}</span></div><small>Filtrer eksisterende watchlist etter strategiprofil</small></div><div className="profile-tabs" aria-label="Filtrer strategiprofil"><button className={profile === "ALL" ? "active" : ""} onClick={() => setProfile("ALL")}>Alle <span>{data.watchlist_ranking.length}</span></button>{data.profiles.map((item) => <button key={item.key} className={profile === item.key ? "active" : ""} onClick={() => setProfile(item.key)}>{item.label} <span>{item.count}</span></button>)}</div><div className="explore-table"><div className="explore-labels"><span>#</span><span>Aksje</span><span>Agent</span><span>Relativ styrke</span><span>Score</span><span /></div>{stocks.map((stock, index) => <ExploreRow key={stock.ticker} stock={stock} rank={index + 1} onOpen={onOpen} />)}{!stocks.length && <div className="list-empty">Ingen aksjer i denne profilen.</div>}</div></section>
  </>;
}
