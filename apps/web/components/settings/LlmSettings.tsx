"use client";

import { useCallback, useEffect, useState } from "react";
import { Loader2, Save, KeyRound } from "lucide-react";
import { api } from "@/lib/api";
import type { LlmConfig } from "@/lib/types";
import { cn } from "@/lib/cn";

/** Provider presets — same wire contract as the retired Streamlit Settings. */
const PROVIDERS: {
  id: string;
  label: string;
  endpoint: string;
  hint: string;
}[] = [
  {
    id: "ollama",
    label: "Local (Ollama)",
    endpoint: "http://ollama:11434",
    hint: "No API key. Use host.docker.internal or localhost if Ollama runs on the host.",
  },
  {
    id: "anthropic",
    label: "Claude (Anthropic)",
    endpoint: "",
    hint: "Uses the Anthropic SDK. Model ids like claude-sonnet-4-20250514.",
  },
  {
    id: "openai",
    label: "OpenAI / compatible",
    endpoint: "https://api.openai.com/v1",
    hint: "Any OpenAI-compatible /chat/completions base URL.",
  },
  {
    id: "google",
    label: "Gemini (OpenAI-compatible)",
    endpoint:
      "https://generativelanguage.googleapis.com/v1beta/openai",
    hint: "Google AI Studio key; Gemini model ids via OpenAI-compat path.",
  },
  {
    id: "xai",
    label: "Grok (xAI)",
    endpoint: "https://api.x.ai/v1",
    hint: "xAI API key; model ids like grok-3.",
  },
];

/**
 * Model provider settings — talks only to FastAPI GET/POST llm config.
 * Keys stay in API process memory (not written to disk/git).
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
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const onProviderChange = (id: string) => {
    setProvider(id);
    const preset = PROVIDERS.find((p) => p.id === id);
    if (preset && preset.endpoint !== undefined) {
      setEndpoint(preset.endpoint);
    }
    setOk(null);
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
        endpoint,
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

  const preset = PROVIDERS.find((p) => p.id === provider);

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
        <div
          className={cn(
            "rounded-lg border px-4 py-3 text-sm",
            "border-navy-100 bg-white text-navy-700",
          )}
        >
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
            {PROVIDERS.map((p) => (
              <option key={p.id} value={p.id}>
                {p.label}
              </option>
            ))}
            {!PROVIDERS.some((p) => p.id === provider) && (
              <option value={provider}>{provider} (custom)</option>
            )}
          </select>
        </label>
        {preset && (
          <p className="text-xs text-navy-400">{preset.hint}</p>
        )}

        <div className="grid gap-4 sm:grid-cols-2">
          <label className="block text-sm font-medium text-navy-800">
            Fast model (extraction)
            <input
              className="mt-1 w-full rounded-md border border-navy-200 px-3 py-2 font-mono text-sm"
              value={menial}
              onChange={(e) => setMenial(e.target.value)}
              placeholder="e.g. qwen3.5:0.8b"
            />
          </label>
          <label className="block text-sm font-medium text-navy-800">
            Answer model
            <input
              className="mt-1 w-full rounded-md border border-navy-200 px-3 py-2 font-mono text-sm"
              value={answer}
              onChange={(e) => setAnswer(e.target.value)}
              placeholder="e.g. grok-3 / gemini-2.0-flash"
            />
          </label>
        </div>

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
            {saving ? (
              <Loader2 className="animate-spin" size={14} />
            ) : (
              <Save size={14} />
            )}
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
          <p className="text-sm text-red-600" role="alert">
            {error}
          </p>
        )}
        {ok && (
          <p className="text-sm text-emerald-700" role="status">
            {ok}
          </p>
        )}
      </div>

      <p className="text-xs text-navy-400">
        Boot defaults also come from env:{" "}
        <code>ARYX_LLM_PROVIDER</code>, <code>ARYX_LLM_BASE_URL</code>,{" "}
        <code>ARYX_LLM_MENIAL_MODEL</code>, <code>ARYX_LLM_REASON_MODEL</code>,{" "}
        <code>ARYX_LLM_API_KEY</code>.
      </p>
    </div>
  );
}
