"use client";

import { useState } from "react";
import { Plus, X, Save, Loader2 } from "lucide-react";
import { api } from "@/lib/api";
import type { OntologyType } from "@/lib/types";
import { cn } from "@/lib/cn";

interface AttrsEditorProps {
  type: OntologyType;
  workspaceId: number;
  onSaved: () => void;
}

/** Inline attribute editor: chips + add + remove + save back via API. */
export function AttrsEditor({ type, workspaceId, onSaved }: AttrsEditorProps) {
  const [attrs, setAttrs] = useState<string[]>(type.attributes);
  const [draft, setDraft] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const dirty = attrs.length !== type.attributes.length
    || attrs.some((a, i) => a !== type.attributes[i]);

  const add = () => {
    const v = draft.trim();
    if (!v || attrs.includes(v)) {
      setDraft("");
      return;
    }
    setAttrs([...attrs, v]);
    setDraft("");
  };

  const remove = (a: string) => setAttrs(attrs.filter((x) => x !== a));

  const save = async () => {
    setBusy(true);
    setError(null);
    try {
      await api.updateTypeAttrs(workspaceId, type.name, attrs);
      onSaved();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Save failed");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="space-y-3">
      {attrs.length === 0 ? (
        <Empty label="No attributes yet — add one below." />
      ) : (
        <ul className="space-y-1.5">
          {attrs.map((a) => (
            <li
              key={a}
              className="group flex items-center justify-between rounded-lg border border-navy-100 bg-navy-50/40 px-3 py-2 font-mono text-[12px] text-navy-800"
            >
              <span className="truncate">{a}</span>
              <button
                type="button"
                onClick={() => remove(a)}
                className="focus-ring rounded p-1 text-subtle opacity-0 transition-opacity hover:bg-white hover:text-rose-500 group-hover:opacity-100"
                aria-label={`Remove ${a}`}
              >
                <X size={12} />
              </button>
            </li>
          ))}
        </ul>
      )}

      <div className="flex items-center gap-2">
        <input
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && add()}
          placeholder="new attribute…"
          className="focus-ring flex-1 rounded-lg border border-navy-100 bg-white px-3 py-1.5 font-mono text-[12px] text-navy-800 placeholder:text-subtle focus:border-steel-500"
        />
        <button
          type="button"
          onClick={add}
          disabled={!draft.trim()}
          className="focus-ring inline-flex size-8 items-center justify-center rounded-lg bg-navy-100 text-navy-700 hover:bg-navy-200 disabled:opacity-50"
          aria-label="Add attribute"
        >
          <Plus size={14} />
        </button>
      </div>

      {error && (
        <div className="rounded-lg border border-rose-200 bg-rose-50 px-3 py-2 text-[11px] text-rose-700">
          {error}
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
          Save attributes
        </button>
      )}
    </div>
  );
}

function Empty({ label }: { label: string }) {
  return (
    <div className="rounded-lg border border-dashed border-navy-200 px-4 py-6 text-center text-[12px] italic text-subtle">
      {label}
    </div>
  );
}
