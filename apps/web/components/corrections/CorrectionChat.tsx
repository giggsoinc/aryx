"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import {
  Check, Loader2, MessageSquarePlus, Send, X, Trash2,
} from "lucide-react";
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
  action?: Action;
  resolved?: boolean;
  choices?: string[];
}

type Intent =
  | "retype" | "merge" | "link" | "unlink" | "remove" | "rename_type";

const INTENTS: { id: Intent; label: string; hint: string; template: string }[] = [
  { id: "retype", label: "Wrong type", hint: "Retype an entity",
    template: "Retype {name} as " },
  { id: "merge", label: "Merge duplicates", hint: "Same real-world thing",
    template: "Merge {name} into " },
  { id: "link", label: "Link", hint: "Relate two entities",
    template: "Link {name} to " },
  { id: "unlink", label: "Unlink", hint: "Remove a relationship",
    template: "Unlink {name} and " },
  { id: "remove", label: "Remove junk", hint: "Drop a bad entity",
    template: "Remove {name}" },
  { id: "rename_type", label: "Rename type", hint: "Rename an ontology type",
    template: "Rename type {name} to " },
];

/** Graph-editing coach — WRITE-ONLY, separate from Ask.
 *  Proposes only; Apply required. Wires selected_entity_id when set. */
export function CorrectionChat({ workspaceId, scope }: {
  workspaceId: number;
  scope: "data" | "model";
}) {
  const [open, setOpen] = useState(false);
  const [tab, setTab] = useState<"coach" | "rules">("coach");
  const [turns, setTurns] = useState<Turn[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [selected, setSelected] = useState<{
    id: number; name: string; type?: string;
  } | null>(null);
  const [examples, setExamples] = useState<string[]>([]);
  const [entityCount, setEntityCount] = useState<number | null>(null);
  const [rules, setRules] = useState<Array<{
    id: number; kind: string; subject: string; object: string; created_at: string;
  }>>([]);
  const [rulesLoading, setRulesLoading] = useState(false);

  // Selection from Data lenses (table/tree/graph) via custom event.
  useEffect(() => {
    const onSel = (ev: Event) => {
      const d = (ev as CustomEvent).detail as {
        id?: number; name?: string; type?: string;
      } | null;
      if (d?.id != null && d.name) {
        setSelected({ id: d.id, name: d.name, type: d.type });
      }
    };
    window.addEventListener("aryx:select-entity", onSel);
    return () => window.removeEventListener("aryx:select-entity", onSel);
  }, []);

  useEffect(() => {
    if (!open) return;
    let live = true;
    api.dataSummary(workspaceId).then((s) => {
      if (!live || "error" in s) return;
      setEntityCount(s.total_entities ?? 0);
      const top = s.types?.[0]?.name;
      if ((s.total_entities ?? 0) > 0 && top) {
        api.dataEntities(workspaceId, top, 3, 0).then((page) => {
          if (!live) return;
          const names = (page.items || []).map((e) => e.name).filter(Boolean);
          setExamples(names.slice(0, 3).map((n) => `Retype “${n}” as `));
        }).catch(() => {});
      } else {
        setExamples([]);
      }
    }).catch(() => setEntityCount(null));
    return () => { live = false; };
  }, [open, workspaceId]);

  const loadRules = useCallback(async () => {
    setRulesLoading(true);
    try {
      setRules(await api.listCorrections(workspaceId));
    } catch {
      setRules([]);
    } finally {
      setRulesLoading(false);
    }
  }, [workspaceId]);

  useEffect(() => {
    if (open && tab === "rules") void loadRules();
  }, [open, tab, loadRules]);

  const push = (t: Turn) => setTurns((prev) => [...prev, t]);

  const sendText = async (text: string) => {
    const q = text.trim();
    if (!q || busy) return;
    setInput("");
    push({ role: "user", text: q });
    setBusy(true);
    try {
      const res = await api.correctionChat(
        workspaceId, q, selected?.id ?? 0,
      );
      const status = res.status || "";
      const choices = status === "ambiguous"
        ? (res.message.match(/(?:Which one\?\s*)?(.+)/)?.[1] || "")
            .split("·").map((s) => s.trim()).filter(Boolean)
        : undefined;
      push({
        role: "aryx",
        text: res.message,
        status,
        action: res.action,
        choices: choices && choices.length > 1 ? choices : undefined,
      });
    } catch (e) {
      push({
        role: "aryx", status: "error",
        text: e instanceof Error ? e.message : "failed",
      });
    } finally {
      setBusy(false);
    }
  };

  const send = () => void sendText(input);

  const apply = async (i: number, action: Action) => {
    setBusy(true);
    try {
      await api.addCorrection(workspaceId, action as Parameters<typeof api.addCorrection>[1]);
      setTurns((prev) => prev.map((t, j) => (j === i ? { ...t, resolved: true } : t)));
      push({
        role: "aryx", status: "applied",
        text: "Applied ✓ — saved as a standing rule for every future ingest.",
      });
      window.dispatchEvent(new CustomEvent("aryx:corrected"));
      if (tab === "rules") void loadRules();
    } catch (e) {
      push({
        role: "aryx", status: "error",
        text: e instanceof Error ? e.message : "apply failed",
      });
    } finally {
      setBusy(false);
    }
  };

  const dismiss = (i: number) => {
    setTurns((prev) => prev.map((t, j) => (j === i ? { ...t, resolved: true } : t)));
    push({ role: "aryx", text: "Okay, not applied. Pick an intent below or rephrase." });
  };

  const applyIntent = (id: Intent) => {
    const t = INTENTS.find((x) => x.id === id)!;
    const name = selected?.name || "…";
    setInput(t.template.replace("{name}", name));
  };

  if (!open) {
    return (
      <button
        type="button"
        onClick={() => setOpen(true)}
        className="focus-ring fixed bottom-5 right-5 z-40 inline-flex items-center gap-2 rounded-full bg-navy-800 px-4 py-2.5 text-[12px] font-semibold text-white shadow-lg hover:bg-navy-700"
      >
        <MessageSquarePlus size={14} /> Correct data
      </button>
    );
  }

  const emptyGraph = entityCount === 0;

  return (
    <aside className="fixed right-0 top-16 z-40 flex h-[calc(100vh-4rem)] w-[420px] flex-col border-l border-navy-100 bg-white shadow-xl">
      <div className="border-b border-navy-100 bg-navy-50/60 px-4 py-2.5">
        <div className="flex items-center justify-between">
          <div>
            <div className="text-[12px] font-bold text-navy-800">
              Correct the {scope === "model" ? "ontology" : "graph"}
            </div>
            <div className="text-[10px] text-subtle">
              You approve every change · Questions →{" "}
              <Link href="/ask" className="underline">Ask</Link>
            </div>
          </div>
          <button onClick={() => setOpen(false)} className="focus-ring rounded p-0.5 text-subtle hover:bg-navy-100">
            <X size={14} />
          </button>
        </div>
        <div className="mt-2 flex gap-1">
          {(["coach", "rules"] as const).map((t) => (
            <button
              key={t}
              type="button"
              onClick={() => setTab(t)}
              className={cn(
                "rounded-md px-2.5 py-1 text-[11px] font-semibold",
                tab === t ? "bg-navy-800 text-white" : "bg-white text-navy-600 hover:bg-navy-50",
              )}
            >
              {t === "coach" ? "Coach" : "Standing rules"}
            </button>
          ))}
        </div>
      </div>

      {tab === "coach" && (
        <>
          <div className="border-b border-navy-100 px-4 py-2 text-[11px]">
            {selected ? (
              <div className="flex items-center justify-between gap-2">
                <span className="text-navy-800">
                  Selected: <b>{selected.name}</b>
                  {selected.type ? ` [${selected.type}]` : ""}
                </span>
                <button
                  type="button"
                  className="text-subtle underline"
                  onClick={() => setSelected(null)}
                >
                  Clear
                </button>
              </div>
            ) : (
              <span className="text-subtle">
                Tip: select a row in Data (table/tree/graph), then use an intent —
                or type a name.
              </span>
            )}
          </div>

          <div className="flex-1 space-y-2 overflow-y-auto px-4 py-3">
            {emptyGraph && (
              <div className="rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-[12px] text-amber-900">
                Nothing to correct yet — ingest data first via{" "}
                <Link href="/start" className="font-semibold underline">Setup</Link>.
              </div>
            )}

            {turns.length === 0 && !emptyGraph && (
              <div className="space-y-3">
                <p className="text-[12px] font-semibold text-navy-800">
                  What do you want to do?
                </p>
                <div className="grid grid-cols-2 gap-1.5">
                  {INTENTS.map((it) => (
                    <button
                      key={it.id}
                      type="button"
                      onClick={() => applyIntent(it.id)}
                      className="focus-ring rounded-lg border border-navy-100 bg-navy-50/80 px-2.5 py-2 text-left hover:border-steel-400"
                    >
                      <span className="block text-[11px] font-bold text-navy-800">{it.label}</span>
                      <span className="block text-[10px] text-subtle">{it.hint}</span>
                    </button>
                  ))}
                </div>
                {examples.length > 0 && (
                  <div>
                    <p className="mb-1 text-[10px] font-bold uppercase tracking-wide text-navy-500">
                      Try with your data
                    </p>
                    <div className="flex flex-wrap gap-1">
                      {examples.map((ex) => (
                        <button
                          key={ex}
                          type="button"
                          onClick={() => setInput(ex)}
                          className="focus-ring rounded-full border border-navy-100 bg-white px-2.5 py-1 text-[10px] text-navy-700 hover:bg-navy-50"
                        >
                          {ex}…
                        </button>
                      ))}
                    </div>
                  </div>
                )}
              </div>
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
                        No
                      </button>
                    </div>
                  )}
                  {t.choices && t.choices.length > 0 && (
                    <div className="mt-2 flex flex-wrap gap-1">
                      {t.choices.map((c) => (
                        <button
                          key={c}
                          type="button"
                          disabled={busy}
                          onClick={() => void sendText(c)}
                          className="focus-ring rounded-full border border-navy-200 bg-white px-2.5 py-1 text-[11px] font-medium text-navy-800 hover:bg-navy-50"
                        >
                          {c}
                        </button>
                      ))}
                    </div>
                  )}
                  {t.status === "none" && (
                    <div className="mt-2 text-[11px]">
                      <Link href="/ask" className="font-semibold underline">Open Ask</Link>
                      {" "}for questions.
                    </div>
                  )}
                  {t.status === "error" && (
                    <button
                      type="button"
                      className="mt-2 text-[11px] font-semibold underline"
                      onClick={() => void sendText(
                        [...turns].reverse().find((x) => x.role === "user")?.text || "",
                      )}
                    >
                      Retry
                    </button>
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
              placeholder={emptyGraph ? "Ingest data first…" : "Describe the fix…"}
              disabled={!!emptyGraph}
              className="focus-ring flex-1 rounded-lg border border-navy-100 bg-white px-3 py-2 text-[12.5px] text-navy-800 disabled:opacity-50"
            />
            <button
              type="button" onClick={send}
              disabled={busy || !input.trim() || !!emptyGraph}
              className="focus-ring rounded-lg bg-navy-800 p-2.5 text-white hover:bg-navy-700 disabled:opacity-50"
            >
              <Send size={14} />
            </button>
          </div>
        </>
      )}

      {tab === "rules" && (
        <div className="flex-1 overflow-y-auto px-4 py-3">
          {rulesLoading ? (
            <div className="flex items-center gap-1.5 text-[12px] text-subtle">
              <Loader2 size={12} className="animate-spin" /> Loading…
            </div>
          ) : rules.length === 0 ? (
            <p className="text-[12px] text-subtle">
              No standing rules yet — applied fixes appear here and guide future ingest.
            </p>
          ) : (
            <ul className="space-y-2">
              {rules.map((r) => (
                <li
                  key={r.id}
                  className="flex items-start justify-between gap-2 rounded-lg border border-navy-100 bg-navy-50/50 px-3 py-2 text-[12px]"
                >
                  <div>
                    <div className="font-semibold text-navy-800">{r.kind}</div>
                    <div className="text-navy-700">{r.subject}
                      {r.object ? ` → ${r.object}` : ""}
                    </div>
                    <div className="text-[10px] text-subtle">{r.created_at}</div>
                  </div>
                  <button
                    type="button"
                    title="Delete rule"
                    onClick={async () => {
                      try {
                        await api.deleteCorrection(r.id);
                        void loadRules();
                      } catch { /* keep list */ }
                    }}
                    className="focus-ring rounded p-1 text-rose-600 hover:bg-rose-50"
                  >
                    <Trash2 size={13} />
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </aside>
  );
}
