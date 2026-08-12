"use client";

import { useCallback, useEffect, useState } from "react";
import { Loader2, Save, KeyRound } from "lucide-react";
import { api } from "@/lib/api";
import type { LlmConfig } from "@/lib/types";
import { cn } from "@/lib/cn";
import {
  SETTINGS_PROVIDER_OPTIONS,
  defaultSampleFor,
  samplesFor,
} from "@/lib/llmPresets";

/**
 * Model provider settings — FastAPI GET/POST llm config.
 * Keys stay in API process memory (not written to disk/git).
 * Ollama: live installed-model dropdowns; cloud: sample models + Custom.
 */
export function LlmSettings() {
  const [cfg, setCfg] = useState<LlmConfig | null>(null);
  const [provider, setProvider] = useState("ollama");
  const [menial, setMenial] = useState("");
  const [answer, setAnswer] = useState("");
  const [endpoint, setEndpoint] = useState("");
  const [apiKey, setApiKey] = useState("");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [ok, setOk] = useState<string | null>(null);
  const [customMenial, setCustomMenial] = useState(false);
  const [customAnswer, setCustomAnswer] = useState(false);
  const [version, setVersion] = useState<{
    product: string; version: string; api: string;
    python: string; platform: string;
  } | null>(null);

  const [localModels, setLocalModels] = useState<string[]>([]);
  const [modelsErr, setModelsErr] = useState<string | null>(null);
  const [modelsLoading, setModelsLoading] = useState(false);

  const fetchModels = useCallback(() => {
    setModelsLoading(true); setModelsErr(null);
    api.listLlmModels()
      .then((r) => {
        setLocalModels(r.models);
        if (!r.ok || r.models.length === 0) {
          setModelsErr(r.error || "No local models found — is Ollama running?");
        }
      })
      .catch((e) => setModelsErr(e instanceof Error ? e.message : "Ollama unreachable"))
      .finally(() => setModelsLoading(false));
  }, []);

  useEffect(() => { fetchModels(); }, [fetchModels]);
  useEffect(() => { if (provider === "ollama") fetchModels(); }, [provider, fetchModels]);

  useEffect(() => {
    if (provider === "ollama" && localModels.length > 0) {
      if (!localModels.includes(menial)) setMenial(localModels[0]);
      if (!localModels.includes(answer)) setAnswer(localModels[0]);
      setCustomMenial(false);
      setCustomAnswer(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [provider, localModels]);

  // Poll while Ollama list is empty (model pull in progress).
  useEffect(() => {
    if (provider !== "ollama" || localModels.length > 0) return;
    const t = setInterval(fetchModels, 10000);
    return () => clearInterval(t);
  }, [provider, localModels.length, fetchModels]);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const c = await api.getLlmConfig();
      setCfg(c);
      setProvider(c.provider || "ollama");
      setMenial(c.menial_model || "");
      setAnswer(c.answer_model || "");
      setEndpoint(c.endpoint || "");
      setCustomMenial(false);
      setCustomAnswer(false);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { void load(); }, [load]);
  useEffect(() => {
    api.getVersion().then(setVersion).catch(() => setVersion(null));
  }, []);

  const onProviderChange = (id: string) => {
    setProvider(id);
    const preset = SETTINGS_PROVIDER_OPTIONS.find((p) => p.id === id);
    if (preset?.endpoint !== undefined) setEndpoint(preset.endpoint);
    setOk(null);
    setCustomMenial(false);
    setCustomAnswer(false);
    if (id === "ollama") {
      setEndpoint(preset?.endpoint || "http://ollama:11434");
      if (localModels[0]) {
        setMenial(localModels[0]);
        setAnswer(localModels[0]);
      }
      fetchModels();
    } else {
      const sample = defaultSampleFor(id);
      if (sample) {
        setMenial(sample);
        setAnswer(sample);
      }
    }
  };

  const save = async () => {
    setSaving(true);
    setError(null);
    setOk(null);
    try {
      const body: Record<string, string> = {
        provider,
        menial_model: menial,
        answer_model: answer,
        // Always send endpoint — Ollama switch must overwrite a cloud URL.
        endpoint: provider === "ollama"
          ? (endpoint || "http://ollama:11434")
          : endpoint,
      };
      if (apiKey.trim()) body.api_key = apiKey.trim();
      const next = await api.setLlmConfig(body);
      setCfg(next);
      setApiKey("");
      setOk(
        `Saved. Ask uses ${next.provider} · ${next.answer_model}` +
          (next.api_key_set ? " · key set" : " · no key"),
      );
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setSaving(false);
    }
  };

  if (loading) {
    return (
      <div className="flex items-center gap-2 text-sm text-navy-500">
        <Loader2 className="animate-spin" size={16} /> Loading LLM config…
      </div>
    );
  }

  const preset = SETTINGS_PROVIDER_OPTIONS.find((p) => p.id === provider);
  const cloudSamples = samplesFor(provider);

  const modelField = (
    label: string,
    value: string,
    setValue: (v: string) => void,
    custom: boolean,
    setCustom: (v: boolean) => void,
    placeholder: string,
  ) => (
    <label className="block text-sm font-medium text-navy-800">
      {label}
      {provider === "ollama" && modelsLoading && localModels.length === 0 ? (
        <span className="mt-1 flex items-center gap-1.5 text-xs text-navy-500">
          <Loader2 className="animate-spin" size={12} /> Listing installed models…
        </span>
      ) : provider === "ollama" && localModels.length > 0 ? (
        <select
          className="mt-1 w-full rounded-md border border-navy-200 bg-white px-3 py-2 font-mono text-sm"
          value={localModels.includes(value) ? value : localModels[0]}
          onChange={(e) => setValue(e.target.value)}
        >
          {localModels.map((m) => (
            <option key={m} value={m}>{m} (installed)</option>
          ))}
        </select>
      ) : provider === "ollama" ? (
        <input
          className="mt-1 w-full rounded-md border border-navy-200 px-3 py-2 font-mono text-sm"
          value={value}
          onChange={(e) => setValue(e.target.value)}
          placeholder={placeholder}
        />
      ) : custom || cloudSamples.length === 0 ? (
        <input
          className="mt-1 w-full rounded-md border border-navy-200 px-3 py-2 font-mono text-sm"
          value={value}
          onChange={(e) => setValue(e.target.value)}
          placeholder={placeholder}
        />
      ) : (
        <select
          className="mt-1 w-full rounded-md border border-navy-200 bg-white px-3 py-2 font-mono text-sm"
          value={cloudSamples.includes(value) ? value : cloudSamples[0]}
          onChange={(e) => {
            if (e.target.value === "__custom__") {
              setCustom(true);
              setValue("");
            } else {
              setValue(e.target.value);
            }
          }}
        >
          {cloudSamples.map((m) => (
            <option key={m} value={m}>{m}</option>
          ))}
          <option value="__custom__">Custom…</option>
        </select>
      )}
    </label>
  );

  return (
    <div className="mx-auto max-w-2xl space-y-6 px-6 py-8">
      <div>
        <h1 className="font-display text-2xl font-semibold text-navy-900">
          Settings — Model provider
        </h1>
        <p className="mt-1 text-sm text-navy-500">
          Engine for Ask and ingest. Local Ollama needs no key; cloud providers
          need an API key. Changes apply live (no restart). Keys stay in API
          memory only — not written to disk or git.
        </p>
      </div>

      {cfg && (
        <div className="rounded-lg border border-navy-100 bg-white px-4 py-3 text-sm text-navy-700">
          Active: <strong>{cfg.provider}</strong>
          {" · "}
          <code className="text-xs">{cfg.answer_model}</code>
          {" · "}
          {cfg.api_key_set ? (
            <span className="inline-flex items-center gap-1 text-emerald-700">
              <KeyRound size={12} /> key set
            </span>
          ) : (
            <span className="text-navy-400">no key (local ok)</span>
          )}
        </div>
      )}

      <div className="space-y-4 rounded-xl border border-navy-100 bg-white p-5 shadow-sm">
        <label className="block text-sm font-medium text-navy-800">
          Provider
          <select
            className="mt-1 w-full rounded-md border border-navy-200 px-3 py-2 text-sm"
            value={provider}
            onChange={(e) => onProviderChange(e.target.value)}
          >
            {SETTINGS_PROVIDER_OPTIONS.map((p) => (
              <option key={p.id} value={p.id}>{p.label}</option>
            ))}
            {!SETTINGS_PROVIDER_OPTIONS.some((p) => p.id === provider) && (
              <option value={provider}>{provider} (custom)</option>
            )}
          </select>
        </label>
        {preset?.hint && (
          <p className="text-xs text-navy-400">{preset.hint}</p>
        )}

        <div className="grid gap-4 sm:grid-cols-2">
          {modelField(
            "Fast model (extraction)",
            menial, setMenial, customMenial, setCustomMenial,
            "e.g. qwen3.5:0.8b",
          )}
          {modelField(
            "Answer model",
            answer, setAnswer, customAnswer, setCustomAnswer,
            "e.g. grok-3 / gemini-2.0-flash",
          )}
        </div>

        {provider === "ollama" && (modelsErr || modelsLoading) && (
          <div className="flex flex-wrap items-center gap-2 text-xs text-amber-700">
            {modelsLoading && localModels.length === 0
              ? "Listing local models…"
              : modelsErr ? `⚠ ${modelsErr}` : null}
            {!modelsLoading && modelsErr && (
              <button
                type="button" onClick={fetchModels}
                className="rounded border border-amber-300 bg-white px-1.5 py-0.5 text-[10px] font-semibold hover:bg-amber-50"
              >
                Retry
              </button>
            )}
            {modelsErr && !modelsLoading && (
              <span className="text-navy-500">You can still type a custom model name above.</span>
            )}
          </div>
        )}

        <label className="block text-sm font-medium text-navy-800">
          Endpoint / base URL
          <input
            className="mt-1 w-full rounded-md border border-navy-200 px-3 py-2 font-mono text-sm"
            value={endpoint}
            onChange={(e) => setEndpoint(e.target.value)}
            placeholder="https://…"
          />
        </label>

        <label className="block text-sm font-medium text-navy-800">
          API key
          <input
            type="password"
            autoComplete="off"
            className="mt-1 w-full rounded-md border border-navy-200 px-3 py-2 font-mono text-sm"
            value={apiKey}
            onChange={(e) => setApiKey(e.target.value)}
            placeholder={
              cfg?.api_key_set
                ? "Leave blank to keep existing key"
                : "Required for cloud providers"
            }
          />
        </label>

        <div className="flex items-center gap-3 pt-1">
          <button
            type="button"
            onClick={() => void save()}
            disabled={saving}
            className={cn(
              "inline-flex items-center gap-2 rounded-md bg-navy-900 px-4 py-2",
              "text-sm font-medium text-white hover:bg-navy-800 disabled:opacity-60",
            )}
          >
            {saving ? <Loader2 className="animate-spin" size={14} /> : <Save size={14} />}
            Save
          </button>
          <button
            type="button"
            onClick={() => void load()}
            className="text-sm text-navy-500 underline-offset-2 hover:underline"
          >
            Reload
          </button>
        </div>

        {error && (
          <p className="text-sm text-red-600" role="alert">{error}</p>
        )}
        {ok && (
          <p className="text-sm text-emerald-700" role="status">{ok}</p>
        )}
      </div>

      <p className="text-xs text-navy-400">
        Boot defaults also come from env:{" "}
        <code>ARYX_LLM_PROVIDER</code>, <code>ARYX_LLM_BASE_URL</code>,{" "}
        <code>ARYX_LLM_MENIAL_MODEL</code>, <code>ARYX_LLM_REASON_MODEL</code>,{" "}
        <code>ARYX_LLM_API_KEY</code>.
      </p>

      <div className="rounded-xl border border-navy-100 bg-navy-50/60 px-4 py-3 text-[12px] text-navy-700">
        <div className="text-[10px] font-bold uppercase tracking-[0.12em] text-navy-500">
          Software
        </div>
        {version ? (
          <dl className="mt-2 grid grid-cols-[auto_1fr] gap-x-3 gap-y-1 font-mono text-[11px]">
            <dt className="text-navy-500">Product</dt>
            <dd>{version.product}</dd>
            <dt className="text-navy-500">Version</dt>
            <dd className="font-semibold text-navy-900">{version.version}</dd>
            <dt className="text-navy-500">API</dt>
            <dd>{version.api}</dd>
            <dt className="text-navy-500">Python</dt>
            <dd>{version.python}</dd>
            <dt className="text-navy-500">Platform</dt>
            <dd className="break-all">{version.platform}</dd>
          </dl>
        ) : (
          <p className="mt-1 text-[11px] text-subtle">
            Version unavailable — is the API running? Expected Aryx Lite 1.7.0+.
          </p>
        )}
      </div>
    </div>
  );
}
