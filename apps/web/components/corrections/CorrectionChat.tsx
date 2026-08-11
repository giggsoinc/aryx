"use client";

import { useState } from "react";
import { Check, Loader2, MessageSquarePlus, Send, X } from "lucide-react";
import { api } from "@/lib/api";
import { cn } from "@/lib/cn";

type Action = {
  kind: "retype" | "remove" | "link" | "unlink" | "merge" | "rename_type";
  entity_id?: number; target_id?: number; name?: string; type_name?: string;
};

interface Turn {
  role: "user" | "aryx";
  text: string;
  status?: string;
  action?: Action;      // proposal awaiting Apply
  resolved?: boolean;   // proposal already applied/dismissed
}

/** Graph-editing chat drawer — WRITE-ONLY, entirely separate from Ask.
 *  The bot NEVER applies straight from parsing: it proposes ("Rename type
 *  X → Y. Apply?") and only your Apply click executes — a misread costs a
 *  click, never a wrong edit. Applied corrections fire `aryx:corrected`. */
export function CorrectionChat({ workspaceId, scope }: {
  workspaceId: number;
  scope: "data" | "model";
}) {
  const [open, setOpen] = useState(false);
  const [turns, setTurns] = useState<Turn[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);

  const push = (t: Turn) => setTurns((prev) => [...prev, t]);

  const send = async () => {
    const text = input.trim();
    if (!text || busy) return;
    setInput("");
    push({ role: "user", text });
    setBusy(true);
    try {
      const res = await api.correctionChat(workspaceId, text);
      push({ role: "aryx", text: res.message, status: res.status,
             action: res.action });
    } catch (e) {
      push({ role: "aryx", status: "error",
             text: e instanceof Error ? e.message : "failed" });
    } finally {
      setBusy(false);
    }
  };

  const apply = async (i: number, action: Action) => {
    setBusy(true);
    try {
      await api.addCorrection(workspaceId, action as Parameters<typeof api.addCorrection>[1]);
      setTurns((prev) => prev.map((t, j) => (j === i ? { ...t, resolved: true } : t)));
      push({ role: "aryx", status: "applied",
             text: "Applied ✓ — and saved as a standing rule for every future ingest." });
      window.dispatchEvent(new CustomEvent("aryx:corrected"));
    } catch (e) {
      push({ role: "aryx", status: "error",
             text: e instanceof Error ? e.message : "apply failed" });
    } finally {
      setBusy(false);
    }
  };

  const dismiss = (i: number) => {
    setTurns((prev) => prev.map((t, j) => (j === i ? { ...t, resolved: true } : t)));
    push({ role: "aryx", text: "Okay, not applied. Rephrase it and I'll try again." });
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
    <aside className="fixed right-0 top-16 z-40 flex h-[calc(100vh-4rem)] w-[420px] flex-col border-l border-navy-100 bg-white shadow-xl">
      <div className="flex items-center justify-between border-b border-navy-100 bg-navy-50/60 px-4 py-2.5">
        <span className="text-[11px] font-bold uppercase tracking-wide text-navy-700">
          Fix by chat — edits the {scope === "model" ? "ontology" : "graph"}
        </span>
        <button onClick={() => setOpen(false)} className="focus-ring rounded p-0.5 text-subtle hover:bg-navy-100">
          <X size={14} />
        </button>
      </div>
      <p className="border-b border-navy-100 px-4 py-2 text-[11px] leading-snug text-subtle">
        I propose, you approve — nothing changes until you click Apply.
        Questions belong on Ask. Try: “rename type AI Security Governance to
        GREaaS” · “merge M. Lopez into Maria Lopez” · “T-100 was resolved by
        Maria” · “remove that REVENUE WORKFLOW junk”.
      </p>
      <div className="flex-1 space-y-2 overflow-y-auto px-4 py-3">
        {turns.length === 0 && (
          <p className="text-[12px] text-subtle">
            Tell me what's wrong in the {scope === "model" ? "ontology" : "graph"}…
          </p>
        )}
        {turns.map((t, i) => (
          <div key={i}>
            <div className={cn(
              "max-w-[92%] rounded-lg px-3 py-2 text-[12.5px] leading-snug",
              t.role === "user"
                ? "ml-auto bg-navy-800 text-white"
                : t.status === "applied"
                ? "bg-emerald-50 text-emerald-800"
                : t.status === "error"
                ? "bg-rose-50 text-rose-700"
                : t.status === "proposal"
                ? "border border-steel-500/40 bg-steel-500/5 text-navy-800"
                : "bg-navy-50 text-navy-800",
            )}>
              {t.text}
              {t.status === "proposal" && t.action && !t.resolved && (
                <div className="mt-2 flex gap-2">
                  <button
                    type="button" disabled={busy}
                    onClick={() => apply(i, t.action!)}
                    className="focus-ring inline-flex items-center gap-1 rounded-lg bg-navy-800 px-3 py-1 text-[11.5px] font-semibold text-white hover:bg-navy-700 disabled:opacity-50"
                  >
                    <Check size={11} /> Apply
                  </button>
                  <button
                    type="button" disabled={busy}
                    onClick={() => dismiss(i)}
                    className="focus-ring rounded-lg border border-navy-100 bg-white px-3 py-1 text-[11.5px] font-medium text-navy-700 hover:bg-navy-50"
                  >
                    No, rephrase
                  </button>
                </div>
              )}
            </div>
          </div>
        ))}
        {busy && (
          <div className="flex items-center gap-1.5 text-[11px] text-subtle">
            <Loader2 size={11} className="animate-spin" /> working…
          </div>
        )}
      </div>
      <div className="flex items-center gap-1.5 border-t border-navy-100 p-3">
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && send()}
          placeholder="Tell Aryx what to fix…"
          className="focus-ring flex-1 rounded-lg border border-navy-100 bg-white px-3 py-2 text-[12.5px] text-navy-800"
        />
        <button
          type="button" onClick={send} disabled={busy || !input.trim()}
          className="focus-ring rounded-lg bg-navy-800 p-2.5 text-white hover:bg-navy-700 disabled:opacity-50"
        >
          <Send size={14} />
        </button>
      </div>
    </aside>
  );
}
