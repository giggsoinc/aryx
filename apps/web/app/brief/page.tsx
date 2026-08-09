"use client";

import { useCallback, useEffect, useState } from "react";
import {
  AlertCircle, CheckCircle2, FileText, Loader2, Sparkles,
} from "lucide-react";
import { Header } from "@/components/brand/Header";
import { api } from "@/lib/api";
import { useWorkspace } from "@/lib/workspace";
import type { Brief } from "@/lib/types";

function FieldGroup({
  label, name, value, onChange, rows = 1,
}: {
  label: string;
  name: string;
  value: string;
  onChange: (v: string) => void;
  rows?: number;
}) {
  return (
    <div>
      <label className="mb-1 block text-[11px] font-semibold uppercase tracking-[0.1em] text-navy-600">
        {label}
      </label>
      {rows === 1 ? (
        <input
          name={name}
          value={value}
          onChange={(e) => onChange(e.target.value)}
          className="focus-ring w-full rounded-lg border border-navy-100 bg-white px-3 py-2 text-[13px] text-navy-800 focus:border-steel-500"
        />
      ) : (
        <textarea
          name={name}
          rows={rows}
          value={value}
          onChange={(e) => onChange(e.target.value)}
          className="focus-ring w-full resize-none rounded-lg border border-navy-100 bg-white px-3 py-2 text-[13px] text-navy-800 focus:border-steel-500"
        />
      )}
    </div>
  );
}

function Readiness({ filled }: { filled: number }) {
  const labels = ["Generic NER", "Grounded", "Grounded", "Sharp", "Expert", "Expert"];
  const pct = Math.round((filled / 5) * 100);
  return (
    <div>
      <div className="mb-1 flex items-center justify-between">
        <span className="text-[11px] font-medium text-navy-600">Brief depth</span>
        <span className="text-[11px] font-semibold text-navy-800">{labels[filled]}</span>
      </div>
      <div className="h-1.5 overflow-hidden rounded-full bg-navy-100">
        <div
          className="h-full rounded-full bg-steel-500 transition-all"
          style={{ width: `${pct}%` }}
        />
      </div>
    </div>
  );
}

export default function BriefPage() {
  const { workspaceId, workspaces, setWorkspaceId, refresh } = useWorkspace();
  const [domain, setDomain] = useState("");
  const [aim, setAim] = useState("");
  const [objectives, setObjectives] = useState("");
  const [scope, setScope] = useState("");
  const [roles, setRoles] = useState("");

  const [seed, setSeed] = useState("");
  const [drafting, setDrafting] = useState(false);
  const [saving, setSaving] = useState(false);
  const [result, setResult] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const loadBrief = useCallback(() => {
    const ws = workspaces.find((w) => w.id === workspaceId);
    const b = (ws?.brief ?? {}) as Partial<Brief>;
    setDomain(b.domain ?? "");
    setAim(b.aim ?? "");
    setObjectives((b.objectives ?? []).join("\n"));
    setScope(b.scope ?? "");
    setRoles((b.roles ?? []).join("\n"));
  }, [workspaceId, workspaces]);

  // Re-load when workspace changes or workspaces list updates.
  useEffect(() => { loadBrief(); }, [loadBrief]);

  const filledCount = [domain, aim, objectives, scope, roles].filter(
    (v) => v.trim().length > 0,
  ).length;

  const draftBrief = async () => {
    if (!seed.trim()) return;
    setDrafting(true); setError(null); setResult(null);
    try {
      const res = await api.draftBrief(workspaceId, seed);
      const b = res.brief as Partial<Brief>;
      setDomain(b.domain ?? "");
      setAim(b.aim ?? "");
      setObjectives((b.objectives ?? []).join("\n"));
      setScope(b.scope ?? "");
      setRoles((b.roles ?? []).join("\n"));
      setResult("Brief drafted — review and save below.");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Draft failed");
    } finally {
      setDrafting(false);
    }
  };

  const saveBrief = async () => {
    setSaving(true); setError(null); setResult(null);
    try {
      const brief: Brief = {
        domain: domain.trim(),
        aim: aim.trim(),
        objectives: objectives.split("\n").map((l) => l.trim()).filter(Boolean),
        scope: scope.trim(),
        roles: roles.split("\n").map((l) => l.trim()).filter(Boolean),
      };
      await api.saveBrief(workspaceId, brief);
      await refresh();
      setResult("Brief saved — Aryx will use it for extraction.");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Save failed");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="flex min-h-screen flex-col">
      <Header workspaceId={workspaceId} onWorkspaceChange={setWorkspaceId} />
      <main className="flex-1 bg-canvas">
        <div className="mx-auto w-full max-w-4xl px-6 pb-8 pt-6">
        <div className="mb-6 flex items-center gap-2">
          <FileText size={20} className="text-steel-600" />
          <div>
            <h1 className="font-display text-2xl font-bold text-navy-900">Brief</h1>
            <p className="text-[13px] text-subtle">
              Five questions that ground every extraction. Skip any field and Aryx ingests generically.
            </p>
          </div>
        </div>

        {/* Feedback */}
        {error && (
          <div className="mb-4 flex items-center gap-2 rounded-lg border border-rose-200 bg-rose-50 px-3 py-2 text-[12px] text-rose-700">
            <AlertCircle size={13} /> {error}
          </div>
        )}
        {result && (
          <div className="mb-4 flex items-center gap-2 rounded-lg border border-emerald-200 bg-emerald-50 px-3 py-2 text-[12px] text-emerald-700">
            <CheckCircle2 size={13} /> {result}
          </div>
        )}

        {/* AI draft */}
        <div className="mb-6 rounded-xl border border-navy-100 bg-white p-5 shadow-soft">
          <h2 className="mb-1 text-[13px] font-bold text-navy-900">
            ✨ Start fast — describe it once
          </h2>
          <p className="mb-3 text-[12px] text-subtle">
            Type one sentence and Aryx drafts all five fields. Edit the draft before saving.
          </p>
          <div className="flex gap-2">
            <input
              value={seed}
              onChange={(e) => setSeed(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && draftBrief()}
              placeholder="e.g. Match support tickets to the right expert agent"
              className="focus-ring flex-1 rounded-lg border border-navy-100 bg-white px-3 py-2 text-[13px] text-navy-800 focus:border-steel-500"
            />
            <button
              type="button"
              onClick={draftBrief}
              disabled={!seed.trim() || drafting}
              className="focus-ring inline-flex items-center gap-1.5 rounded-lg bg-navy-800 px-4 py-2 text-[13px] font-semibold text-white hover:bg-navy-700 disabled:opacity-50"
            >
              {drafting ? (
                <><Loader2 size={13} className="animate-spin" /> Drafting…</>
              ) : (
                <><Sparkles size={13} /> Draft</>
              )}
            </button>
          </div>
        </div>

        {/* Five fields */}
        <div className="space-y-5 rounded-xl border border-navy-100 bg-white p-5 shadow-soft">
          <div className="text-[10px] font-bold uppercase tracking-[0.12em] text-navy-500">
            Review and edit
          </div>
          <div className="grid grid-cols-1 gap-5 sm:grid-cols-2">
            <FieldGroup
              label="1 · Domain of interest"
              name="domain"
              value={domain}
              onChange={setDomain}
            />
            <FieldGroup
              label="2 · Aim — purpose of the knowledge model"
              name="aim"
              value={aim}
              onChange={setAim}
              rows={3}
            />
            <FieldGroup
              label="3 · Objectives (one per line)"
              name="objectives"
              value={objectives}
              onChange={setObjectives}
              rows={4}
            />
            <FieldGroup
              label="5 · Participant roles (one per line)"
              name="roles"
              value={roles}
              onChange={setRoles}
              rows={4}
            />
          </div>
          <FieldGroup
            label="4 · Scope — what's IN, what's OUT"
            name="scope"
            value={scope}
            onChange={setScope}
            rows={2}
          />

          <Readiness filled={filledCount} />

          <button
            type="button"
            onClick={saveBrief}
            disabled={saving}
            className="focus-ring inline-flex w-full items-center justify-center gap-2 rounded-lg bg-navy-800 py-2.5 text-[13px] font-semibold text-white hover:bg-navy-700 disabled:opacity-50"
          >
            {saving ? (
              <><Loader2 size={13} className="animate-spin" /> Saving…</>
            ) : (
              "Save Brief"
            )}
          </button>
        </div>

        {/* Current brief summary */}
        {filledCount > 0 && (
          <div className="mt-5 rounded-xl border border-navy-100 bg-navy-50/40 p-5">
            <h3 className="mb-3 text-[11px] font-bold uppercase tracking-[0.1em] text-navy-500">
              Current brief
            </h3>
            <dl className="space-y-2 text-[13px]">
              {domain && <div><dt className="inline font-semibold text-navy-700">Domain: </dt><dd className="inline text-navy-600">{domain}</dd></div>}
              {aim && <div><dt className="inline font-semibold text-navy-700">Aim: </dt><dd className="inline text-navy-600">{aim}</dd></div>}
              {scope && <div><dt className="inline font-semibold text-navy-700">Scope: </dt><dd className="inline text-navy-600">{scope}</dd></div>}
              {objectives && <div><dt className="inline font-semibold text-navy-700">Objectives: </dt><dd className="inline text-navy-600">{objectives.split("\n").filter(Boolean).join(" · ")}</dd></div>}
              {roles && <div><dt className="inline font-semibold text-navy-700">Participants: </dt><dd className="inline text-navy-600">{roles.split("\n").filter(Boolean).join(" · ")}</dd></div>}
            </dl>
          </div>
        )}
        </div>
      </main>
    </div>
  );
}
