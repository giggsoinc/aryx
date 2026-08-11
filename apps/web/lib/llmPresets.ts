/** Shared LLM provider UX for Home ModelGate and Settings (OSS Lite). */

export type LlmProviderId =
  | "ollama"
  | "anthropic"
  | "gemini"
  | "openai"
  | "grok"
  | "google"
  | "xai";

export interface LlmProviderOption {
  id: string;
  label: string;
  /** Suggested model ids (empty for Ollama — use live /api/tags list). */
  samples: string[];
  /** Default API base URL for Settings. */
  endpoint?: string;
  hint?: string;
}

/** Home ModelGate options (ids historically used by Home). */
export const LLM_PROVIDER_OPTIONS: LlmProviderOption[] = [
  {
    id: "ollama",
    label: "Ollama (local, free) — default",
    samples: [],
    endpoint: "http://ollama:11434",
    hint: "No API key. Lists models from local Ollama tags.",
  },
  {
    id: "anthropic",
    label: "Anthropic",
    samples: ["claude-sonnet-4-20250514", "claude-3-5-haiku-latest"],
    endpoint: "",
    hint: "Anthropic SDK. Model ids like claude-sonnet-4-20250514.",
  },
  {
    id: "gemini",
    label: "Gemini",
    samples: ["gemini-2.0-flash", "gemini-1.5-pro"],
    endpoint: "https://generativelanguage.googleapis.com/v1beta/openai",
    hint: "Google AI Studio / Gemini model ids.",
  },
  {
    id: "openai",
    label: "OpenAI-compatible",
    samples: ["gpt-4o", "gpt-4o-mini"],
    endpoint: "https://api.openai.com/v1",
    hint: "Any OpenAI-compatible /chat/completions base URL.",
  },
  {
    id: "grok",
    label: "Grok (xAI)",
    samples: ["grok-3", "grok-2-latest"],
    endpoint: "https://api.x.ai/v1",
    hint: "xAI API key; model ids like grok-3.",
  },
];

/**
 * Settings page providers (includes google/xai ids used in older configs).
 * Samples align with Home for a consistent look & feel.
 */
export const SETTINGS_PROVIDER_OPTIONS: LlmProviderOption[] = [
  {
    id: "ollama",
    label: "Local (Ollama)",
    samples: [],
    endpoint: "http://ollama:11434",
    hint: "No API key. Use host.docker.internal or localhost if Ollama runs on the host.",
  },
  {
    id: "anthropic",
    label: "Claude (Anthropic)",
    samples: ["claude-sonnet-4-20250514", "claude-3-5-haiku-latest"],
    endpoint: "",
    hint: "Uses the Anthropic SDK. Model ids like claude-sonnet-4-20250514.",
  },
  {
    id: "openai",
    label: "OpenAI / compatible",
    samples: ["gpt-4o", "gpt-4o-mini"],
    endpoint: "https://api.openai.com/v1",
    hint: "Any OpenAI-compatible /chat/completions base URL.",
  },
  {
    id: "google",
    label: "Gemini (OpenAI-compatible)",
    samples: ["gemini-2.0-flash", "gemini-1.5-pro"],
    endpoint: "https://generativelanguage.googleapis.com/v1beta/openai",
    hint: "Google AI Studio key; Gemini model ids via OpenAI-compat path.",
  },
  {
    id: "xai",
    label: "Grok (xAI)",
    samples: ["grok-3", "grok-2-latest"],
    endpoint: "https://api.x.ai/v1",
    hint: "xAI API key; model ids like grok-3.",
  },
];

export function defaultSampleFor(provider: string): string {
  const all = [...LLM_PROVIDER_OPTIONS, ...SETTINGS_PROVIDER_OPTIONS];
  const opt = all.find((p) => p.id === provider);
  return opt?.samples[0] ?? "";
}

export function samplesFor(provider: string): string[] {
  const all = [...LLM_PROVIDER_OPTIONS, ...SETTINGS_PROVIDER_OPTIONS];
  return all.find((p) => p.id === provider)?.samples ?? [];
}
