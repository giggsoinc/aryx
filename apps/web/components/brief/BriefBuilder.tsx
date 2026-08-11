"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import {
  AlertCircle, AlertTriangle, CheckCircle2, FileText, Loader2, Plus, Sparkles,
  Upload, X,
} from "lucide-react";
import { api } from "@/lib/api";
import { cn } from "@/lib/cn";
import type { Brief } from "@/lib/types";
import { useChainJob, type ChainJobState } from "@/lib/useChainJob";

/** One toggleable suggestion for a list field (objectives/roles/questions). */
interface Item { text: string; on: boolean }

interface DocTag { filename: string; chars: number; error?: string }

interface Props {
  workspaceId: number;
  /** Existing brief to preload (revisit mode). */
  initial?: Brief;
  submitLabel: string;
  /** Called after the brief is saved server-side. */
  onSubmitted: (brief: Brief) => void;
  /** Optional skip — proceed without saving anything. */
  onSkip?: () => void;
}

const ACCEPT = ".pdf,.doc,.docx,.rtf,.ppt,.pptx,.txt,.md";

function toItems(list?: string[]): Item[] {
  return (list ?? []).map((text) => ({ text, on: true }));
}
function fromItems(items: Item[]): string[] {
  return items.filter((i) => i.on).map((i) => i.text);
}

/** Cruise-control brief: documents + one sentence → LLM pre-answers all six
 *  questions; the user confirms chips and lightly edits — never authors from
 *  a blank form. Shared by the Onboard wizard (step 1) and /brief. */
export function BriefBuilder({
  workspaceId, initial, submitLabel, onSubmitted, onSkip,
}: Props) {
  const [domain, setDomain] = useState(initial?.domain ?? "");
  const [aim, setAim] = useState(initial?.aim ?? "");
  const [scope, setScope] = useState(initial?.scope ?? "");
  const [objectives, setObjectives] = useState<Item[]>(toItems(initial?.objectives));
  const [roles, setRoles] = useState<Item[]>(toItems(initial?.roles));
  const [questions, setQuestions] = useState<Item[]>(toItems(initial?.questions));

  const [seed, setSeed] = useState("");
  const [docs, setDocs] = useState<DocTag[]>([]);
  const docTexts = useRef<string[]>([]);
  const [reading, setReading] = useState(false);
  const [drafting, setDrafting] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  // Saving the brief starts the zero-click auto-chain (intent -> context ->
  // planner -> execution -> dashboard, see aryx.pipeline.auto_chain) —
  // poll its job so the user sees the chain move without clicking anything.
  const [chainJobId, setChainJobId] = useState<string | null>(null);
  const chain = useChainJob(chainJobId);

  // LLM health — cruise control needs a model that is actually READY, not
  // just configured (fresh installs spend minutes pulling Ollama models).
  const [llm, setLlm] = useState<{
    ok: boolean; provider: string; model: string; detail: string;
  } | null>(null);
  const [llmChecking, setLlmChecking] = useState(true);
  const checkLlm = useCallback(() => {
    setLlmChecking(true);
    api.getLlmHealth()
      .then(setLlm)
      .catch(() => setLlm({
        ok: false, provider: "", model: "",
        detail: "API not reachable — is the backend running?",
      }))
      .finally(() => setLlmChecking(false));
  }, []);
  useEffect(() => { checkLlm(); }, [checkLlm]);
  // While the model is still downloading, re-probe on its own so the bar
  // flips to ready without the user hammering Retry.
  useEffect(() => {
    if (llm && !llm.ok) {
      const t = setInterval(checkLlm, 10000);
      return () => clearInterval(t);
    }
  }, [llm, checkLlm]);

  // Reload fields when the stored brief changes (workspace switch).
  useEffect(() => {
    setDomain(initial?.domain ?? "");
    setAim(initial?.aim ?? "");
    setScope(initial?.scope ?? "");
    setObjectives(toItems(initial?.objectives));
    setRoles(toItems(initial?.roles));
    setQuestions(toItems(initial?.questions));
  }, [initial]);

  const readDocs = useCallback(async (files: FileList | null) => {
    if (!files?.length) return;
    setReading(true); setError(null);
    for (const file of Array.from(files)) {
      try {
        const res = await api.extractBriefDoc(workspaceId, file);
        docTexts.current.push(res.text);
        setDocs((d) => [...d, { filename: res.filename, chars: res.chars }]);
      } catch (e) {
        setDocs((d) => [...d, {
          filename: file.name, chars: 0,
          error: e instanceof Error ? e.message : "read failed",
        }]);
      }
    }
    setReading(false);
  }, [workspaceId]);

  const friendlyErr = (e: unknown, fallback: string) => {
    const raw = e instanceof Error ? e.message : String(e);
    if (/\b413\b/.test(raw)) return "File too large (max 20 MB per document).";
    if (/\b415\b/.test(raw)) return "Unsupported file type for briefing docs.";
    if (/\b422\b/.test(raw)) return "Could not read that document — try PDF, DOCX, or plain text.";
    if (/not ready|unreachable|API not reachable/i.test(raw))
      return "Language model not ready — check Settings, then retry.";
    if (raw.length > 180) return `${fallback}: ${raw.slice(0, 160)}…`;
    return raw || fallback;
  };

  const hasContent =
    !!(domain.trim() || aim.trim() || scope.trim()
      || fromItems(objectives).length || fromItems(roles).length
      || fromItems(questions).length);

  const [aiOpen, setAiOpen] = useState(!hasContent);

  useEffect(() => {
    // Keep AI assist collapsed when revisiting a filled brief.
    if (hasContent) setAiOpen(false);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [initial]);

  const applyDraft = (b: Brief) => {
    setDomain(b.domain ?? "");
    setAim(b.aim ?? "");
    setScope(b.scope ?? "");
    setObjectives(toItems(b.objectives));
    setRoles(toItems(b.roles));
    setQuestions(toItems(b.questions));
    setNotice("Drafted — tap chips to keep or drop, edit anything, then save.");
  };

  const draft = async () => {
    const docText = docTexts.current.join("\n\n").slice(0, 12000);
    if (!seed.trim() && !docText) {
      setError("Add a document or one sentence first — or fill the six questions below by hand.");
      return;
    }
    if (hasContent) {
      const ok = window.confirm(
        "Replace your current brief answers with the AI draft?",
      );
      if (!ok) return;
    }
    setDrafting(true); setError(null); setNotice(null);
    try {
      const res = await api.draftBrief(workspaceId, seed.trim(), docText);
      applyDraft(res.brief);
    } catch (e) {
      setError(friendlyErr(e, "Draft failed"));
    } finally {
      setDrafting(false);
    }
  };

  const save = async () => {
    setSaving(true); setError(null); setNotice(null);
    try {
      const brief: Brief = {
        domain: domain.trim(),
        aim: aim.trim(),
        scope: scope.trim(),
        objectives: fromItems(objectives),
        roles: fromItems(roles),
        questions: fromItems(questions),
        source_docs: Array.from(new Set([
          ...(initial?.source_docs ?? []),
          ...docs.filter((d) => !d.error).map((d) => d.filename),
        ])),
      };
      const res = await api.saveBrief(workspaceId, brief);
      setChainJobId(res.chain_job_id);
      setNotice("Brief saved.");
      onSubmitted(brief);
    } catch (e) {
      setError(friendlyErr(e, "Save failed"));
    } finally {
      setSaving(false);
    }
  };

  const filled = [
    domain, aim, scope,
    fromItems(objectives).join(""), fromItems(roles).join(""),
    fromItems(questions).join(""),
  ].filter((v) => v.trim().length > 0).length;
  const depthLabels = ["Generic", "Grounded", "Grounded", "Sharp", "Sharp", "Expert", "Expert"];

  return (
    <div className="w-full max-w-3xl">
      <div className={cn(
        "mb-4 flex items-center justify-between gap-3 rounded-lg border px-3 py-2 text-[12px]",
        llm?.ok
          ? "border-emerald-200 bg-emerald-50 text-emerald-800"
          : "border-amber-200 bg-amber-50 text-amber-800",
      )}>
        <span className="flex items-center gap-2">
          <span className={cn(
            "inline-block size-2 shrink-0 rounded-full",
            llmChecking ? "animate-pulse bg-navy-300"
              : llm?.ok ? "bg-emerald-500" : "bg-amber-500",
          )} />
          {llmChecking && !llm
            ? "Checking your language model…"
            : llm?.ok
            ? <>Model ready — <b>{llm.provider} · {llm.model}</b> (optional AI draft).</>
            : <>
                Model not ready{llm?.model ? <> (<b>{llm.provider} · {llm.model}</b>)</> : null}
                {" — "}{llm?.detail}{" · "}
                <Link href="/settings" className="underline">Settings</Link>
              </>}
        </span>
        {!llm?.ok && (
          <button
            type="button" onClick={checkLlm} disabled={llmChecking}
            className="focus-ring shrink-0 rounded-md border border-amber-300 bg-white px-2 py-0.5 text-[11px] font-semibold text-amber-800 hover:bg-amber-100 disabled:opacity-50"
          >
            {llmChecking ? "Checking…" : "Retry"}
          </button>
        )}
      </div>
      {error && (
        <div className="mb-4 flex items-center gap-2 rounded-lg border border-rose-200 bg-rose-50 px-3 py-2 text-[12px] text-rose-700">
          <AlertCircle size={13} className="shrink-0" /> {error}
        </div>
      )}
      {notice && (
        <div className="mb-4 flex items-center gap-2 rounded-lg border border-emerald-200 bg-emerald-50 px-3 py-2 text-[12px] text-emerald-700">
          <CheckCircle2 size={13} className="shrink-0" /> {notice}
        </div>
      )}
      {chain && <ChainStatusStrip chain={chain} />}

      {/* PRIMARY: answer the brief directly */}
      <div className="mb-4 space-y-5 rounded-xl border border-navy-100 bg-white p-5 shadow-soft">
        <div>
          <h2 className="text-[14px] font-bold text-navy-900">Your brief</h2>
          <p className="mt-1 text-[12px] text-subtle">
            Answer any of these six questions by hand — every field is optional.
            Save anytime. AI draft below is optional help, not required.
          </p>
        </div>

        <ScalarField
          label="1 · What world is this about?" hint="domain"
          value={domain} onChange={setDomain}
        />
        <ScalarField
          label="2 · What should the knowledge model make possible?" hint="aim"
          value={aim} onChange={setAim} rows={2}
        />
        <ChipField
          label="3 · Which outcomes matter?" hint="objectives — tap to keep or drop"
          items={objectives} onChange={setObjectives}
          addPlaceholder="Add an outcome…"
        />
        <ScalarField
          label="4 · What's IN, what's OUT?" hint="scope"
          value={scope} onChange={setScope} rows={2}
        />
        <ChipField
          label="5 · Who will use the answers?" hint="participant roles"
          items={roles} onChange={setRoles}
          addPlaceholder="Add a role…"
        />
        <ChipField
          label="6 · What must this graph be able to answer?"
          hint="proof questions — these become your test set on Ask"
          items={questions} onChange={setQuestions}
          addPlaceholder="Add a question…"
        />

        <div>
          <div className="mb-1 flex items-center justify-between">
            <span className="text-[11px] font-medium text-navy-600">Brief depth</span>
            <span className="text-[11px] font-semibold text-navy-800">{depthLabels[filled]}</span>
          </div>
          <div className="h-1.5 overflow-hidden rounded-full bg-navy-100">
            <div
              className="h-full rounded-full bg-steel-500 transition-all"
              style={{ width: `${Math.round((filled / 6) * 100)}%` }}
            />
          </div>
        </div>

        <div className="flex items-center justify-between gap-3">
          {onSkip ? (
            <button
              type="button" onClick={onSkip}
              className="focus-ring text-[12px] text-subtle hover:text-navy-700"
            >
              Skip brief entirely
            </button>
          ) : <span />}
          <button
            type="button"
            onClick={save}
            disabled={saving}
            className="focus-ring inline-flex items-center justify-center gap-2 rounded-lg bg-navy-800 px-6 py-2.5 text-[13px] font-semibold text-white hover:bg-navy-700 disabled:opacity-50"
          >
            {saving
              ? <><Loader2 size={13} className="animate-spin" /> Saving…</>
              : submitLabel}
          </button>
        </div>
      </div>

      {/* SECONDARY: optional AI draft */}
      <div className="rounded-xl border border-dashed border-navy-200 bg-white/80 shadow-soft">
        <button
          type="button"
          onClick={() => setAiOpen((v) => !v)}
          className="focus-ring flex w-full items-center justify-between px-5 py-3 text-left"
        >
          <span>
            <span className="text-[13px] font-bold text-navy-800">
              Optional: draft with AI
            </span>
            <span className="mt-0.5 block text-[11px] text-subtle">
              Documents are read only for this draft — not stored as ingest data.
              Re-upload after reload to draft again.
            </span>
          </span>
          <span className="text-[12px] font-semibold text-steel-600">
            {aiOpen ? "Hide" : "Show"}
          </span>
        </button>
        {aiOpen && (
          <div className="border-t border-navy-100 px-5 pb-5 pt-3">
            <p className="mb-3 text-[12px] text-subtle">
              Drop a strategy deck or one sentence. Aryx pre-fills the questions
              above — you confirm. Draft overwrites current answers (you&apos;ll
              be asked first if they&apos;re not empty).
            </p>
            <label className={cn(
              "mb-3 flex cursor-pointer flex-col items-center justify-center gap-1 rounded-xl border-2 border-dashed px-4 py-5 text-center transition-colors",
              reading ? "border-steel-400 bg-navy-50/50" : "border-navy-100 hover:border-steel-400 hover:bg-navy-50/40",
            )}>
              <input
                type="file" multiple accept={ACCEPT} className="hidden"
                onChange={(e) => { readDocs(e.target.files); e.target.value = ""; }}
              />
              <span className="flex items-center gap-2 text-[13px] font-medium text-navy-700">
                {reading ? <Loader2 size={14} className="animate-spin" /> : <Upload size={14} />}
                {reading ? "Reading…" : "Drop or pick documents"}
              </span>
              <span className="text-[11px] text-subtle">
                PDF · DOC · DOCX · PPT · PPTX — briefing only, not graph ingest
              </span>
            </label>
            {(initial?.source_docs?.length ?? 0) > 0 && (
              <div className="mb-2 text-[11px] text-subtle">
                Filenames from a previous draft (not re-openable files):{" "}
                {initial!.source_docs!.join(" · ")}
              </div>
            )}
            {docs.length > 0 && (
              <div className="mb-3 flex flex-wrap gap-1.5">
                {docs.map((d, i) => (
                  <span key={`${d.filename}-${i}`} className={cn(
                    "inline-flex items-center gap-1 rounded-lg px-2.5 py-1 text-[11px]",
                    d.error ? "bg-rose-50 text-rose-700" : "bg-navy-50 text-navy-700",
                  )}>
                    <FileText size={11} />
                    {d.filename}
                    {d.error
                      ? ` — ${d.error}`
                      : ` — ${d.chars.toLocaleString()} chars · not stored · this session only`}
                  </span>
                ))}
              </div>
            )}
            <div className="flex gap-2">
              <input
                value={seed}
                onChange={(e) => setSeed(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && draft()}
                placeholder="…and/or one sentence: e.g. Match support tickets to agents"
                className="focus-ring flex-1 rounded-lg border border-navy-100 bg-white px-3 py-2 text-[13px] text-navy-800 focus:border-steel-500"
              />
              <button
                type="button"
                onClick={draft}
                disabled={drafting || reading}
                className="focus-ring inline-flex items-center gap-1.5 rounded-lg bg-navy-800 px-4 py-2 text-[13px] font-semibold text-white hover:bg-navy-700 disabled:opacity-50"
              >
                {drafting
                  ? <><Loader2 size={13} className="animate-spin" /> Drafting…</>
                  : <><Sparkles size={13} /> Draft my brief</>}
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

/** Inline status for the auto-chain a Brief save just kicked off — replaces
 *  the old "saved, now go click Generate" flow with a live read of what's
 *  actually happening, including a plain-language reason when it pauses. */
function ChainStatusStrip({ chain }: { chain: ChainJobState }) {
  const isBlocked = chain.status === "blocked";
  const isFailed = !isBlocked && chain.status === "failed";
  const isDone = chain.status === "complete";
  return (
    <div className={cn(
      "mb-4 flex items-start gap-2 rounded-lg border px-3 py-2 text-[12px]",
      isBlocked ? "border-amber-200 bg-amber-50 text-amber-800"
        : isFailed ? "border-rose-200 bg-rose-50 text-rose-700"
        : isDone ? "border-emerald-200 bg-emerald-50 text-emerald-700"
        : "border-navy-100 bg-navy-50 text-navy-700",
    )}>
      {isBlocked || isFailed
        ? <AlertTriangle size={13} className="mt-0.5 shrink-0" />
        : isDone
        ? <CheckCircle2 size={13} className="mt-0.5 shrink-0" />
        : <Loader2 size={13} className="mt-0.5 shrink-0 animate-spin" />}
      <span>
        {isDone && "Pipeline finished automatically — check the Dashboard tab."}
        {isBlocked && (chain.error || "Paused — needs a decision before it can continue.")}
        {isFailed && `Something went wrong: ${chain.error || "unknown error"}.`}
        {!isDone && !isBlocked && !isFailed &&
          `Running — ${chain.stage || "starting"}${chain.pct != null ? ` (${chain.pct}%)` : ""}. `
          + "No need to click anything; this keeps going on its own."}
      </span>
    </div>
  );
}

function ScalarField({
  label, hint, value, onChange, rows = 1,
}: {
  label: string; hint: string; value: string;
  onChange: (v: string) => void; rows?: number;
}) {
  return (
    <div>
      <label className="mb-1 block text-[11px] font-semibold uppercase tracking-[0.1em] text-navy-600">
        {label} <span className="font-normal normal-case text-subtle">({hint})</span>
      </label>
      {rows === 1 ? (
        <input
          value={value}
          onChange={(e) => onChange(e.target.value)}
          className="focus-ring w-full rounded-lg border border-navy-100 bg-white px-3 py-2 text-[13px] text-navy-800 focus:border-steel-500"
        />
      ) : (
        <textarea
          rows={rows}
          value={value}
          onChange={(e) => onChange(e.target.value)}
          className="focus-ring w-full resize-none rounded-lg border border-navy-100 bg-white px-3 py-2 text-[13px] text-navy-800 focus:border-steel-500"
        />
      )}
    </div>
  );
}

/** List field as toggle chips: drafted suggestions arrive ON; tapping
 *  toggles keep/drop; an inline input appends the user's own. */
function ChipField({
  label, hint, items, onChange, addPlaceholder,
}: {
  label: string; hint: string; items: Item[];
  onChange: (items: Item[]) => void; addPlaceholder: string;
}) {
  const [text, setText] = useState("");
  const add = () => {
    const t = text.trim();
    if (!t) return;
    onChange([...items, { text: t, on: true }]);
    setText("");
  };
  return (
    <div>
      <label className="mb-1.5 block text-[11px] font-semibold uppercase tracking-[0.1em] text-navy-600">
        {label} <span className="font-normal normal-case text-subtle">({hint})</span>
      </label>
      <div className="flex flex-wrap items-center gap-1.5">
        {items.map((it, i) => (
          <button
            key={`${it.text}-${i}`}
            type="button"
            onClick={() => onChange(items.map((x, j) => (j === i ? { ...x, on: !x.on } : x)))}
            className={cn(
              "focus-ring inline-flex max-w-full items-center gap-1.5 rounded-full border px-3 py-1.5 text-left text-[12px] transition-colors",
              it.on
                ? "border-navy-800 bg-navy-800 text-white"
                : "border-navy-100 bg-white text-subtle line-through",
            )}
            title={it.on ? "Tap to drop" : "Tap to keep"}
          >
            <span className="truncate">{it.text}</span>
            {it.on ? <X size={11} className="shrink-0 opacity-60" /> : <Plus size={11} className="shrink-0" />}
          </button>
        ))}
        <span className="inline-flex items-center gap-1">
          <input
            value={text}
            onChange={(e) => setText(e.target.value)}
            onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); add(); } }}
            placeholder={addPlaceholder}
            className="focus-ring w-44 rounded-full border border-dashed border-navy-200 bg-white px-3 py-1.5 text-[12px] text-navy-800 focus:border-steel-500"
          />
        </span>
      </div>
    </div>
  );
}
