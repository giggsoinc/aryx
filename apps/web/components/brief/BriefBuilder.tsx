"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import {
  AlertCircle, CheckCircle2, FileText, Loader2, Plus, Sparkles, Upload, X,
} from "lucide-react";
import { api } from "@/lib/api";
import { cn } from "@/lib/cn";
import type { Brief } from "@/lib/types";

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

  // LLM reachability — cruise control needs a model. Reuses Settings' API.
  const [llmLabel, setLlmLabel] = useState<string | null>(null);
  const [llmDown, setLlmDown] = useState(false);
  useEffect(() => {
    api.getLlmConfig()
      .then((c) => setLlmLabel(`${c.provider} · ${c.answer_model}`))
      .catch(() => setLlmDown(true));
  }, []);

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

  const draft = async () => {
    const docText = docTexts.current.join("\n\n").slice(0, 12000);
    if (!seed.trim() && !docText) {
      setError("Drop a document or type one sentence first — Aryx needs something to work from.");
      return;
    }
    setDrafting(true); setError(null); setNotice(null);
    try {
      const res = await api.draftBrief(workspaceId, seed.trim(), docText);
      const b = res.brief;
      setDomain(b.domain ?? "");
      setAim(b.aim ?? "");
      setScope(b.scope ?? "");
      setObjectives(toItems(b.objectives));
      setRoles(toItems(b.roles));
      setQuestions(toItems(b.questions));
      setNotice("Drafted — tap chips to keep or drop, edit anything, then save.");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Draft failed");
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
      };
      await api.saveBrief(workspaceId, brief);
      onSubmitted(brief);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Save failed");
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
      {llmDown && (
        <div className="mb-4 flex items-center gap-2 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-[12px] text-amber-800">
          <AlertCircle size={13} className="shrink-0" />
          <span>
            Aryx needs a language model to draft your brief —{" "}
            <Link href="/settings" className="underline">choose one in Settings</Link>{" "}
            (Ollama is free and local), or fill the fields by hand below.
          </span>
        </div>
      )}
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

      {/* Feed Aryx: documents + one sentence */}
      <div className="mb-6 rounded-xl border border-navy-100 bg-white p-5 shadow-soft">
        <div className="mb-1 flex items-center justify-between">
          <h2 className="text-[13px] font-bold text-navy-900">
            ✨ Give Aryx something to read — it does the writing
          </h2>
          {llmLabel && (
            <span className="rounded-full bg-navy-50 px-2.5 py-0.5 text-[10px] font-medium text-navy-600">
              drafting with {llmLabel}
            </span>
          )}
        </div>
        <p className="mb-3 text-[12px] text-subtle">
          Drop documents that describe your world (an RFP, process doc,
          strategy deck…) and/or one sentence. Aryx pre-answers every question
          below — you just correct it.
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
            PDF · DOC · DOCX · PPT · PPTX — read to draft your brief, not ingested as data
          </span>
        </label>

        {docs.length > 0 && (
          <div className="mb-3 flex flex-wrap gap-1.5">
            {docs.map((d, i) => (
              <span key={`${d.filename}-${i}`} className={cn(
                "inline-flex items-center gap-1 rounded-lg px-2.5 py-1 text-[11px]",
                d.error ? "bg-rose-50 text-rose-700" : "bg-navy-50 text-navy-700",
              )}>
                <FileText size={11} />
                {d.filename}
                {d.error ? ` — ${d.error}` : " ✓"}
              </span>
            ))}
          </div>
        )}

        <div className="flex gap-2">
          <input
            value={seed}
            onChange={(e) => setSeed(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && draft()}
            placeholder="…and/or one sentence: e.g. Match support tickets to the right expert agent"
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

      {/* Review: six questions, pre-answered */}
      <div className="space-y-5 rounded-xl border border-navy-100 bg-white p-5 shadow-soft">
        <div className="text-[10px] font-bold uppercase tracking-[0.12em] text-navy-500">
          Confirm — every question is skippable
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

        {/* Depth meter */}
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
