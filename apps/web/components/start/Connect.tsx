"use client";

import { useEffect, useState } from "react";
import { ArrowRight, Loader2, Lock } from "lucide-react";
import { api } from "@/lib/api";
import type { QuizField } from "@/lib/types";
import { StepShell, ExampleBox } from "./StepShell";

interface Props {
  workspaceId: number;
  kind: "postgres" | "mysql" | "oracle" | "files" | string;
  onConnected: (datasourceId: number) => void;
  onBack: () => void;
}

const ADVANCED = new Set(["port", "dialect", "extra_context", "schema"]);

/** Screen 4 — per-source connect form (DB). Quiz fields drive the labels. */
export function Connect({ workspaceId, kind, onConnected, onBack }: Props) {
  const [fields, setFields] = useState<QuizField[]>([]);
  const [values, setValues] = useState<Record<string, string>>({});
  const [showAdvanced, setShowAdvanced] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.getDatasourceQuiz(kind).then((q) => {
      setFields(q.fields);
      const defaults: Record<string, string> = {};
      for (const f of q.fields)
        if (f.default !== undefined) defaults[f.name] = f.default;
      setValues(defaults);
    }).catch(() => setFields([]));
  }, [kind]);

  const submit = async () => {
    setBusy(true);
    setError(null);
    try {
      const secret = values.password || values.secret || "";
      const config: Record<string, unknown> = {};
      for (const f of fields) {
        if (f.secret) continue;
        if (values[f.name]) config[f.name] = values[f.name];
      }
      const ds = await api.addDatasource(
        workspaceId, values.name || `${kind}-connection`,
        kind, config, secret,
      );
      const test = await api.testDatasource(ds.id);
      if (!test.ok) {
        setError(test.error || "Connection failed");
        setBusy(false);
        return;
      }
      onConnected(ds.id);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Connect failed");
      setBusy(false);
    }
  };

  const visible = fields.filter((f) => !ADVANCED.has(f.name) || showAdvanced);

  return (
    <StepShell progress={65}>
      <h1 className="max-w-2xl text-center font-display text-[2rem] leading-tight text-navy-900">
        Connect to your database
      </h1>

      <section className="mt-7 w-full max-w-md rounded-2xl border border-navy-100 bg-white p-6 shadow-soft">
        {visible.map((f) => (
          <FieldRow
            key={f.name}
            field={f}
            value={values[f.name] || ""}
            onChange={(v) => setValues({ ...values, [f.name]: v })}
          />
        ))}

        {error && (
          <div className="mt-3 rounded-lg border border-rose-200 bg-rose-50 px-3 py-2 text-[12px] text-rose-700">
            {error}
          </div>
        )}

        <button
          type="button"
          onClick={submit}
          disabled={busy}
          className="focus-ring mt-5 inline-flex w-full items-center justify-center gap-2 rounded-xl bg-navy-800 px-4 py-3 text-[15px] font-semibold text-white hover:bg-navy-700 disabled:opacity-50"
        >
          {busy ? <Loader2 size={15} className="animate-spin" /> : "Connect"}
          <ArrowRight size={14} />
        </button>

        <button
          type="button"
          onClick={() => setShowAdvanced((v) => !v)}
          className="focus-ring mt-4 block w-full text-center text-[12px] text-steel-600 hover:text-steel-500"
        >
          {showAdvanced ? "Hide advanced" : "Advanced (port, dialect, options)"}
        </button>
      </section>

      <button
        onClick={onBack}
        className="focus-ring mt-4 text-[12px] text-subtle hover:text-navy-700"
      >
        ← Back
      </button>

      <ExampleBox label="What happens when you click Connect">
        Aryx opens a test connection, lists your tables (read-only), and shows
        you what it sees. Your password is{" "}
        <strong>encrypted before it touches disk</strong> with a key only the
        server holds; the UI never shows it again.
      </ExampleBox>
    </StepShell>
  );
}

function FieldRow({
  field, value, onChange,
}: { field: QuizField; value: string; onChange: (v: string) => void }) {
  return (
    <div className="mb-3.5">
      <label className="block text-[12px] font-semibold text-navy-700">
        {field.label}
      </label>
      <input
        type={field.secret ? "password" : "text"}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={field.help || ""}
        className="focus-ring mt-1 w-full rounded-lg border border-navy-100 bg-white px-3 py-2 text-[14px] text-navy-900 focus:border-steel-500"
      />
      {field.secret && (
        <div className="mt-1 inline-flex items-center gap-1 text-[11px] text-emerald-600">
          <Lock size={10} /> Encrypted on save · never shown again
        </div>
      )}
      {field.help && !field.secret && (
        <div className="mt-1 text-[11px] text-subtle">{field.help}</div>
      )}
    </div>
  );
}
