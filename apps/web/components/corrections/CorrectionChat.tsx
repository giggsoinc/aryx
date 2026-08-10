"use client";

import { useState } from "react";
import { Loader2, MessageSquarePlus, Send, X } from "lucide-react";
import { api } from "@/lib/api";
import { cn } from "@/lib/cn";

interface Turn { role: "user" | "aryx"; text: string; status?: string }

/** Graph-editing chat dock — WRITE-ONLY, entirely separate from Ask.
 *  Utterances are parsed into corrections and applied through the same
 *  audited path as the buttons; questions are redirected to Ask.
 *  After an applied correction, fires the `aryx:corrected` DOM event so
 *  graph/ontology views reload without coupling. */
export function CorrectionChat({ workspaceId, scope }: {
  workspaceId: number;
  /** "data" (entity fixes) or "model" (shown label only — same endpoint). */
  scope: "data" | "model";
}) {
  const [open, setOpen] = useState(false);
  const [turns, setTurns] = useState<Turn[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);

  const send = async () => {
    const text = input.trim();
    if (!text || busy) return;
    setInput("");
    setTurns((t) => [...t, { role: "user", text }]);
    setBusy(true);
    try {
      const res = await api.correctionChat(workspaceId, text);
      setTurns((t) => [...t, { role: "aryx", text: res.message, status: res.status }]);
      if (res.status === "applied") {
        window.dispatchEvent(new CustomEvent("aryx:corrected"));
      }
    } catch (e) {
      setTurns((t) => [...t, {
        role: "aryx", status: "error",
        text: e instanceof Error ? e.message : "correction failed",
      }]);
    } finally {
      setBusy(false);
    }
  };

  if (!open) {
    return (
      <button
        type="button"
        onClick={() => setOpen(true)}
        className="focus-ring fixed bottom-5 right-5 z-40 inline-flex items-center gap-2 rounded-full bg-navy-800 px-4 py-2.5 text-[12px] font-semibold text-white shadow-lg hover:bg-navy-700"
      >
        <MessageSquarePlus size={14} /> Fix by chat
      </button>
    );
  }

  return (
    <div className="fixed bottom-5 right-5 z-40 flex max-h-[70vh] w-[340px] flex-col overflow-hidden rounded-xl border border-navy-100 bg-white shadow-xl">
      <div className="flex items-center justify-between border-b border-navy-100 bg-navy-50/60 px-3 py-2">
        <span className="text-[11px] font-bold uppercase tracking-wide text-navy-700">
          Fix by chat — edits the {scope === "model" ? "ontology" : "graph"}
        </span>
        <button onClick={() => setOpen(false)} className="focus-ring rounded p-0.5 text-subtle hover:bg-navy-100">
          <X size={13} />
        </button>
      </div>
      <p className="border-b border-navy-100 px-3 py-1.5 text-[10.5px] leading-snug text-subtle">
        This changes data and saves standing rules. It does not answer
        questions — that's Ask. Try: “merge M. Lopez into Maria Lopez” ·
        “T-100 was resolved by Maria” · “remove that REVENUE WORKFLOW junk”.
      </p>
      <div className="flex-1 space-y-2 overflow-y-auto px-3 py-2">
        {turns.map((t, i) => (
          <div key={i} className={cn(
            "max-w-[92%] rounded-lg px-2.5 py-1.5 text-[12px] leading-snug",
            t.role === "user"
              ? "ml-auto bg-navy-800 text-white"
              : t.status === "applied"
              ? "bg-emerald-50 text-emerald-800"
              : t.status === "error"
              ? "bg-rose-50 text-rose-700"
              : "bg-navy-50 text-navy-800",
          )}>
            {t.text}
          </div>
        ))}
        {busy && (
          <div className="flex items-center gap-1.5 text-[11px] text-subtle">
            <Loader2 size={11} className="animate-spin" /> applying…
          </div>
        )}
      </div>
      <div className="flex items-center gap-1.5 border-t border-navy-100 p-2">
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && send()}
          placeholder="Tell Aryx what to fix…"
          className="focus-ring flex-1 rounded-lg border border-navy-100 bg-white px-2.5 py-1.5 text-[12px] text-navy-800"
        />
        <button
          type="button" onClick={send} disabled={busy || !input.trim()}
          className="focus-ring rounded-lg bg-navy-800 p-2 text-white hover:bg-navy-700 disabled:opacity-50"
        >
          <Send size={13} />
        </button>
      </div>
    </div>
  );
}
