# Aryx MCP Server Configuration for Claude

## Server Status
- **Service:** aryx-mcp-1
- **Port:** 8765
- **Status:** ✅ Running
- **Address:** `http://ec2-3-91-73-197.compute-1.amazonaws.com:8765`
- **Protocol:** SSE (Server-Sent Events) + MCP

---

## Setup for Claude Code

### **Option 1: Direct Connection (Claude.ai)**

1. Go to **claude.ai/code**
2. Click **Settings** (⚙️)
3. Go to **MCP Servers**
4. Click **+ Add Server**
5. Select **Custom Server** 
6. Configure:
   ```
   Name:        Aryx Demo Support
   URL:         http://ec2-3-91-73-197.compute-1.amazonaws.com:8765
   Type:        SSE over HTTP
   Auth Token:  (optional — see below)
   ```
7. Click **Connect**

---

### **Option 2: Local SSH Tunnel (Secure)**

If accessing from your machine:

```bash
# Create tunnel to EC2
ssh -i ~/.ssh/rvdts-oracle-key.pem \
  -L 8765:localhost:8765 \
  ec2-user@ec2-3-91-73-197.compute-1.amazonaws.com

# Then in Claude settings, use: http://localhost:8765
```

---

## Available MCP Tools

Once connected, Claude can:

### **Query the Knowledge Graph**
```
Get entities by type
Search entities by property
Find relationships between entities
Get entity details with full context
```

### **Ask Questions**
```
Run pre-canned queries
Execute natural language questions against the graph
Get reasoning + evidence
```

### **Manage Workspace**
```
List workspaces
Get workspace brief
View ingestion status
Check ontology exports
```

### **Analyze Support Tickets**
```
Find tickets by status/priority
Get agent workload
Find device failure patterns
Recommend escalations
```

---

## Example Queries You Can Ask Claude

Once MCP is connected:

```
"What are the most common failure patterns in RadioX-6000?"
"Which agents have the highest resolution rate?"
"Show me escalated tickets that are still open"
"Find devices with RMA-eligible status"
"What's the MTTR for critical priority tickets?"
"List all tickets assigned to Sam Patel"
```

---

## Authentication

### Generate MCP Token

If you need bearer token auth:

```bash
ssh -i ~/.ssh/rvdts-oracle-key.pem ec2-user@ec2-3-91-73-197.compute-1.amazonaws.com
cd /home/ec2-user/aryx

# Create token
curl -s -X POST http://localhost:8088/admin/mcp/tokens \
  -H 'Content-Type: application/json' \
  -d '{"name": "claude-integration", "expires_in": 2592000}' | jq .token
```

Then use that token as Bearer auth in Claude settings:
```
Authorization: Bearer <token>
```

---

## Troubleshooting

### "Connection Refused"
- Check EC2 security group allows port 8765
- Verify container is running: `docker ps | grep mcp`
- Try: `curl http://localhost:8765 -v`

### "No Entities Found"
- MCP is connected, but the workspace hasn't ingested data yet
- Complete the **File Ingest** step first (upload tickets.csv)
- Then refresh Claude MCP connection

### "Timeout"
- EC2 instance may have paused
- Restart: `docker-compose up -d mcp`
- Or: `docker restart aryx-mcp-1`

---

## What You Can Do in Claude with Aryx

Once MCP is live:

```
Claude: "Based on the support graph, which agent should handle 
this new ticket about RadioX-6000 firmware 6.2.1 crash?"

Aryx MCP: 
  Entity: Ticket-123
  Symptom: Firmware crashes on boot
  Matching agents: [Sam Patel (L2, Firmware, has Firmware-6.2 tag)]
  Similar tickets resolved: 8 (87% success rate)
  Recommendation: Assign to Sam Patel
```

---

## Development

### MCP Server Code
- **Location:** `src/aryx/mcp/server.py`
- **Routes:** `/mcp` (SSE endpoint)
- **Protocol:** MCP 1.0 (Model Context Protocol)

### Available Resources
- `aryx://entities` — All graph entities
- `aryx://relationships` — All relationships
- `aryx://queries` — Pre-canned queries
- `aryx://workspace/{id}` — Workspace-specific data

### Tools Exposed
- `entity_search` — Query entities
- `relationship_get` — Get specific relationships
- `query_execute` — Run stored queries
- `workspace_info` — Get workspace metadata

---

## Next Steps

1. ✅ **MCP Server Running:** aryx-mcp-1 (port 8765)
2. 📋 **Ingest Data Tomorrow:** Upload tickets.csv via Brief → Ingest
3. 🔗 **Connect to Claude:** Use config above
4. 💬 **Ask Claude Questions:** About tickets, agents, patterns

**MCP is ready. Just ingest the data first, then connect from Claude.** 🚀
