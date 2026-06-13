"use client";

import { useState } from "react";
import { ArrowRight, Edit3, CheckCircle2 } from "lucide-react";
import { api } from "@/lib/api";
import type { Brief } from "@/lib/types";
import { StepShell, ExampleBox } from "./StepShell";

interface Props {
  workspaceId: number;
  brief: Brief;
  onConfirm: () => void;
  onBack: () => void;
}

/** Screen 2 — read-back of the AI-drafted brief. Confirm or edit. */
export function Confirm({ workspaceId, brief, onConfirm, onBack }: Props) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState<Brief>(brief);
  const [busy, setBusy] = useState(false);

  const save = async () => {
    setBusy(true);
    try {
      await api.saveBrief(workspaceId, draft);
      onConfirm();
    } finally {
      setBusy(false);
    }
  };

  const candidateClasses = (draft.scope || "")
    .replace(/^IN[\s:]+/i, "")
    .split(/[,;\n]+/)
    .map((s) => s.trim())
    .filter(Boolean)
    .slice(0, 6);

  return (
    <StepShell progress={35}>
      <h1 className="max-w-2xl text-center font-display text-[2rem] leading-tight text-navy-900">
        Here's what I&nbsp;understood:
      </h1>

      <section className="mt-8 w-full max-w-xl rounded-2xl border border-navy-100 bg-white p-7 shadow-soft">
        <Row label="You track" value={draft.domain || "—"}
              editing={editing}
              onChange={(v) => setDraft({ ...draft, domain: v })} />
        <Row label="You want" value={draft.aim || "—"}
              editing={editing}
              onChange={(v) => setDraft({ ...draft, aim: v })} multiline />
        <Row label="In scope" value={draft.scope || "—"}
              editing={editing}
              onChange={(v) => setDraft({ ...draft, scope: v })} multiline last />
      </section>

      <div className="mt-6 flex w-full max-w-xl items-center justify-center gap-3">
        <button
          type="button"
          onClick={save}
          disabled={busy}
          className="focus-ring inline-flex items-center gap-2 rounded-xl bg-navy-800 px-5 py-2.5 text-[14px] font-semibold text-white hover:bg-navy-700 disabled:opacity-50"
        >
          <CheckCircle2 size={14} /> Looks right — keep going{" "}
          <ArrowRight size={14} />
        </button>
        <button
          type="button"
          onClick={() => setEditing((e) => !e)}
          className="focus-ring inline-flex items-center gap-1.5 rounded-xl border border-navy-100 bg-white px-4 py-2.5 text-[13px] font-medium text-navy-700 hover:bg-navy-50"
        >
          <Edit3 size={13} /> {editing ? "Done editing" : "Let me edit"}
        </button>
      </div>

      <button
        onClick={onBack}
        className="focus-ring mt-4 text-[12px] text-subtle hover:text-navy-700"
      >
        ← Back to goals
      </button>

      <ExampleBox label="What this means downstream">
        Aryx will look for these <em>kinds of records</em> as it reads your
        data:{" "}
        {candidateClasses.length > 0 ? (
          candidateClasses.map((c, i) => (
            <span key={c} className="font-mono text-[12px]">
              <code className="rounded bg-navy-50 px-1.5 py-0.5">{c}</code>
              {i < candidateClasses.length - 1 ? " · " : ""}
            </span>
          ))
        ) : (
          <em>discovered from your data once it's connected.</em>
        )}
        . Anything unexpected gets flagged for your review — nothing silent.
      </ExampleBox>
    </StepShell>
  );
}

function Row({
  label, value, editing, onChange, multiline, last,
}: {
  label: string; value: string; editing: boolean;
  onChange: (v: string) => void; multiline?: boolean; last?: boolean;
}) {
  return (
    <div
      className={`flex items-baseline gap-5 py-3 ${last ? "" : "border-b border-dashed border-navy-100"}`}
    >
      <div className="min-w-[100px] text-[10px] font-semibold uppercase tracking-[0.1em] text-subtle">
        {label}
      </div>
      {editing ? (
        multiline ? (
          <textarea
            value={value === "—" ? "" : value}
            onChange={(e) => onChange(e.target.value)}
            rows={2}
            className="focus-ring flex-1 resize-y rounded-md border border-navy-100 bg-white px-2 py-1 text-[14px] text-navy-900 focus:border-steel-500"
          />
        ) : (
          <input
            value={value === "—" ? "" : value}
            onChange={(e) => onChange(e.target.value)}
            className="focus-ring flex-1 rounded-md border border-navy-100 bg-white px-2 py-1 text-[14px] text-navy-900 focus:border-steel-500"
          />
        )
      ) : (
        <div className="flex-1 text-[15px] leading-relaxed text-navy-900">
          {value}
        </div>
      )}
    </div>
  );
}
