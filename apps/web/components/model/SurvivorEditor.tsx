"use client";

import { useEffect, useState } from "react";
import { Save, Loader2, Plus, X } from "lucide-react";
import { api } from "@/lib/api";
import type { OntologyType, SurvivorshipPolicy } from "@/lib/types";
import { cn } from "@/lib/cn";

interface Props {
  type: OntologyType;
  workspaceId: number;
  initialPolicy: SurvivorshipPolicy;
}

const STRATEGIES = [
  "first_non_empty",
  "source_priority",
  "most_recent",
  "most_complete",
  "most_frequent",
] as const;

/** Editable survivorship policy (G3x). Workspace-scoped — the same policy
 *  drives every type, so this editor exposes default + per-attr overrides
 *  + source-priority list. Saved via PUT /admin/workspaces/{id}/survivorship. */
export function SurvivorEditor({ type, workspaceId, initialPolicy }: Props) {
  const [policy, setPolicy] = useState<SurvivorshipPolicy>(initialPolicy);
  const [busy, setBusy] = useState(false);
  const [saved, setSaved] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [newSource, setNewSource] = useState("");

  useEffect(() => { setPolicy(initialPolicy); }, [initialPolicy, type.name]);

  const dirty = JSON.stringify(policy) !== JSON.stringify(initialPolicy);

  const setDefault = (s: string) =>
    setPolicy({ ...policy, default_strategy: s });

  const setAttrOverride = (attr: string, value: string) => {
    const next = { ...(policy.attribute_strategies || {}) };
    if (!value || value === (policy.default_strategy || "first_non_empty")) {
      delete next[attr];
    } else {
      next[attr] = value;
    }
    setPolicy({ ...policy, attribute_strategies: next });
  };

  const addSource = () => {
    const v = newSource.trim();
    if (!v) return;
    const list = policy.source_priority || [];
    if (list.includes(v)) { setNewSource(""); return; }
    setPolicy({ ...policy, source_priority: [...list, v] });
    setNewSource("");
  };

  const removeSource = (s: string) => setPolicy({
    ...policy,
    source_priority: (policy.source_priority || []).filter((x) => x !== s),
  });

  const save = async () => {
    setBusy(true); setError(null); setSaved(null);
    try {
      await api.setSurvivorship(workspaceId, policy);
      setSaved("Policy saved");
      setTimeout(() => setSaved(null), 2000);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Save failed");
    } finally { setBusy(false); }
  };

  const def = policy.default_strategy || "first_non_empty";

  return (
    <div className="space-y-4">
      <div className="rounded-lg border border-navy-100 bg-white px-3 py-2.5">
        <label className="block text-[10px] uppercase tracking-wider text-subtle">
          Default strategy
        </label>
        <select
          value={def}
          onChange={(e) => setDefault(e.target.value)}
          className="focus-ring mt-1 w-full rounded-md border border-navy-100 bg-white px-2 py-1.5 font-mono text-[12px] text-navy-800 focus:border-steel-500"
        >
          {STRATEGIES.map((s) => (
            <option key={s} value={s}>{s}</option>
          ))}
        </select>
      </div>

      <div className="rounded-lg border border-navy-100 bg-white px-3 py-2.5">
        <label className="block text-[10px] uppercase tracking-wider text-subtle">
          Source priority {def !== "source_priority" && (
            <span className="text-subtle/60"> · used only by source_priority</span>
          )}
        </label>
        <div className="mt-2 flex flex-wrap gap-1.5">
          {(policy.source_priority || []).length === 0 && (
            <span className="text-[11px] italic text-subtle">empty</span>
          )}
          {(policy.source_priority || []).map((s, i) => (
            <span
              key={s}
              className="group inline-flex items-center gap-1 rounded-full border border-navy-100 bg-navy-50/60 pl-2 pr-1 py-0.5 font-mono text-[11px] text-navy-700"
            >
              {i + 1}. {s}
              <button
                type="button"
                onClick={() => removeSource(s)}
                className="focus-ring rounded-full p-0.5 text-subtle hover:bg-white hover:text-rose-500"
              >
                <X size={9} />
              </button>
            </span>
          ))}
        </div>
        <div className="mt-2 flex items-center gap-1.5">
          <input
            value={newSource}
            onChange={(e) => setNewSource(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && addSource()}
            placeholder="add source… (e.g. crm)"
            className="focus-ring flex-1 rounded-md border border-navy-100 bg-white px-2 py-1 font-mono text-[11px] text-navy-800 focus:border-steel-500"
          />
          <button
            type="button"
            onClick={addSource}
            disabled={!newSource.trim()}
            className="focus-ring inline-flex size-6 items-center justify-center rounded-md bg-navy-100 text-navy-700 hover:bg-navy-200 disabled:opacity-50"
            aria-label="Add source"
          >
            <Plus size={11} />
          </button>
        </div>
      </div>

      <div className="rounded-lg border border-navy-100 bg-white">
        <div className="border-b border-navy-100 px-3 py-2">
          <label className="block text-[10px] uppercase tracking-wider text-subtle">
            Per-attribute override · {type.name}
          </label>
        </div>
        {type.attributes.length === 0 ? (
          <p className="px-3 py-3 text-[11px] italic text-subtle">
            no attributes yet
          </p>
        ) : (
          <ul className="divide-y divide-navy-100/60">
            {type.attributes.map((a) => (
              <li key={a} className="flex items-center justify-between gap-2 px-3 py-2">
                <span className="truncate font-mono text-[11px] text-navy-700">
                  {a}
                </span>
                <select
                  value={policy.attribute_strategies?.[a] || def}
                  onChange={(e) => setAttrOverride(a, e.target.value)}
                  className="focus-ring rounded-md border border-navy-100 bg-white px-2 py-0.5 font-mono text-[11px] text-navy-800 focus:border-steel-500"
                >
                  {STRATEGIES.map((s) => (
                    <option key={s} value={s}>{s}</option>
                  ))}
                </select>
              </li>
            ))}
          </ul>
        )}
      </div>

      {error && (
        <div className="rounded-lg border border-rose-200 bg-rose-50 px-3 py-2 text-[11px] text-rose-700">
          {error}
        </div>
      )}
      {saved && (
        <div className="rounded-lg border border-emerald-200 bg-emerald-50 px-3 py-2 text-[11px] text-emerald-700">
          {saved}
        </div>
      )}

      {dirty && (
        <button
          type="button"
          onClick={save}
          disabled={busy}
          className={cn(
            "focus-ring inline-flex w-full items-center justify-center gap-2 rounded-lg bg-navy-800 px-3 py-2 text-[13px] font-semibold text-white hover:bg-navy-700",
            busy && "opacity-60",
          )}
        >
          {busy ? <Loader2 size={14} className="animate-spin" /> : <Save size={14} />}
          Save survivorship policy
        </button>
      )}
    </div>
  );
}
