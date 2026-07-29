"use client";

import { useEffect, useState } from "react";
import { Loader2, CheckCircle2, XCircle, AlertTriangle } from "lucide-react";
import { api } from "@/lib/api";
import type { UserIntent, UserIntentRequest } from "@/lib/types";

const CHART_HINT = "bar, line, pie, area, table, scatter, kpi, funnel, map…";
const AUDIENCE_HINT = "executive, sales leadership, finance, operations…";

/** Split a comma/newline separated string into trimmed, non-empty items. */
function toList(value: string): string[] {
  return value
    .split(/[,\n]/)
    .map((s) => s.trim())
    .filter(Boolean);
}

interface Props {
  workspaceId: number;
}

export function IntentForm({ workspaceId }: Props) {
  const [uploadedFile, setUploadedFile] = useState("contracts_1000.csv");
  const [domain, setDomain] = useState("contract_management");
  const [objective, setObjective] = useState(
    "Show contract renewal performance and identify regions with weak renewal outcomes",
  );
  const [kpis, setKpis] = useState("renewal rate, renewed contract value");
  const [dimensions, setDimensions] = useState("region");
  const [chartTypes, setChartTypes] = useState("bar");
  const [audience, setAudience] = useState("sales leadership");
  const [startDate, setStartDate] = useState("");
  const [endDate, setEndDate] = useState("");

  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<UserIntent | null>(null);
  const [recent, setRecent] = useState<UserIntent[]>([]);

  const refreshRecent = () => {
    api.listIntents(workspaceId).then(setRecent).catch(() => setRecent([]));
  };

  useEffect(refreshRecent, [workspaceId]);

  const submit = async () => {
    setSubmitting(true);
    setError(null);
    const req: UserIntentRequest = {
      uploaded_file: uploadedFile,
      domain,
      objective,
      preferred_kpis: toList(kpis),
      preferred_dimensions: toList(dimensions),
      preferred_chart_types: toList(chartTypes),
      target_audience: audience,
      date_range:
        startDate || endDate ? { start: startDate, end: endDate } : null,
    };
    try {
      const res = await api.captureIntent(req, workspaceId);
      setResult(res);
      refreshRecent();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="mx-auto grid max-w-6xl gap-6 px-6 py-8 lg:grid-cols-2">
      {/* ── Form ── */}
      <section className="rounded-xl border border-navy-100 bg-white p-6 shadow-sm">
        <h1 className="text-lg font-semibold text-navy-900">User Intent Capture</h1>
        <p className="mt-1 text-sm text-navy-500">
          Collect the business domain, objective, and dashboard preferences.
          Required fields block; unsupported preferences are kept as warnings.
        </p>

        <div className="mt-5 space-y-4">
          <Field label="Uploaded file reference" required>
            <input className={inputCls} value={uploadedFile}
                   onChange={(e) => setUploadedFile(e.target.value)}
                   placeholder="contracts_1000.csv" />
          </Field>

          <Field label="Business domain" required>
            <input className={inputCls} value={domain}
                   onChange={(e) => setDomain(e.target.value)}
                   placeholder="contract_management" />
          </Field>

          <Field label="Objective" required>
            <textarea className={`${inputCls} min-h-[70px]`} value={objective}
                      onChange={(e) => setObjective(e.target.value)}
                      placeholder="Plain-language analysis objective" />
          </Field>

          <Field label="Preferred KPIs" hint="comma-separated">
            <input className={inputCls} value={kpis}
                   onChange={(e) => setKpis(e.target.value)} />
          </Field>

          <Field label="Preferred dimensions" hint="comma-separated">
            <input className={inputCls} value={dimensions}
                   onChange={(e) => setDimensions(e.target.value)} />
          </Field>

          <Field label="Preferred chart types" hint={CHART_HINT}>
            <input className={inputCls} value={chartTypes}
                   onChange={(e) => setChartTypes(e.target.value)} />
          </Field>

          <Field label="Target audience" hint={AUDIENCE_HINT}>
            <input className={inputCls} value={audience}
                   onChange={(e) => setAudience(e.target.value)} />
          </Field>

          <div className="grid grid-cols-2 gap-3">
            <Field label="Date range start" hint="optional">
              <input type="date" className={inputCls} value={startDate}
                     onChange={(e) => setStartDate(e.target.value)} />
            </Field>
            <Field label="Date range end" hint="optional">
              <input type="date" className={inputCls} value={endDate}
                     onChange={(e) => setEndDate(e.target.value)} />
            </Field>
          </div>

          <button onClick={submit} disabled={submitting}
                  className="focus-ring inline-flex items-center gap-2 rounded-lg bg-navy-900 px-4 py-2 text-sm font-medium text-white hover:bg-navy-800 disabled:opacity-60">
            {submitting && <Loader2 size={15} className="animate-spin" />}
            Capture intent
          </button>
          {error && <p className="text-sm text-red-600">Request failed: {error}</p>}
        </div>
      </section>

      {/* ── Result + recent ── */}
      <section className="space-y-6">
        {result && <ResultCard intent={result} />}

        <div className="rounded-xl border border-navy-100 bg-white p-6 shadow-sm">
          <h2 className="text-sm font-semibold text-navy-900">
            Recent captures ({recent.length})
          </h2>
          <ul className="mt-3 space-y-2">
            {recent.map((r) => (
              <li key={r.request_id}
                  className="flex items-center justify-between rounded-lg border border-navy-100 px-3 py-2 text-sm">
                <span className="truncate">
                  <code className="text-navy-500">{r.request_id}</code>
                  <span className="ml-2 text-navy-700">{r.domain}</span>
                </span>
                <StatusPill status={r.validation_status} />
              </li>
            ))}
            {recent.length === 0 && (
              <li className="text-sm text-navy-400">No captures yet.</li>
            )}
          </ul>
        </div>
      </section>
    </div>
  );
}

function ResultCard({ intent }: { intent: UserIntent }) {
  const ok = intent.validation_status === "valid";
  return (
    <div className={`rounded-xl border p-6 shadow-sm ${ok ? "border-emerald-200 bg-emerald-50/50" : "border-red-200 bg-red-50/50"}`}>
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          {ok ? <CheckCircle2 className="text-emerald-600" size={18} />
              : <XCircle className="text-red-600" size={18} />}
          <span className="font-semibold text-navy-900">
            {ok ? "Valid — ready to hand off" : "Invalid — blocked"}
          </span>
        </div>
        <code className="text-xs text-navy-500">{intent.request_id}</code>
      </div>

      {intent.errors.length > 0 && (
        <ul className="mt-3 space-y-1">
          {intent.errors.map((e, i) => (
            <li key={i} className="flex items-center gap-2 text-sm text-red-700">
              <XCircle size={14} /> {e}
            </li>
          ))}
        </ul>
      )}
      {intent.warnings.length > 0 && (
        <ul className="mt-3 space-y-1">
          {intent.warnings.map((w, i) => (
            <li key={i} className="flex items-center gap-2 text-sm text-amber-700">
              <AlertTriangle size={14} /> {w}
            </li>
          ))}
        </ul>
      )}

      <pre className="mt-4 overflow-x-auto rounded-lg bg-navy-900/95 p-3 text-xs text-navy-50">
        {JSON.stringify(intent, null, 2)}
      </pre>
    </div>
  );
}

function StatusPill({ status }: { status: "valid" | "invalid" }) {
  const ok = status === "valid";
  return (
    <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${ok ? "bg-emerald-100 text-emerald-700" : "bg-red-100 text-red-700"}`}>
      {status}
    </span>
  );
}

function Field({ label, hint, required, children }: {
  label: string; hint?: string; required?: boolean; children: React.ReactNode;
}) {
  return (
    <label className="block">
      <span className="mb-1 flex items-center gap-2 text-sm font-medium text-navy-800">
        {label}
        {required && <span className="text-red-500">*</span>}
        {hint && <span className="text-xs font-normal text-navy-400">{hint}</span>}
      </span>
      {children}
    </label>
  );
}

const inputCls =
  "w-full rounded-lg border border-navy-200 px-3 py-2 text-sm text-navy-900 focus-ring placeholder:text-navy-300";
