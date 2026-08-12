"use client";

import { useMemo, useState } from "react";
import {
  Check, Copy, Plug, Code2, Users, Terminal,
} from "lucide-react";
import { Header } from "@/components/brand/Header";
import { useWorkspace } from "@/lib/workspace";
import { cn } from "@/lib/cn";

/** In-app MCP hub: business (Claude etc.) + developer (programs / agents). */
export default function McpPage() {
  const { workspaceId, setWorkspaceId } = useWorkspace();
  const [tab, setTab] = useState<"business" | "developer">("business");
  const [copied, setCopied] = useState<string | null>(null);

  const endpoints = useMemo(() => {
    if (typeof window === "undefined") {
      return {
        host: "localhost",
        sse: "http://localhost:8765/sse",
        api: "http://localhost:8088",
        ui: "http://localhost:3000",
      };
    }
    const host = window.location.hostname || "localhost";
    const proto = window.location.protocol === "https:" ? "https" : "http";
    // MCP SSE is a sibling service on 8765 (compose default), not next.js port.
    const sseHost = host === "localhost" || host === "127.0.0.1"
      ? "localhost"
      : host;
    return {
      host,
      sse: `${proto === "https" ? "https" : "http"}://${sseHost}:8765/sse`,
      api: `${proto}://${sseHost}:8088`,
      ui: window.location.origin,
    };
  }, []);

  const claudeConfig = `{
  "mcpServers": {
    "aryx": {
      "command": "npx",
      "args": ["-y", "mcp-remote", "${endpoints.sse}"]
    }
  }
}`;

  const cursorConfig = claudeConfig;

  const pythonExample = `import httpx

# Prefer MCP tools from an MCP host when possible.
# Direct HTTP (OpenAPI) when embedding Aryx in your own backend:

BASE = "${endpoints.api}"
# Example: health
print(httpx.get(f"{BASE}/health", timeout=10).json())

# Ask / workspace routes: see ${endpoints.api}/docs
# MCP SSE (for hosts): ${endpoints.sse}
`;

  const curlSse = `curl -m 6 -i ${endpoints.sse}
# Expect Content-Type: text/event-stream when MCP is up`;

  const copy = async (key: string, text: string) => {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(key);
      setTimeout(() => setCopied(null), 2000);
    } catch {
      /* ignore */
    }
  };

  return (
    <div className="flex min-h-screen flex-col">
      <Header workspaceId={workspaceId} onWorkspaceChange={setWorkspaceId} />
      <main className="flex-1 bg-canvas">
        <div className="mx-auto w-full max-w-3xl px-6 pb-12 pt-6">
          <div className="mb-6 flex items-start gap-3">
            <div className="flex size-11 items-center justify-center rounded-xl bg-navy-800 text-white">
              <Plug size={22} />
            </div>
            <div>
              <h1 className="font-display text-2xl font-bold text-navy-900">
                MCP — connect agents to Aryx
              </h1>
              <p className="mt-1 text-[14px] text-subtle">
                <b>Model Context Protocol</b> lets Claude, coding tools, and your
                own programs use Aryx as tools — list workspaces, check status,
                ask grounded questions over the context graph.
              </p>
            </div>
          </div>

          {/* Endpoint strip */}
          <div className="mb-6 rounded-xl border border-navy-100 bg-white p-4 shadow-soft">
            <div className="text-[10px] font-bold uppercase tracking-[0.12em] text-navy-500">
              Your MCP endpoint (this host)
            </div>
            <div className="mt-2 flex flex-wrap items-center gap-2">
              <code className="rounded-lg bg-navy-50 px-2.5 py-1.5 font-mono text-[12px] text-navy-800">
                {endpoints.sse}
              </code>
              <CopyBtn
                ok={copied === "sse"}
                onClick={() => copy("sse", endpoints.sse)}
              />
            </div>
            <p className="mt-2 text-[11px] text-subtle">
              Compose default port <b>8765</b>. API OpenAPI:{" "}
              <a className="underline" href={`${endpoints.api}/docs`} target="_blank" rel="noreferrer">
                {endpoints.api}/docs
              </a>
              . Open firewall / security group for 8765 if connecting from another machine.
            </p>
            <pre className="mt-3 overflow-x-auto rounded-lg bg-navy-900 p-3 font-mono text-[11px] text-navy-100">
              {curlSse}
            </pre>
            <CopyBtn
              className="mt-2"
              ok={copied === "curl"}
              onClick={() => copy("curl", curlSse)}
              label="Copy curl"
            />
          </div>

          {/* Audience tabs */}
          <div className="mb-4 flex gap-2">
            <TabBtn
              active={tab === "business"}
              onClick={() => setTab("business")}
              icon={<Users size={14} />}
              label="Business · Claude & tools"
            />
            <TabBtn
              active={tab === "developer"}
              onClick={() => setTab("developer")}
              icon={<Code2 size={14} />}
              label="Developer · programs"
            />
          </div>

          {tab === "business" && (
            <div className="space-y-4">
              <section className="rounded-xl border border-navy-100 bg-white p-5 shadow-soft">
                <h2 className="font-display text-lg font-bold text-navy-900">
                  What you get
                </h2>
                <p className="mt-2 text-[13px] text-navy-800">
                  After your team loads data into Aryx and builds the context graph,
                  you can ask questions in <b>Claude Desktop</b> (or other MCP hosts)
                  and Claude will call Aryx tools instead of guessing who “Acme” is.
                </p>
                <ol className="mt-3 list-decimal space-y-1.5 pl-5 text-[13px] text-navy-800">
                  <li>IT runs Aryx (Docker). Data is loaded; smart review approved.</li>
                  <li>IT connects Claude to the MCP URL above.</li>
                  <li>You open Claude, confirm the <b>aryx</b> tools appear (plug icon).</li>
                  <li>Ask in plain English — demand sources if the answer is thin.</li>
                  <li>Wrong links? Fix once in Aryx <b>Data → Correct data</b>.</li>
                </ol>
              </section>

              <section className="rounded-xl border border-navy-100 bg-white p-5 shadow-soft">
                <h2 className="font-display text-lg font-bold text-navy-900">
                  Claude Desktop (recommended)
                </h2>
                <ol className="mt-2 list-decimal space-y-2 pl-5 text-[13px] text-navy-800">
                  <li>
                    Verify MCP is up (IT): <code className="text-[11px]">curl</code> the SSE URL.
                  </li>
                  <li>
                    Edit Claude config (macOS):{" "}
                    <code className="text-[11px]">
                      ~/Library/Application Support/Claude/claude_desktop_config.json
                    </code>
                  </li>
                  <li>Paste the JSON below (adjust URL if not localhost).</li>
                  <li>Quit Claude fully (⌘Q) and reopen → check tools under <b>aryx</b>.</li>
                </ol>
                <CodeBlock
                  title="claude_desktop_config.json"
                  code={claudeConfig}
                  copied={copied === "claude"}
                  onCopy={() => copy("claude", claudeConfig)}
                />
                <p className="mt-3 text-[12px] text-subtle">
                  <b>Cursor / Continue:</b> same <code>mcpServers</code> shape.{" "}
                  <b>claude.ai web:</b> needs HTTPS (e.g. Cloudflare tunnel) — see full guide.
                </p>
              </section>

              <section className="rounded-xl border border-navy-100 bg-white p-5 shadow-soft">
                <h2 className="font-display text-lg font-bold text-navy-900">
                  Prompts to try in Claude
                </h2>
                <ul className="mt-2 space-y-2 text-[13px] text-navy-800">
                  <li className="rounded-lg bg-navy-50 px-3 py-2">
                    “List Aryx workspaces and what’s in each.”
                  </li>
                  <li className="rounded-lg bg-navy-50 px-3 py-2">
                    “In workspace {workspaceId}, which customers have the most open tickets? Cite sources.”
                  </li>
                  <li className="rounded-lg bg-navy-50 px-3 py-2">
                    “What is the brief for the current workspace?”
                  </li>
                </ul>
                <p className="mt-3 text-[12px] text-subtle">
                  Gemini / Copilot as chat apps do not use this MCP URL automatically —
                  use <b>Ask</b> in Aryx, or ask IT for an API bridge. MCP is the native path for Claude and MCP-capable IDEs.
                </p>
              </section>
            </div>
          )}

          {tab === "developer" && (
            <div className="space-y-4">
              <section className="rounded-xl border border-navy-100 bg-white p-5 shadow-soft">
                <h2 className="font-display text-lg font-bold text-navy-900">
                  Two ways to call Aryx from a program
                </h2>
                <table className="mt-3 w-full text-left text-[13px]">
                  <thead>
                    <tr className="border-b border-navy-100 text-[10px] uppercase tracking-wide text-subtle">
                      <th className="py-2 pr-3">Path</th>
                      <th className="py-2">When to use</th>
                    </tr>
                  </thead>
                  <tbody className="text-navy-800">
                    <tr className="border-b border-navy-50">
                      <td className="py-2 pr-3 font-semibold">MCP client SDK</td>
                      <td className="py-2">
                        Agent frameworks / hosts that speak MCP (connect to{" "}
                        <code className="text-[11px]">{endpoints.sse}</code>)
                      </td>
                    </tr>
                    <tr>
                      <td className="py-2 pr-3 font-semibold">REST / OpenAPI</td>
                      <td className="py-2">
                        Your backend, LangGraph tools, Copilot Studio actions —{" "}
                        <code className="text-[11px]">{endpoints.api}/docs</code>
                      </td>
                    </tr>
                  </tbody>
                </table>
              </section>

              <section className="rounded-xl border border-navy-100 bg-white p-5 shadow-soft">
                <h2 className="font-display text-lg font-bold text-navy-900">
                  MCP tool surface (summary)
                </h2>
                <p className="mt-2 text-[13px] text-navy-800">
                  Aryx exposes onboard, ask/act, datasource, ingest HITL, and ontology
                  tools over MCP (on the order of ~20 tools). Typical agent flow:
                </p>
                <pre className="mt-3 overflow-x-auto rounded-lg bg-navy-900 p-3 font-mono text-[11px] leading-relaxed text-navy-100">
{`list / workspace tools  → pick workspace_id
brief / ontology tools   → understand model
ask                      → grounded question + citations
ingest HITL tools        → answer pending questions if pipeline paused`}
                </pre>
                <p className="mt-2 text-[12px] text-subtle">
                  Full narrative walkthrough in the repo:{" "}
                  <code className="text-[11px]">docs/mcp-guide.html</code>
                  {" "}(open from the git checkout or GitHub).
                </p>
              </section>

              <section className="rounded-xl border border-navy-100 bg-white p-5 shadow-soft">
                <h2 className="font-display text-lg font-bold text-navy-900 flex items-center gap-2">
                  <Terminal size={18} /> Cursor / IDE config
                </h2>
                <CodeBlock
                  title="mcpServers (same shape as Claude)"
                  code={cursorConfig}
                  copied={copied === "cursor"}
                  onCopy={() => copy("cursor", cursorConfig)}
                />
              </section>

              <section className="rounded-xl border border-navy-100 bg-white p-5 shadow-soft">
                <h2 className="font-display text-lg font-bold text-navy-900">
                  HTTP from Python (backend embed)
                </h2>
                <CodeBlock
                  title="example.py"
                  code={pythonExample}
                  copied={copied === "py"}
                  onCopy={() => copy("py", pythonExample)}
                />
              </section>

              <section className="rounded-xl border border-dashed border-steel-400/40 bg-white/80 p-4 text-[13px] text-navy-800">
                <b>Compose services</b>
                <ul className="mt-2 list-disc space-y-1 pl-5 text-[12px] text-subtle">
                  <li>Web UI — :3000 (this page)</li>
                  <li>API — :8088</li>
                  <li>MCP SSE — :8765/sse</li>
                </ul>
                <p className="mt-2 text-[12px] text-subtle">
                  Production: terminate TLS, restrict 8765, and use network policies.
                  MCP tokens (if enabled in your deploy) live under admin security docs.
                </p>
              </section>
            </div>
          )}

          <p className="mt-8 text-center text-[12px] text-subtle">
            Product path: load data in setup → build context → connect MCP → ask via Claude or your agent.{" "}
            <a href="/ask" className="font-semibold text-steel-600 underline">Open Ask</a>
            {" · "}
            <a href="/settings" className="font-semibold text-steel-600 underline">Settings (LLM)</a>
          </p>
        </div>
      </main>
    </div>
  );
}

function TabBtn({
  active, onClick, icon, label,
}: {
  active: boolean; onClick: () => void; icon: React.ReactNode; label: string;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        "focus-ring inline-flex items-center gap-1.5 rounded-xl px-3.5 py-2 text-[12px] font-semibold",
        active
          ? "bg-navy-800 text-white"
          : "border border-navy-100 bg-white text-navy-700 hover:bg-navy-50",
      )}
    >
      {icon}
      {label}
    </button>
  );
}

function CopyBtn({
  ok, onClick, label = "Copy", className,
}: {
  ok: boolean; onClick: () => void; label?: string; className?: string;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        "focus-ring inline-flex items-center gap-1 rounded-lg border border-navy-100 bg-white px-2.5 py-1 text-[11px] font-medium text-navy-700 hover:bg-navy-50",
        className,
      )}
    >
      {ok ? <Check size={12} className="text-emerald-600" /> : <Copy size={12} />}
      {ok ? "Copied" : label}
    </button>
  );
}

function CodeBlock({
  title, code, copied, onCopy,
}: {
  title: string; code: string; copied: boolean; onCopy: () => void;
}) {
  return (
    <div className="mt-3">
      <div className="mb-1 flex items-center justify-between">
        <span className="text-[10px] font-bold uppercase tracking-wide text-navy-500">
          {title}
        </span>
        <CopyBtn ok={copied} onClick={onCopy} />
      </div>
      <pre className="overflow-x-auto rounded-lg bg-navy-900 p-3 font-mono text-[11px] leading-relaxed text-navy-100 whitespace-pre-wrap">
        {code}
      </pre>
    </div>
  );
}
