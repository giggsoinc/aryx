"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { Cpu, FileText, Loader2, Plus } from "lucide-react";
import { Header } from "@/components/brand/Header";
import { api } from "@/lib/api";
import { cn } from "@/lib/cn";
import { useWorkspace } from "@/lib/workspace";
import type { LlmConfig } from "@/lib/types";

interface Overview {
  id: number;
  entities: number;
  relationships: number;
  landed_records: number;
  running_jobs: number;
}

/** Landing home — the first thing a user sees on the domain. Lists every
 *  workspace with its vitals; blank slate routes straight into the guided
 *  wizard. Ask lives at /ask. */
export default function HomePage() {
  const router = useRouter();
  const { ready, workspaceId, workspaces, setWorkspaceId, refresh } =
    useWorkspaceCompat();
  const [overview, setOverview] = useState<Map<number, Overview>>(new Map());
  const [creating, setCreating] = useState(false);
  const [name, setName] = useState("");
  const [desc, setDesc] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.workspaceOverview()
      .then((rows) => setOverview(new Map(rows.map((r) => [r.id, r]))))
      .catch(() => {});
  }, [workspaces]);

  // Blank slate → no detour, straight into onboarding.
  useEffect(() => {
    if (ready && workspaces.length === 0) router.replace("/start");
  }, [ready, workspaces.length, router]);

  const open = (id: number, href: string) => {
    setWorkspaceId(id);
    router.push(href);
  };

  const create = async () => {
    if (!name.trim()) return;
    setBusy(true); setError(null);
    try {
      const w = await api.createWorkspace(name.trim(), desc.trim());
      await refresh();
      open(w.id, "/start");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Create failed");
      setBusy(false);
    }
  };

  return (
    <div className="flex min-h-screen flex-col">
      <Header workspaceId={workspaceId} onWorkspaceChange={setWorkspaceId} />
      <main className="flex-1 bg-canvas">
        <div className="mx-auto w-full max-w-5xl px-6 pb-10 pt-8">
          <ModelGate />
          <h1 className="font-display text-[1.7rem] font-bold text-navy-900">
            Your workspaces
          </h1>
          <p className="mb-6 mt-1 text-[13px] text-subtle">
            Pick up where you left off, or start a new knowledge model.
          </p>

          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {/* New workspace card */}
            <div className={
              "flex flex-col justify-center rounded-xl border-2 border-dashed " +
              "border-steel-400/70 bg-white/60 p-5 transition-colors hover:border-steel-500"
            }>
              {!creating ? (
                <button
                  type="button"
                  onClick={() => setCreating(true)}
                  className="focus-ring flex h-full min-h-[96px] flex-col items-center justify-center gap-1 rounded-lg text-steel-600"
                >
                  <span className="flex items-center gap-1.5 text-[14px] font-semibold">
                    <Plus size={15} /> New workspace
                  </span>
                  <span className="text-[11px] text-subtle">guided setup · ~3 minutes</span>
                </button>
              ) : (
                <div className="space-y-2">
                  <input
                    autoFocus
                    value={name}
                    onChange={(e) => setName(e.target.value)}
                    onKeyDown={(e) => e.key === "Enter" && create()}
                    placeholder="Name (e.g. Supply Chain Risk)"
                    className="focus-ring w-full rounded-lg border border-navy-100 bg-white px-3 py-2 text-[13px] text-navy-800 focus:border-steel-500"
                  />
                  <input
                    value={desc}
                    onChange={(e) => setDesc(e.target.value)}
                    onKeyDown={(e) => e.key === "Enter" && create()}
                    placeholder="What it's for (optional)"
                    className="focus-ring w-full rounded-lg border border-navy-100 bg-white px-3 py-2 text-[12px] text-navy-800 focus:border-steel-500"
                  />
                  {error && (
                    <div className="rounded-md border border-rose-200 bg-rose-50 px-2.5 py-1.5 text-[11px] text-rose-700">
                      {error}
                    </div>
                  )}
                  <div className="flex justify-end gap-2">
                    <button
                      type="button"
                      onClick={() => { setCreating(false); setError(null); }}
                      className="focus-ring rounded-lg px-2.5 py-1.5 text-[12px] font-medium text-navy-700 hover:bg-navy-50"
                    >
                      Cancel
                    </button>
                    <button
                      type="button"
                      onClick={create}
                      disabled={!name.trim() || busy}
                      className="focus-ring inline-flex items-center gap-1.5 rounded-lg bg-navy-800 px-3 py-1.5 text-[12px] font-semibold text-white hover:bg-navy-700 disabled:opacity-50"
                    >
                      {busy ? <Loader2 size={12} className="animate-spin" /> : <Plus size={12} />}
                      Create &amp; set up
                    </button>
                  </div>
                </div>
              )}
            </div>

            {workspaces.map((w) => {
              const o = overview.get(w.id);
              const hasBrief = !!w.brief && Object.values(w.brief).some(
                (v) => (Array.isArray(v) ? v.length > 0 : String(v ?? "").trim() !== ""),
              );
              const isEmpty = (o?.entities ?? 0) === 0;
              return (
                <div key={w.id} className="flex flex-col rounded-xl border border-navy-100 bg-white p-5 shadow-soft">
                  <div className="flex items-start justify-between">
                    <h3 className="text-[15px] font-bold text-navy-900">{w.name}</h3>
                    {w.id === workspaceId && (
                      <span className="mt-1 size-2 rounded-full bg-steel-500" title="Active" />
                    )}
                  </div>
                  <div className="mt-1 text-[12px] text-subtle">
                    {o
                      ? `${o.entities.toLocaleString()} entities · ${o.relationships.toLocaleString()} links` +
                        (o.running_jobs > 0 ? ` · ${o.running_jobs} job running` : "")
                      : w.description || "—"}
                  </div>
                  <div className="mt-3 flex flex-wrap gap-1.5">
                    <span className={
                      "inline-flex items-center gap-1 rounded-full px-2.5 py-0.5 text-[10px] font-medium " +
                      (hasBrief
                        ? "bg-emerald-50 text-emerald-700"
                        : "bg-amber-50 text-amber-700")
                    }>
                      <FileText size={10} /> {hasBrief ? "Brief ✓" : "No brief"}
                    </span>
                  </div>
                  <div className="mt-4 flex gap-2">
                    {isEmpty ? (
                      <button
                        type="button"
                        onClick={() => open(w.id, "/start")}
                        className="focus-ring rounded-lg border border-navy-100 bg-white px-3.5 py-1.5 text-[12px] font-semibold text-navy-800 hover:bg-navy-50"
                      >
                        Continue setup
                      </button>
                    ) : (
                      <button
                        type="button"
                        onClick={() => open(w.id, "/ask")}
                        className="focus-ring rounded-lg bg-navy-800 px-3.5 py-1.5 text-[12px] font-semibold text-white hover:bg-navy-700"
                      >
                        Open
                      </button>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      </main>
    </div>
  );
}

/** THE first decision on the first screen: which language model runs this
 *  workspace. Defaults to Ollama; nothing downstream should run on an
 *  unconfirmed default. Confirming persists server-side (survives restarts). */
function ModelGate() {
  const [cfg, setCfg] = useState<LlmConfig | null>(null);
  const [health, setHealth] = useState<{ ok: boolean; detail: string } | null>(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(() => {
    api.getLlmConfig().then(setCfg).catch(() => {});
    api.getLlmHealth()
      .then((h) => setHealth({ ok: h.ok, detail: h.detail }))
      .catch(() => setHealth({ ok: false, detail: "API not reachable" }));
  }, []);
  useEffect(() => { load(); }, [load]);

  const confirmDefault = async () => {
    if (!cfg) return;
    setBusy(true);
    try {
      // Persisting the current (Ollama-default or env-set) config marks it
      // as the user's explicit choice.
      setCfg(await api.setLlmConfig({
        provider: cfg.provider, menial_model: cfg.menial_model,
        answer_model: cfg.answer_model, endpoint: cfg.endpoint,
      }));
    } finally {
      setBusy(false);
    }
  };

  if (!cfg) return null;

  if (cfg.confirmed) {
    return (
      <div className="mb-5 flex items-center gap-2 text-[12px] text-subtle">
        <span className={cn(
          "inline-block size-2 rounded-full",
          health == null ? "bg-navy-200" : health.ok ? "bg-emerald-500" : "bg-amber-500",
        )} />
        <Cpu size={12} />
        Model: <b className="text-navy-800">{cfg.provider} · {cfg.answer_model}</b>
        {health && !health.ok && <span className="text-amber-700">— {health.detail}</span>}
        <Link href="/settings" className="underline hover:text-navy-700">change</Link>
      </div>
    );
  }

  return (
    <div className="mb-6 rounded-xl border border-steel-500/40 bg-white p-4 shadow-soft">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-2 text-[13px] text-navy-800">
          <Cpu size={15} className="text-steel-600" />
          <span>
            <b>Choose your language model first</b> — everything Aryx extracts
            runs through it. Current default:{" "}
            <b>{cfg.provider} · {cfg.answer_model}</b>
            {health && (
              <span className={health.ok ? "text-emerald-700" : "text-amber-700"}>
                {" "}({health.ok ? "ready" : health.detail})
              </span>
            )}
          </span>
        </div>
        <div className="flex shrink-0 gap-2">
          <Link
            href="/settings"
            className="focus-ring rounded-lg border border-navy-100 bg-white px-3.5 py-1.5 text-[12px] font-semibold text-navy-800 hover:bg-navy-50"
          >
            Choose a different model
          </Link>
          <button
            type="button" onClick={confirmDefault} disabled={busy}
            className="focus-ring inline-flex items-center gap-1.5 rounded-lg bg-navy-800 px-3.5 py-1.5 text-[12px] font-semibold text-white hover:bg-navy-700 disabled:opacity-50"
          >
            {busy ? <Loader2 size={12} className="animate-spin" /> : null}
            Use this model
          </button>
        </div>
      </div>
    </div>
  );
}

/** useWorkspace doesn't expose a readiness flag; derive one so the
 *  blank-slate redirect never fires before the first workspace fetch. */
function useWorkspaceCompat() {
  const ws = useWorkspace();
  const [ready, setReady] = useState(false);
  useEffect(() => {
    // listWorkspaces resolves (or fails) shortly after mount; either way a
    // second tick with data present means the redirect decision is safe.
    const t = setTimeout(() => setReady(true), 1500);
    if (ws.workspaces.length > 0) setReady(true);
    return () => clearTimeout(t);
  }, [ws.workspaces.length]);
  return { ...ws, ready };
}
