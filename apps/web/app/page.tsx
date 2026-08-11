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
  const [resetTarget, setResetTarget] = useState<number | null>(null);
  const [resetting, setResetting] = useState(false);

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
                  <div className="mt-4 flex flex-wrap gap-2">
                    {isEmpty ? (
                      <button
                        type="button"
                        onClick={() => open(w.id, "/start")}
                        className="focus-ring rounded-lg border border-navy-100 bg-white px-3.5 py-1.5 text-[12px] font-semibold text-navy-800 hover:bg-navy-50"
                      >
                        Continue setup
                      </button>
                    ) : (
                      <>
                        <button
                          type="button"
                          onClick={() => open(w.id, "/ask")}
                          className="focus-ring rounded-lg bg-navy-800 px-3.5 py-1.5 text-[12px] font-semibold text-white hover:bg-navy-700"
                        >
                          Open
                        </button>
                        <button
                          type="button"
                          onClick={() => setResetTarget(w.id)}
                          className="focus-ring rounded-lg border border-rose-200 bg-white px-3.5 py-1.5 text-[12px] font-semibold text-rose-700 hover:bg-rose-50"
                        >
                          ↺ Reset &amp; re-ingest
                        </button>
                      </>
                    )}
                  </div>
                  {resetTarget === w.id && (
                    <div className="mt-3 rounded-lg border border-rose-200 bg-rose-50/60 p-3 text-[12px] text-navy-800">
                      <b>Reset “{w.name}”?</b> Deletes this workspace's{" "}
                      {o ? <>{o.landed_records.toLocaleString()} records, {o.entities.toLocaleString()} entities, {o.relationships.toLocaleString()} links</> : "data"}{" "}
                      from Postgres and its whole FalkorDB graph.
                      <b> Keeps</b> your Brief, model choice, ontology types, and corrections.
                      (Shared document chunks are left in place.)
                      <div className="mt-2 flex gap-2">
                        <button
                          type="button" disabled={resetting}
                          onClick={async () => {
                            setResetting(true);
                            try {
                              await api.resetWorkspaceData(w.id);
                              open(w.id, "/start");
                            } catch (e) {
                              setError(e instanceof Error ? e.message : "reset failed");
                              setResetting(false);
                              setResetTarget(null);
                            }
                          }}
                          className="focus-ring rounded-lg bg-rose-700 px-3 py-1 text-[12px] font-semibold text-white hover:bg-rose-800 disabled:opacity-50"
                        >
                          {resetting ? "Resetting…" : "Yes, reset & re-ingest"}
                        </button>
                        <button
                          type="button"
                          onClick={() => setResetTarget(null)}
                          className="focus-ring rounded-lg px-3 py-1 text-[12px] font-medium text-navy-700 hover:bg-navy-50"
                        >
                          Cancel
                        </button>
                      </div>
                    </div>
                  )}
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

  // Inline picker state. `expanded` reopens the picker after confirmation —
  // changing the model must never require a detour to Settings.
  const [expanded, setExpanded] = useState(false);
  const [provider, setProvider] = useState("");
  const [model, setModel] = useState("");
  const [apiKey, setApiKey] = useState("");
  const [ollamaModels, setOllamaModels] = useState<string[]>([]);
  useEffect(() => {
    if (cfg && !provider) {
      setProvider(cfg.provider);
      setModel(cfg.answer_model);
    }
  }, [cfg, provider]);
  const [modelsErr, setModelsErr] = useState<string | null>(null);
  const [modelsLoading, setModelsLoading] = useState(false);
  const fetchModels = useCallback(() => {
    setModelsLoading(true); setModelsErr(null);
    api.listLlmModels()
      .then((r) => {
        setOllamaModels(r.models);
        if (!r.ok || r.models.length === 0) {
          setModelsErr(r.error || "no local models found — is Ollama running?");
        }
      })
      .catch((e) => setModelsErr(e instanceof Error ? e.message : "Ollama unreachable"))
      .finally(() => setModelsLoading(false));
  }, []);
  // Fetch on mount AND every time the provider flips to Ollama — the list
  // must appear the moment the user switches, not only if it loaded once.
  useEffect(() => { fetchModels(); }, [fetchModels]);
  useEffect(() => { if (provider === "ollama") fetchModels(); }, [provider, fetchModels]);
  // Keep the saved value honest: once the local list arrives, a leftover
  // cloud model name (e.g. gemini-flash) must not be submitted as Ollama's.
  useEffect(() => {
    if (provider === "ollama" && ollamaModels.length > 0
        && !ollamaModels.includes(model)) {
      setModel(ollamaModels[0]);
    }
  }, [provider, ollamaModels, model]);

  const save = async () => {
    setBusy(true);
    try {
      // Persist → server echoes back the ACTIVE config; render only that,
      // never a cached value — so the bar can't show a stale provider.
      const next = await api.setLlmConfig({
        provider, answer_model: model, menial_model: model,
        ...(apiKey ? { api_key: apiKey } : {}),
        ...(provider === "ollama" ? {} : {}),
      });
      setCfg(next);
      setApiKey("");
      setExpanded(false);
      load();
    } finally {
      setBusy(false);
    }
  };

  if (!cfg) return null;

  const dot = (
    <span className={cn(
      "inline-block size-2 shrink-0 rounded-full",
      health == null ? "bg-navy-200" : health.ok ? "bg-emerald-500" : "bg-amber-500",
    )} />
  );

  if (cfg.confirmed && !expanded) {
    return (
      <div className="mb-5 flex flex-wrap items-center gap-2 text-[12px] text-subtle">
        {dot}
        <Cpu size={12} />
        Model: <b className="text-navy-800">{cfg.provider} · {cfg.answer_model}</b>
        <span className="rounded-full bg-navy-50 px-2 py-0.5 text-[10px]">set by you</span>
        {health && !health.ok && <span className="text-amber-700">— {health.detail}</span>}
        <button
          type="button"
          onClick={() => setExpanded(true)}
          className="focus-ring underline hover:text-navy-700"
        >
          change
        </button>
      </div>
    );
  }

  return (
    <div className="mb-6 rounded-xl border border-steel-500/40 bg-white p-4 shadow-soft">
      <div className="mb-1 flex items-center gap-2 text-[13px] text-navy-800">
        <Cpu size={15} className="text-steel-600" />
        <b>Choose your language model first</b> — everything Aryx extracts runs through it.
      </div>
      <div className="mb-3 text-[11px]">
        <span className={cn(
          "rounded-full px-2 py-0.5 font-medium",
          cfg.confirmed ? "bg-navy-50 text-navy-600" : "bg-amber-50 text-amber-700",
        )}>
          {cfg.confirmed
            ? `current: ${cfg.provider} · ${cfg.answer_model} (set by you)`
            : "source: environment file — not yet confirmed by you"}
        </span>
        {health && (
          <span className={cn("ml-2", health.ok ? "text-emerald-700" : "text-amber-700")}>
            {cfg.provider} · {cfg.answer_model} is {health.ok ? "ready" : health.detail}
          </span>
        )}
      </div>
      <div className="flex flex-wrap items-center gap-2">
        <select
          value={provider}
          onChange={(e) => { setProvider(e.target.value); if (e.target.value === "ollama" && ollamaModels[0]) setModel(ollamaModels[0]); }}
          className="focus-ring rounded-lg border border-navy-100 bg-white px-2.5 py-1.5 text-[12px] text-navy-800"
        >
          <option value="ollama">Ollama (local, free) — default</option>
          <option value="anthropic">Anthropic</option>
          <option value="gemini">Gemini</option>
          <option value="openai">OpenAI-compatible</option>
          <option value="grok">Grok (xAI)</option>
        </select>
        {provider === "ollama" && modelsLoading ? (
          <span className="inline-flex items-center gap-1.5 text-[12px] text-subtle">
            <Loader2 size={12} className="animate-spin" /> listing local models…
          </span>
        ) : provider === "ollama" && ollamaModels.length > 0 ? (
          <select
            value={ollamaModels.includes(model) ? model : ollamaModels[0]}
            onChange={(e) => setModel(e.target.value)}
            className="focus-ring rounded-lg border border-navy-100 bg-white px-2.5 py-1.5 text-[12px] text-navy-800"
          >
            {ollamaModels.map((m) => <option key={m} value={m}>{m} (installed)</option>)}
          </select>
        ) : (
          <input
            value={model}
            onChange={(e) => setModel(e.target.value)}
            placeholder="model name"
            className="focus-ring w-44 rounded-lg border border-navy-100 bg-white px-2.5 py-1.5 text-[12px] text-navy-800"
          />
        )}
        {provider !== "ollama" && (
          <input
            type="password"
            value={apiKey}
            onChange={(e) => setApiKey(e.target.value)}
            placeholder="API key"
            className="focus-ring w-48 rounded-lg border border-navy-100 bg-white px-2.5 py-1.5 text-[12px] text-navy-800"
          />
        )}
        <button
          type="button" onClick={save}
          disabled={busy || !model.trim() || (provider !== "ollama" && !apiKey && !cfg.api_key_set)}
          className="focus-ring inline-flex items-center gap-1.5 rounded-lg bg-navy-800 px-3.5 py-1.5 text-[12px] font-semibold text-white hover:bg-navy-700 disabled:opacity-50"
        >
          {busy ? <Loader2 size={12} className="animate-spin" /> : null}
          Use this model
        </button>
        <Link href="/settings" className="text-[11px] text-subtle underline hover:text-navy-700">
          all options
        </Link>
      </div>
      {provider === "ollama" && modelsErr && !modelsLoading && (
        <div className="mt-2 flex items-center gap-2 text-[11px] text-amber-700">
          <span>⚠ {modelsErr}</span>
          <button
            type="button" onClick={fetchModels}
            className="focus-ring rounded border border-amber-300 bg-white px-1.5 py-0.5 text-[10px] font-semibold hover:bg-amber-50"
          >
            Retry
          </button>
        </div>
      )}
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
