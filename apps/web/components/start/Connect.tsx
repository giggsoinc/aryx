"use client";

import { useEffect, useState } from "react";
import { ArrowRight, Loader2, Lock } from "lucide-react";
import { api } from "@/lib/api";
import type { QuizField } from "@/lib/types";
import { StepShell, ExampleBox } from "./StepShell";
import { ErrorBox, LINK_BUTTON, PRIMARY_BUTTON, TablePicker } from "./TablePicker";

interface Props {
  workspaceId: number;
  kind: "postgres" | "mysql" | "oracle" | "files" | string;
  /** Called once the tables are queued for ingest (jobId) or skipped. */
  onConnected: (datasourceId: number, ingestJobId?: string) => void;
  onBack: () => void;
}

// Business context (extra_context) is required by the API, so it is NOT
// hidden behind "Advanced" — only genuinely optional knobs live there.
const ADVANCED = new Set(["port", "dialect", "schema"]);

const LABELS: Record<string, string> = {
  host: "Host", port: "Port", database: "Database name", user: "Username",
  password: "Password", extra_context: "Business context", schema: "Schema",
  dialect: "Dialect",
};

const labelOf = (f: QuizField) => f.label || LABELS[f.name] || f.name;

/** Pull the human `detail` out of fetchJSON's "400 Bad Request: {...}" errors. */
function errorText(e: unknown, fallback: string): string {
  const msg = e instanceof Error ? e.message : String(e ?? "");
  const json = msg.indexOf("{");
  if (json >= 0) {
    try {
      const detail = JSON.parse(msg.slice(json)).detail;
      if (typeof detail === "string") return detail;
    } catch { /* not JSON — fall through */ }
  }
  return msg || fallback;
}

/** Screen 4 — per-source connect form (DB). Quiz fields drive the labels. */
export function Connect({ workspaceId, kind, onConnected, onBack }: Props) {
  const [fields, setFields] = useState<QuizField[]>([]);
  const [values, setValues] = useState<Record<string, string>>({});
  const [showAdvanced, setShowAdvanced] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // Set once the connection is verified + saved: pick tables, then ingest.
  const [connected, setConnected] = useState<{ id: number; tables: string[] } | null>(null);

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
    const missing = fields.filter(
      (f) => f.required && !(values[f.name] || "").trim());
    if (missing.length) {
      setError(`Please fill in: ${missing.map(labelOf).join(", ")}.`);
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const secret = values.password || values.secret || "";
      const config: Record<string, unknown> = {};
      for (const f of fields) {
        if (f.secret) continue;
        const v = (values[f.name] || "").trim();
        if (v) config[f.name] = v;
      }
      const db = String(config.database || "").replace(/[^\w.-]+/g, "_");
      const name = values.name?.trim() || `${kind}-${db || "connection"}`;
      // verify=true: the server tests first and saves only on success.
      const ds = await api.addDatasource(workspaceId, name, kind, config,
                                         secret, true);
      setConnected({ id: ds.id, tables: ds.tables ?? [] });
    } catch (e) {
      setError(errorText(e, "Connect failed"));
    } finally {
      setBusy(false);
    }
  };

  const ingest = async (tables: string[]) => {
    if (!connected) return;
    setBusy(true);
    setError(null);
    try {
      const res = await api.ingestDatasource(connected.id, tables, workspaceId);
      onConnected(connected.id, res.job_id);
    } catch (e) {
      setError(errorText(e, "Could not start loading the tables"));
      setBusy(false);
    }
  };

  const visible = fields.filter((f) => !ADVANCED.has(f.name) || showAdvanced);

  if (connected) {
    return (
      <TablePicker tables={connected.tables} busy={busy} error={error}
                   onLoad={ingest} onSkip={() => onConnected(connected.id)} />
    );
  }

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

        <ErrorBox error={error} />

        <button type="button" onClick={submit} disabled={busy} className={PRIMARY_BUTTON}>
          {busy ? <Loader2 size={15} className="animate-spin" /> : "Connect"}
          <ArrowRight size={14} />
        </button>

        <button
          type="button"
          onClick={() => setShowAdvanced((v) => !v)}
          className={LINK_BUTTON}
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
        Aryx opens a test connection and lists your tables (read-only). The
        connection is saved only if that test works. Your password is{" "}
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
        {labelOf(field)}
        {field.required && <span className="ml-0.5 text-rose-600">*</span>}
      </label>
      <input
        type={field.secret ? "password" : "text"}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={field.help || ""}
        autoComplete={field.secret ? "new-password" : "off"}
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
