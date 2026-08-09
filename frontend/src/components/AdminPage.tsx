import type { AdminState, Position } from "../types";

type Props = {
  admin: AdminState | null;
  onEdit: (ticker: string, companyName?: string) => void;
};

function number(value: number | null) {
  return value == null ? "–" : value.toLocaleString("nb-NO", { maximumFractionDigits: 2 });
}

export function AdminPage({ admin, onEdit }: Props) {
  if (!admin) return <div className="page-loading">Henter administrasjonsdata…</div>;
  const editable = admin.watchlists.filter((list) => list.editable);
  return <><div className="page-heading admin-heading"><div><span className="eyebrow">Portefølje og lister</span><h1>Administrer</h1><p>Vedlikehold eid-status, GAV og watchlists. Ingen totalverdi beregnes eller vises.</p></div><span className={`write-mode ${admin.writable ? "enabled" : "disabled"}`}>{admin.writable ? "TEST · skriving aktiv" : "Kun lesing"}</span></div>
    <section className="admin-section"><div className="section-heading"><div><h2>Eide aksjer</h2><span className="count">{admin.positions.length}</span></div><small>GAV brukes av eksisterende risiko- og exitlogikk</small></div><div className="admin-position-list">{admin.positions.map((position: Position) => <article key={position.ticker}><div><strong>{position.ticker}</strong><small>{position.company_name}</small></div><div><small>GAV</small><strong>{number(position.average_cost)}</strong></div><div><small>Agent</small><strong>{position.portfolio_action ?? position.recommendation ?? "–"}</strong></div><div><small>Stop-loss</small><strong>{number(position.stop_loss)}</strong></div><button onClick={() => onEdit(position.ticker, position.company_name)}>Rediger</button></article>)}{!admin.positions.length && <div className="list-empty">Ingen eide aksjer.</div>}</div></section>
    <section className="admin-section"><div className="section-heading"><div><h2>Watchlists</h2><span className="count">{editable.length}</span></div><small>«Alle» oppdateres automatisk</small></div><div className="watchlist-admin-grid">{editable.map((list) => <article key={list.name}><div><h3>{list.name}</h3><span>{list.tickers.length} aksjer</span></div><div className="ticker-chips">{list.tickers.map((ticker) => <button key={ticker} onClick={() => onEdit(ticker)}>{ticker}</button>)}</div></article>)}</div></section>
  </>;
}
