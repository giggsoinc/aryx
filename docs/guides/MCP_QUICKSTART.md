# Aryx MCP — 10-minute path (Docker → Claude)

**Goal:** From `docker compose up` to a grounded answer in **Claude Desktop** in under 10 minutes.

**In the product:** open **http://localhost:3000/mcp** (nav **MCP**) — live endpoint, same steps, full **27 tools** catalog.

---

## Timeline

| Step | Time | Action |
|------|------|--------|
| 1 | ~3 min | Start stack |
| 2 | ~1 min | `curl` MCP SSE |
| 3 | ~1 min | Issue an MCP token (required) |
| 4 | ~2 min | Claude Desktop config |
| 5 | ~2 min | First prompts |
| 6 | optional | Load sample data if graph is empty |

---

## 1. Docker

```bash
git clone https://github.com/giggsoinc/aryx.git
cd aryx
cp .env.example .env
docker compose pull
docker compose up -d
```

UI: http://localhost:3000 · API: http://localhost:8088/docs · MCP: http://localhost:8765/sse

---

## 2. Prove MCP is up

```bash
curl -m 6 -i http://localhost:8765/sse
# Expect 401 — the transport is authenticated (see step 3)
```

---

## 3. Issue an MCP token — required

> **The MCP tool surface mutates your graph.** It can ingest files, apply
> entity corrections, and persist charts. The transport is therefore
> bearer-authenticated and **fails closed**: with no token issued, every
> call is rejected.

```bash
curl -s -X POST http://localhost:8088/admin/mcp/tokens \
  -H 'Content-Type: application/json' -d '{"label":"claude-desktop"}'
# → {"token":"<plain token, shown ONCE>", ...}
```

Store it. Then confirm it works:

```bash
curl -m 6 -i http://localhost:8765/sse -H "Authorization: Bearer <token>"
# Expect Content-Type: text/event-stream
```

**Local development only** — to skip auth entirely, set `ARYX_MCP_AUTH=off`
on the `mcp` service. Never do this on a host anyone else can reach.

**Remote host:** issue a token *first*, then expose **8765**. Prefer a
private network, VPN, or an authenticating reverse proxy over opening the
port to the internet — a bearer token is the only thing between a caller
and your graph.

**Hardening the REST API too:** if you set `ARYX_API_AUTH=required` on the
`api` service, also set `ARYX_API_KEY` on the `mcp` service (any key the
API accepts). The MCP shims forward it on every call; without it they get
401 once the API is locked down.

---

## 4. Claude Desktop

Edit `~/Library/Application Support/Claude/claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "aryx": {
      "command": "npx",
      "args": [
        "-y", "mcp-remote", "http://localhost:8765/sse",
        "--header", "Authorization: Bearer <token>"
      ]
    }
  }
}
```

Quit Claude fully (⌘Q) → reopen → 🔌 tools → **aryx** (~27 tools).

---

## 5. Say in Claude

1. `List Aryx workspaces and tell me what’s in each.`  
2. `In workspace 1, which entity types do we have? Use Aryx tools.`  
3. `Ask Aryx workspace 1: summarize what you know and cite sources.`  

If empty: open UI setup → upload `examples/quickstart/` → build → retry.

---

## Tools (27) — quick index

| Group | Tools |
|-------|--------|
| Core | `list`, `ask`, `act` |
| Workspace & brief | `workspace_list`, `workspace_create`, `workspace_select`, `brief_get`, `brief_draft`, `brief_set`, `brief_save` |
| Datasource | `datasource_quiz`, `datasource_add`, `datasource_list`, `datasource_test`, `datasource_delete` |
| Ingest | `ingest_file`, `ingest_questions`, `ingest_answer`, `ingest_status`, `entities_preview` |
| Ontology | `ontology_get`, `ontology_export` |
| Dashboard | `dashboard_link` |
| Correction | `correction_propose`, `correction_apply` |
| Ask-to-visualize | `chart_draft`, `chart_confirm` |

Full parameters, JSON examples, and “say in Claude” lines: **UI → MCP → Tools** tab (`apps/web/lib/mcpTools.ts` mirrors `src/aryx/mcp/tools*.py`).

---

## Developer (programs)

- **MCP host/SDK** → `http://localhost:8765/sse`  
- **REST** → `http://localhost:8088/docs`  
- Cursor/Continue: same `mcpServers` JSON as Claude  

---

## Business (Claude / Gemini / Copilot)

- **Claude:** this MCP path.  
- **Gemini / Copilot chat:** use Aryx **Ask** in the browser, or IT bridges REST into those products.  

See [BUSINESS_GUIDE.md](BUSINESS_GUIDE.md).
