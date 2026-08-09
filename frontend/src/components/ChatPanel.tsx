import { FormEvent, useState } from "react";

import { askChat } from "../api";

type Message = { role: "user" | "agent"; text: string };
type ChatContext = { view: string; ticker?: string | null; companyName?: string | null };
type Props = { onClose: () => void; context: ChatContext };

const GENERAL_PROMPTS = ["Hva bør jeg følge med på i dag?", "Ranger watchlist", "Svakeste posisjoner", "Hvem rapporterer snart?"];

export function ChatPanel({ onClose, context }: Props) {
  const [question, setQuestion] = useState("");
  const [messages, setMessages] = useState<Message[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const send = async (value: string) => {
    const trimmed = value.trim();
    if (!trimmed || loading) return;
    setMessages((current) => [...current, { role: "user", text: trimmed }]);
    setQuestion(""); setLoading(true); setError(null);
    try {
      const response = await askChat(trimmed, context);
      setMessages((current) => [...current, { role: "agent", text: response.answer }]);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Agenten kunne ikke svare");
    } finally { setLoading(false); }
  };
  const submit = (event: FormEvent) => { event.preventDefault(); void send(question); };
  const prompts = context.ticker ? [`Bør jeg holde ${context.ticker}?`, `Hva sier analytikerne om ${context.ticker}?`, `Hva er kursmålet på ${context.ticker}?`, "Hva bør jeg følge med på før earnings?"] : GENERAL_PROMPTS;
  const contextLabel = context.ticker ? `${context.ticker} · ${context.companyName ?? "Selskapsdetaljer"}` : context.view === "explore" ? "Utforsk" : context.view === "model" ? "Modell og data" : context.view === "admin" ? "Administrer" : "I dag";
  return <div className="chat-backdrop"><aside className="chat-panel" aria-label="Spør agenten"><header><div><span className="eyebrow">Kontekst: {contextLabel}</span><h2>Spør agenten</h2></div><button onClick={onClose} aria-label="Lukk chat">×</button></header><div className="chat-content">{!messages.length && <div className="chat-intro"><span>✦</span><h3>Hva vil du forstå?</h3><p>Agenten forklarer det du ser i aktiv flate. Du kan fortsatt lese og bruke innholdet bak panelet.</p><div>{prompts.map((prompt) => <button key={prompt} onClick={() => void send(prompt)}>{prompt}</button>)}</div></div>}{messages.map((message, index) => <article className={`chat-message ${message.role}`} key={index}><span>{message.role === "agent" ? "Agent" : "Du"}</span><p>{message.text}</p></article>)}{loading && <div className="chat-typing">Agenten undersøker snapshotet…</div>}{error && <div className="editor-error" role="alert">{error}</div>}</div><form onSubmit={submit}><label className="sr-only" htmlFor="chat-question">Spør agenten</label><textarea id="chat-question" value={question} onChange={(event) => setQuestion(event.target.value)} placeholder={context.ticker ? `Spør om ${context.ticker}…` : "Still et spørsmål om aksjene eller rådene…"} /><button type="submit" disabled={loading || !question.trim()}>Send</button></form></aside></div>;
}
