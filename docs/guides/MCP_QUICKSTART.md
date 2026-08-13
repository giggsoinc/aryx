# Aryx MCP — 10-minute path (Docker → Claude)

**Goal:** From `docker compose up` to a grounded answer in **Claude Desktop** in under 10 minutes.

**In the product:** open **http://localhost:3000/mcp** (nav **MCP**) — live endpoint, same steps, full **21 tools** catalog.

---

## Timeline

| Step | Time | Action |
|------|------|--------|
| 1 | ~3 min | Start stack |
| 2 | ~1 min | `curl` MCP SSE |
| 3 | ~2 min | Claude Desktop config |
| 4 | ~2 min | First prompts |
| 5 | optional | Load sample data if graph is empty |

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
# Expect Content-Type: text/event-stream
```

Remote host: use `http://<server>:8765/sse` and open **8765** in the security group.

---

## 3. Claude Desktop

Edit `~/Library/Application Support/Claude/claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "aryx": {
      "command": "npx",
      "args": ["-y", "mcp-remote", "http://localhost:8765/sse"]
    }
  }
}
```

Quit Claude fully (⌘Q) → reopen → 🔌 tools → **aryx** (~21 tools).

---

## 4. Say in Claude

1. `List Aryx workspaces and tell me what’s in each.`  
2. `In workspace 1, which entity types do we have? Use Aryx tools.`  
3. `Ask Aryx workspace 1: summarize what you know and cite sources.`  

If empty: open UI setup → upload `examples/quickstart/` → build → retry.

---

## Tools (21) — quick index

| Group | Tools |
|-------|--------|
| Core | `list`, `ask`, `act` |
| Workspace & brief | `workspace_list`, `workspace_create`, `workspace_select`, `brief_get`, `brief_draft`, `brief_set`, `brief_save` |
| Datasource | `datasource_quiz`, `datasource_add`, `datasource_list`, `datasource_test`, `datasource_delete` |
| Ingest HITL | `ingest_questions`, `ingest_answer`, `ingest_status`, `entities_preview` |
| Ontology | `ontology_get`, `ontology_export` |

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
