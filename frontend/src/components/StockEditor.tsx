import { FormEvent, useEffect, useState } from "react";

import { updateStock } from "../api";
import type { AdminState, StockMutation } from "../types";

type Props = {
  ticker: string;
  companyName: string;
  admin: AdminState;
  onClose: () => void;
  onSaved: (result: StockMutation) => Promise<void>;
};

export function StockEditor({ ticker, companyName, admin, onClose, onSaved }: Props) {
  const position = admin.positions.find((item) => item.ticker === ticker);
  const editableLists = admin.watchlists.filter((item) => item.editable);
  const currentLists = editableLists
    .filter((item) => item.tickers.includes(ticker))
    .map((item) => item.name);
  const [owned, setOwned] = useState(Boolean(position));
  const [averageCost, setAverageCost] = useState(position?.average_cost?.toString() ?? "");
  const [watchlists, setWatchlists] = useState<string[]>(currentLists);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState<StockMutation | null>(null);

  useEffect(() => {
    const close = (event: KeyboardEvent) => { if (event.key === "Escape") onClose(); };
    window.addEventListener("keydown", close);
    return () => window.removeEventListener("keydown", close);
  }, [onClose]);

  const toggleList = (name: string) => {
    setWatchlists((current) => current.includes(name)
      ? current.filter((item) => item !== name)
      : [...current, name]);
  };

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    const parsedCost = averageCost.trim() ? Number(averageCost.replace(",", ".")) : null;
    if (owned && (!parsedCost || parsedCost <= 0)) {
      setError("Oppgi en gyldig GAV større enn 0.");
      return;
    }
    setSaving(true);
    setError(null);
    try {
      const result = await updateStock(ticker, {
        owned,
        average_cost: owned ? parsedCost : null,
        watchlists,
      });
      await onSaved(result);
      setSaved(result);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Kunne ikke lagre endringene");
    } finally {
      setSaving(false);
    }
  };

  return <div className="modal-backdrop" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) onClose(); }}>
    <section className="stock-editor" role="dialog" aria-modal="true" aria-labelledby="stock-editor-title">
      <div className="editor-heading"><div><span className="eyebrow">Administrer aksje</span><h2 id="stock-editor-title">{ticker}</h2><p>{companyName}</p></div><button type="button" className="close-button" onClick={onClose} aria-label="Lukk">×</button></div>
      {saved ? <div className="save-success" role="status"><span>✓</span><h3>Endringene er lagret</h3><p>TEST-backup: <code>{saved.backup_id}</code></p><button type="button" onClick={onClose}>Ferdig</button></div> : <form onSubmit={submit}>
        {!admin.writable && <div className="write-warning">Skriving er bare aktivert i TEST.</div>}
        <label className="owned-toggle"><input type="checkbox" checked={owned} onChange={(event) => setOwned(event.target.checked)} /><span><strong>Jeg eier aksjen</strong><small>Aktiverer risiko, stop-loss og gevinstsikring.</small></span></label>
        <label className={`field ${!owned ? "disabled" : ""}`}><span>GAV</span><input inputMode="decimal" value={averageCost} disabled={!owned} onChange={(event) => setAverageCost(event.target.value)} placeholder="Gjennomsnittlig anskaffelsesverdi" /><small>Ingen total porteføljeverdi vises.</small></label>
        <fieldset><legend>Watchlists</legend>{editableLists.map((list) => <label key={list.name}><input type="checkbox" checked={watchlists.includes(list.name)} onChange={() => toggleList(list.name)} /><span>{list.name}</span></label>)}</fieldset>
        {error && <div className="editor-error" role="alert">{error}</div>}
        <div className="editor-actions"><button type="button" onClick={onClose}>Avbryt</button><button className="primary" type="submit" disabled={saving || !admin.writable}>{saving ? "Lagrer…" : "Lagre endringer"}</button></div>
      </form>}
    </section>
  </div>;
}
