"use client";

import { useState } from "react";
import { ArrowRight, CheckCircle2, Loader2 } from "lucide-react";
import { StepShell, ExampleBox } from "./StepShell";

/** Matches the API's listing cap (datasource_api._MAX_LISTED_TABLES). */
const LIST_CAP = 200;

export const PRIMARY_BUTTON =
  "focus-ring mt-5 inline-flex w-full items-center justify-center gap-2 rounded-xl " +
  "bg-navy-800 px-4 py-3 text-[15px] font-semibold text-white hover:bg-navy-700 " +
  "disabled:opacity-50";

export const LINK_BUTTON =
  "focus-ring mt-4 block w-full text-center text-[12px] text-steel-600 hover:text-steel-500";

export function ErrorBox({ error }: { error: string | null }) {
  if (!error) return null;
  return (
    <div className="mt-3 rounded-lg border border-rose-200 bg-rose-50 px-3 py-2 text-[12px] text-rose-700">
      {error}
    </div>
  );
}

interface Props {
  tables: string[];
  busy: boolean;
  error: string | null;
  onLoad: (tables: string[]) => void;
  onSkip: () => void;
}

/** After a verified connect: choose which tables to ingest (all ticked). */
export function TablePicker({ tables, busy, error, onLoad, onSkip }: Props) {
  const [selected, setSelected] = useState<Set<string>>(() => new Set(tables));
  const allOn = selected.size === tables.length;

  const toggle = (t: string) => {
    const next = new Set(selected);
    if (next.has(t)) next.delete(t); else next.add(t);
    setSelected(next);
  };

  return (
    <StepShell progress={75}>
      <h1 className="max-w-2xl text-center font-display text-[2rem] leading-tight text-navy-900">
        Connected — pick the tables to load
      </h1>
      <section className="mt-7 w-full max-w-md rounded-2xl border border-navy-100 bg-white p-6 shadow-soft">
        <div className="mb-3 flex items-center justify-between text-[13px]">
          <span className="inline-flex items-center gap-1.5 text-emerald-700">
            <CheckCircle2 size={14} /> Found {tables.length} table
            {tables.length === 1 ? "" : "s"} (read-only)
          </span>
          {tables.length > 1 && (
            <button type="button" className="text-steel-600 hover:text-steel-500"
                    onClick={() => setSelected(allOn ? new Set() : new Set(tables))}>
              {allOn ? "Select none" : "Select all"}
            </button>
          )}
        </div>
        {tables.length === 0 && (
          <p className="text-[13px] text-subtle">
            No tables are visible to this user. Check the database name and
            the user&apos;s permissions.
          </p>
        )}
        {tables.length >= LIST_CAP && (
          <p className="mb-2 text-[12px] text-amber-700">
            Showing the first {LIST_CAP} tables — a load covers only the ones listed here.
          </p>
        )}
        {tables.map((t) => (
          <label key={t} className="flex cursor-pointer items-center gap-2 py-1 text-[14px] text-navy-900">
            <input type="checkbox" checked={selected.has(t)} onChange={() => toggle(t)} />
            <span className="font-mono text-[13px]">{t}</span>
          </label>
        ))}

        <ErrorBox error={error} />

        <button type="button" onClick={() => onLoad([...selected])}
                disabled={busy || selected.size === 0} className={PRIMARY_BUTTON}>
          {busy ? <Loader2 size={15} className="animate-spin" />
                : `Load ${selected.size} table${selected.size === 1 ? "" : "s"}`}
          <ArrowRight size={14} />
        </button>
        <button type="button" onClick={onSkip} disabled={busy} className={LINK_BUTTON}>
          Skip for now — keep the connection, load later
        </button>
      </section>
      <ExampleBox label="What happens when you click Load">
        Aryx uses your business context to decide what each table
        represents, then reads the rows (read-only) into its own store and
        builds the graph. Progress shows on the next screen and in Observe.
      </ExampleBox>
    </StepShell>
  );
}
