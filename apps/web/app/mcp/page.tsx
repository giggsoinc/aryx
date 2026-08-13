"use client";

import { useMemo, useState } from "react";
import {
  Check, Copy, Plug, Code2, Users, Terminal, ListOrdered, Clock,
} from "lucide-react";
import { Header } from "@/components/brand/Header";
import { useWorkspace } from "@/lib/workspace";
import { cn } from "@/lib/cn";
import {
  MCP_TOOLS, MCP_TOOL_COUNT, MCP_TOOL_GROUPS, type McpToolDoc,
} from "@/lib/mcpTools";

type Tab = "start" | "tools" | "business" | "developer";

/** In-app MCP hub: 10-min Docker→Claude path, full tool catalog, dev notes. */
export default function McpPage() {
  const { workspaceId, setWorkspaceId } = useWorkspace();
  const [tab, setTab] = useState<Tab>("start");
  const [copied, setCopied] = useState<string | null>(null);
  const [toolFilter, setToolFilter] = useState<string>("All");
  const [openTool, setOpenTool] = useState<string | null>("list");

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
    // MCP SSE is compose service on 8765 (not the Next.js port).
    const sseHost =
      host === "localhost" || host === "127.0.0.1" ? "localhost" : host;
    return {
      host,
      sse: `http://${sseHost}:8765/sse`,
      api: `http://${sseHost}:8088`,
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

  const curlSse = `curl -m 6 -i ${endpoints.sse}
# Expect: HTTP/1.x 200  and  Content-Type: text/event-stream`;

  const pythonExample = `import httpx
BASE = "${endpoints.api}"
print(httpx.get(f"{BASE}/health", timeout=10).json())
# Full REST: ${endpoints.api}/docs
# MCP for hosts: ${endpoints.sse}
`;

  const copy = async (key: string, text: string) => {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(key);
      setTimeout(() => setCopied(null), 2000);
    } catch { /* ignore */ }
  };

  const filtered =
    toolFilter === "All"
      ? MCP_TOOLS
      : MCP_TOOLS.filter((t) => t.group === toolFilter);

  return (
    <div className="flex min-h-screen flex-col">
      <Header workspaceId={workspaceId} onWorkspaceChange={setWorkspaceId} />
      <main className="flex-1 bg-canvas">
        <div className="mx-auto w-full max-w-3xl px-6 pb-12 pt-6">
          <div className="mb-5 flex items-start gap-3">
            <div className="flex size-11 shrink-0 items-center justify-center rounded-xl bg-navy-800 text-white">
              <Plug size={22} />
            </div>
            <div>
              <h1 className="font-display text-2xl font-bold text-navy-900">
                MCP — Aryx for Claude &amp; agents
              </h1>
              <p className="mt-1 text-[14px] text-subtle">
                Docker → Claude in under <b>10 minutes</b>.{" "}
                {MCP_TOOL_COUNT} tools: list workspaces, ask grounded questions,
                brief, datasources, ingest HITL, ontology.
              </p>
            </div>
          </div>

          {/* Endpoint always visible */}
          <div className="mb-5 rounded-xl border border-navy-100 bg-white p-4 shadow-soft">
            <div className="text-[10px] font-bold uppercase tracking-[0.12em] text-navy-500">
              Your MCP endpoint
            </div>
            <div className="mt-2 flex flex-wrap items-center gap-2">
              <code className="rounded-lg bg-navy-50 px-2.5 py-1.5 font-mono text-[12px] text-navy-800">
                {endpoints.sse}
              </code>
              <CopyBtn ok={copied === "sse"} onClick={() => copy("sse", endpoints.sse)} />
            </div>
            <p className="mt-2 text-[11px] text-subtle">
              Port <b>8765</b> · Open firewall if Claude is on another machine ·
              API docs:{" "}
              <a className="underline" href={`${endpoints.api}/docs`} target="_blank" rel="noreferrer">
                {endpoints.api}/docs
              </a>
            </p>
          </div>

          <div className="mb-4 flex flex-wrap gap-2">
            <TabBtn active={tab === "start"} onClick={() => setTab("start")}
              icon={<Clock size={14} />} label="10-min setup" />
            <TabBtn active={tab === "tools"} onClick={() => setTab("tools")}
              icon={<ListOrdered size={14} />} label={`Tools (${MCP_TOOL_COUNT})`} />
            <TabBtn active={tab === "business"} onClick={() => setTab("business")}
              icon={<Users size={14} />} label="Claude / business" />
            <TabBtn active={tab === "developer"} onClick={() => setTab("developer")}
              icon={<Code2 size={14} />} label="Developer" />
          </div>

          {tab === "start" && (
            <StartTab
              endpoints={endpoints}
              claudeConfig={claudeConfig}
              curlSse={curlSse}
              workspaceId={workspaceId}
              copied={copied}
              copy={copy}
              onGoTools={() => setTab("tools")}
            />
          )}

          {tab === "tools" && (
            <ToolsTab
              filtered={filtered}
              toolFilter={toolFilter}
              setToolFilter={setToolFilter}
              openTool={openTool}
              setOpenTool={setOpenTool}
              copied={copied}
              copy={copy}
              workspaceId={workspaceId}
            />
          )}

          {tab === "business" && (
            <BusinessTab
              claudeConfig={claudeConfig}
              copied={copied}
              copy={copy}
              workspaceId={workspaceId}
            />
          )}

          {tab === "developer" && (
            <DeveloperTab
              endpoints={endpoints}
              claudeConfig={claudeConfig}
              pythonExample={pythonExample}
              curlSse={curlSse}
              copied={copied}
              copy={copy}
            />
          )}
        </div>
      </main>
    </div>
  );
}

function StartTab({
  endpoints, claudeConfig, curlSse, workspaceId, copied, copy, onGoTools,
}: {
  endpoints: { sse: string; api: string; ui: string };
  claudeConfig: string;
  curlSse: string;
  workspaceId: number;
  copied: string | null;
  copy: (k: string, t: string) => void;
  onGoTools: () => void;
}) {
  return (
    <div className="space-y-4">
      <section className="rounded-xl border border-emerald-200 bg-emerald-50/40 p-5 shadow-soft">
        <h2 className="font-display text-lg font-bold text-navy-900">
          Goal: first Claude answer from Aryx in ≤10 minutes
        </h2>
        <p className="mt-1 text-[13px] text-navy-800">
          Assumes Docker Desktop (or Linux Docker) and Claude Desktop on the same Mac,
          or Claude can reach this host’s port 8765.
        </p>
      </section>

      <Step n={1} mins="~3 min" title="Start Aryx with Docker">
        <pre className="overflow-x-auto rounded-lg bg-navy-900 p-3 font-mono text-[11px] text-navy-100">{`git clone https://github.com/giggsoinc/aryx.git
cd aryx
cp .env.example .env
docker compose pull
docker compose up -d`}</pre>
        <p className="mt-2 text-[12px] text-subtle">
          Wait until UI opens:{" "}
          <a className="underline" href={endpoints.ui}>{endpoints.ui}</a>
          {" "}· Optional: load sample CSVs via setup (or Ask after any workspace has data).
        </p>
      </Step>

      <Step n={2} mins="~1 min" title="Prove MCP is alive">
        <pre className="overflow-x-auto rounded-lg bg-navy-900 p-3 font-mono text-[11px] text-navy-100">{curlSse}</pre>
        <CopyBtn className="mt-2" ok={copied === "curl"} onClick={() => copy("curl", curlSse)} label="Copy curl" />
        <p className="mt-2 text-[12px] text-subtle">
          If this fails: check <code>docker compose ps</code> for the MCP service and
          open port <b>8765</b> (local or security group).
        </p>
      </Step>

      <Step n={3} mins="~2 min" title="Point Claude Desktop at Aryx">
        <p className="text-[13px] text-navy-800">
          Edit{" "}
          <code className="text-[11px]">
            ~/Library/Application Support/Claude/claude_desktop_config.json
          </code>
          {" "}(create the file if missing). Paste:
        </p>
        <CodeBlock
          title="claude_desktop_config.json"
          code={claudeConfig}
          copied={copied === "claude"}
          onCopy={() => copy("claude", claudeConfig)}
        />
        <p className="mt-2 text-[12px] text-subtle">
          Fully quit Claude (⌘Q) → reopen → open the <b>🔌</b> / tools panel → look for{" "}
          <b>aryx</b> with {MCP_TOOL_COUNT} tools.
        </p>
      </Step>

      <Step n={4} mins="~2 min" title="Say this in Claude (copy-paste)">
        <ul className="space-y-2 text-[13px] text-navy-800">
          {[
            "List Aryx workspaces and tell me what’s in each.",
            `Using Aryx, ask workspace ${workspaceId}: what entity types do we have? Cite sources if possible.`,
            "Show the ontology for workspace 1 using Aryx tools.",
          ].map((p) => (
            <li key={p} className="flex items-start justify-between gap-2 rounded-lg bg-navy-50 px-3 py-2">
              <span>“{p}”</span>
              <CopyBtn ok={copied === p} onClick={() => copy(p, p)} label="Copy" />
            </li>
          ))}
        </ul>
        <p className="mt-3 text-[12px] text-subtle">
          No data yet? In the browser open setup, upload{" "}
          <code className="text-[11px]">examples/quickstart/</code> CSVs, build the graph,
          then re-run the asks (~extra few minutes for first ingest).
        </p>
      </Step>

      <Step n={5} mins="optional" title="Browse every tool">
        <button
          type="button"
          onClick={onGoTools}
          className="focus-ring rounded-lg bg-navy-800 px-3.5 py-2 text-[12px] font-semibold text-white hover:bg-navy-700"
        >
          Open full tools catalog →
        </button>
      </Step>
    </div>
  );
}

function ToolsTab({
  filtered, toolFilter, setToolFilter, openTool, setOpenTool, copied, copy, workspaceId,
}: {
  filtered: McpToolDoc[];
  toolFilter: string;
  setToolFilter: (g: string) => void;
  openTool: string | null;
  setOpenTool: (n: string | null) => void;
  copied: string | null;
  copy: (k: string, t: string) => void;
  workspaceId: number;
}) {
  return (
    <div className="space-y-3">
      <p className="text-[13px] text-navy-800">
        All <b>{MCP_TOOL_COUNT}</b> tools Claude can call. Expand a row for parameters,
        JSON example, and a plain-English line to say in chat.
      </p>
      <div className="flex flex-wrap gap-1.5">
        {["All", ...MCP_TOOL_GROUPS].map((g) => (
          <button
            key={g}
            type="button"
            onClick={() => setToolFilter(g)}
            className={cn(
              "focus-ring rounded-full px-2.5 py-1 text-[11px] font-semibold",
              toolFilter === g
                ? "bg-navy-800 text-white"
                : "bg-white text-navy-700 border border-navy-100 hover:bg-navy-50",
            )}
          >
            {g}
          </button>
        ))}
      </div>
      <ul className="space-y-2">
        {filtered.map((t) => {
          const open = openTool === t.name;
          const ex = t.example.replace(/"workspace_id": 1/g, `"workspace_id": ${workspaceId}`);
          return (
            <li
              key={t.name}
              className="rounded-xl border border-navy-100 bg-white shadow-soft overflow-hidden"
            >
              <button
                type="button"
                onClick={() => setOpenTool(open ? null : t.name)}
                className="flex w-full items-center justify-between gap-2 px-4 py-3 text-left hover:bg-navy-50/50"
              >
                <div className="min-w-0">
                  <div className="flex flex-wrap items-center gap-2">
                    <code className="font-mono text-[13px] font-bold text-navy-900">
                      {t.name}
                    </code>
                    <span className="rounded-full bg-navy-50 px-2 py-0.5 text-[10px] font-semibold text-navy-600">
                      {t.group}
                    </span>
                  </div>
                  <p className="mt-0.5 text-[12px] text-subtle">{t.summary}</p>
                </div>
                <span className="shrink-0 text-[11px] text-steel-600">
                  {open ? "Hide" : "Details"}
                </span>
              </button>
              {open && (
                <div className="border-t border-navy-50 px-4 py-3 text-[12px] text-navy-800 space-y-2">
                  <div>
                    <span className="text-[10px] font-bold uppercase text-navy-500">
                      Parameters
                    </span>
                    <p className="mt-0.5 font-mono text-[11px]">{t.params}</p>
                  </div>
                  <div>
                    <div className="mb-1 flex items-center justify-between">
                      <span className="text-[10px] font-bold uppercase text-navy-500">
                        Example call (JSON args)
                      </span>
                      <CopyBtn
                        ok={copied === `ex-${t.name}`}
                        onClick={() => copy(`ex-${t.name}`, ex)}
                      />
                    </div>
                    <pre className="overflow-x-auto rounded-lg bg-navy-900 p-2.5 font-mono text-[11px] text-navy-100">
                      {ex}
                    </pre>
                  </div>
                  <div>
                    <div className="mb-1 flex items-center justify-between">
                      <span className="text-[10px] font-bold uppercase text-navy-500">
                        Say in Claude
                      </span>
                      <CopyBtn
                        ok={copied === `say-${t.name}`}
                        onClick={() => copy(`say-${t.name}`, t.sayInClaude)}
                      />
                    </div>
                    <p className="rounded-lg bg-navy-50 px-3 py-2 text-[13px]">
                      “{t.sayInClaude}”
                    </p>
                  </div>
                </div>
              )}
            </li>
          );
        })}
      </ul>
    </div>
  );
}

function BusinessTab({
  claudeConfig, copied, copy, workspaceId,
}: {
  claudeConfig: string;
  copied: string | null;
  copy: (k: string, t: string) => void;
  workspaceId: number;
}) {
  return (
    <div className="space-y-4">
      <section className="rounded-xl border border-navy-100 bg-white p-5 shadow-soft">
        <h2 className="font-display text-lg font-bold text-navy-900">
          What you get
        </h2>
        <p className="mt-2 text-[13px] text-navy-800">
          Claude becomes the chat UI. Aryx becomes the <b>context tools</b>
          (identity, graph, provenance). You type normal questions; Claude calls{" "}
          <code className="text-[11px]">list</code>, <code className="text-[11px]">ask</code>, etc.
        </p>
        <ol className="mt-3 list-decimal space-y-1 pl-5 text-[13px] text-navy-800">
          <li>IT finishes <b>10-min setup</b> (Docker + Claude config).</li>
          <li>Team loads data in the web UI (data first → build).</li>
          <li>You ask Claude; check the 🔌 tools list includes <b>aryx</b>.</li>
          <li>Fix bad links once in Aryx <b>Data → Correct data</b>.</li>
        </ol>
      </section>
      <section className="rounded-xl border border-navy-100 bg-white p-5 shadow-soft">
        <h2 className="font-display text-lg font-bold text-navy-900">
          Claude config (paste)
        </h2>
        <CodeBlock
          title="claude_desktop_config.json"
          code={claudeConfig}
          copied={copied === "claude2"}
          onCopy={() => copy("claude2", claudeConfig)}
        />
      </section>
      <section className="rounded-xl border border-navy-100 bg-white p-5 shadow-soft">
        <h2 className="font-display text-lg font-bold text-navy-900">
          Prompts that work well
        </h2>
        <ul className="mt-2 space-y-2 text-[13px]">
          {[
            "List Aryx workspaces and what’s in each.",
            `In workspace ${workspaceId}, which entity types exist? Use Aryx tools.`,
            `Ask Aryx workspace ${workspaceId}: summarize top entities and cite sources.`,
            "Are there any pending ingest questions I should answer?",
            "Show the ontology for workspace 1.",
          ].map((p) => (
            <li key={p} className="flex justify-between gap-2 rounded-lg bg-navy-50 px-3 py-2 text-navy-800">
              <span>“{p}”</span>
              <CopyBtn ok={copied === p} onClick={() => copy(p, p)} />
            </li>
          ))}
        </ul>
        <p className="mt-3 text-[12px] text-subtle">
          Gemini / Copilot: use Aryx <b>Ask</b> in the browser, or an IT-built API bridge.
          MCP is the fast path for Claude and MCP-capable IDEs.
        </p>
      </section>
    </div>
  );
}

function DeveloperTab({
  endpoints, claudeConfig, pythonExample, curlSse, copied, copy,
}: {
  endpoints: { sse: string; api: string };
  claudeConfig: string;
  pythonExample: string;
  curlSse: string;
  copied: string | null;
  copy: (k: string, t: string) => void;
}) {
  return (
    <div className="space-y-4">
      <section className="rounded-xl border border-navy-100 bg-white p-5 shadow-soft">
        <h2 className="font-display text-lg font-bold text-navy-900">
          Call paths
        </h2>
        <table className="mt-3 w-full text-left text-[13px]">
          <thead>
            <tr className="border-b border-navy-100 text-[10px] uppercase text-subtle">
              <th className="py-2">Path</th>
              <th className="py-2">Use when</th>
            </tr>
          </thead>
          <tbody className="text-navy-800">
            <tr className="border-b border-navy-50">
              <td className="py-2 font-semibold pr-3">MCP host / SDK</td>
              <td className="py-2">Claude, Cursor, agent frameworks → {endpoints.sse}</td>
            </tr>
            <tr>
              <td className="py-2 font-semibold pr-3">REST OpenAPI</td>
              <td className="py-2">Your backend / Copilot Studio → {endpoints.api}/docs</td>
            </tr>
          </tbody>
        </table>
      </section>
      <section className="rounded-xl border border-navy-100 bg-white p-5 shadow-soft">
        <h2 className="font-display text-lg font-bold text-navy-900 flex items-center gap-2">
          <Terminal size={18} /> IDE / Claude MCP JSON
        </h2>
        <CodeBlock
          title="mcpServers"
          code={claudeConfig}
          copied={copied === "devclaude"}
          onCopy={() => copy("devclaude", claudeConfig)}
        />
      </section>
      <section className="rounded-xl border border-navy-100 bg-white p-5 shadow-soft">
        <h2 className="font-display text-lg font-bold text-navy-900">HTTP smoke</h2>
        <CodeBlock
          title="curl SSE"
          code={curlSse}
          copied={copied === "curl2"}
          onCopy={() => copy("curl2", curlSse)}
        />
        <CodeBlock
          title="python health"
          code={pythonExample}
          copied={copied === "py"}
          onCopy={() => copy("py", pythonExample)}
        />
      </section>
      <p className="text-[12px] text-subtle">
        Tool definitions live in <code className="text-[11px]">src/aryx/mcp/tools*.py</code>.
        Catalog on this page is kept in <code className="text-[11px]">apps/web/lib/mcpTools.ts</code>.
      </p>
    </div>
  );
}

function Step({
  n, mins, title, children,
}: {
  n: number; mins: string; title: string; children: React.ReactNode;
}) {
  return (
    <section className="rounded-xl border border-navy-100 bg-white p-5 shadow-soft">
      <div className="mb-2 flex items-center gap-2">
        <span className="flex size-7 items-center justify-center rounded-full bg-navy-800 text-[12px] font-bold text-white">
          {n}
        </span>
        <h2 className="font-display text-[1.05rem] font-bold text-navy-900">{title}</h2>
        <span className="ml-auto text-[10px] font-bold uppercase tracking-wide text-steel-600">
          {mins}
        </span>
      </div>
      {children}
    </section>
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
        "focus-ring inline-flex items-center gap-1.5 rounded-xl px-3 py-2 text-[12px] font-semibold",
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
        "focus-ring inline-flex shrink-0 items-center gap-1 rounded-lg border border-navy-100 bg-white px-2 py-1 text-[11px] font-medium text-navy-700 hover:bg-navy-50",
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
      <pre className="overflow-x-auto whitespace-pre-wrap rounded-lg bg-navy-900 p-3 font-mono text-[11px] leading-relaxed text-navy-100">
        {code}
      </pre>
    </div>
  );
}
