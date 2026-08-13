/** Catalog of Aryx MCP tools for the in-app /mcp hub (keep in sync with src/aryx/mcp/tools*.py). */

export type McpToolDoc = {
  name: string;
  group: string;
  summary: string;
  params: string;
  example: string;
  sayInClaude: string;
};

export const MCP_TOOL_COUNT = 21;

export const MCP_TOOL_GROUPS = [
  "Core",
  "Workspace & brief",
  "Datasource",
  "Ingest HITL",
  "Ontology",
] as const;

export const MCP_TOOLS: McpToolDoc[] = [
  {
    name: "list",
    group: "Core",
    summary: "List every workspace with counts and types. Call first.",
    params: "(none)",
    example: `{}`,
    sayInClaude: "List Aryx workspaces and what’s in each.",
  },
  {
    name: "ask",
    group: "Core",
    summary: "Natural-language question over a workspace graph; grounded answer + entity ids.",
    params: "question (required), workspace_id (optional)",
    example: `{"question": "Which customers have the most open tickets?", "workspace_id": 1}`,
    sayInClaude: "In workspace 1, which customers have the most open tickets? Cite sources.",
  },
  {
    name: "act",
    group: "Core",
    summary: "Request an action on an entity (always pending human approval).",
    params: "action, entity_id, params?",
    example: `{"action": "retype", "entity_id": 42, "params": {"type": "Customer"}}`,
    sayInClaude: "Request a retype of entity 42 to Customer (needs approval).",
  },
  {
    name: "workspace_list",
    group: "Workspace & brief",
    summary: "List workspaces (id, name, brief, timestamps).",
    params: "(none)",
    example: `{}`,
    sayInClaude: "Show all Aryx workspaces.",
  },
  {
    name: "workspace_create",
    group: "Workspace & brief",
    summary: "Create an isolated workspace (own graph partition).",
    params: "name (required), description?, context?",
    example: `{"name": "Support pilot", "description": "Tickets + customers"}`,
    sayInClaude: "Create a workspace called Support pilot.",
  },
  {
    name: "workspace_select",
    group: "Workspace & brief",
    summary: "Confirm a workspace exists; use before brief/ingest.",
    params: "workspace_id (required)",
    example: `{"workspace_id": 1}`,
    sayInClaude: "Select workspace 1 and confirm it exists.",
  },
  {
    name: "brief_get",
    group: "Workspace & brief",
    summary: "Current brief + depth + next_question to ask the user.",
    params: "workspace_id (required)",
    example: `{"workspace_id": 1}`,
    sayInClaude: "What’s the brief for workspace 1, and what should I ask next?",
  },
  {
    name: "brief_draft",
    group: "Workspace & brief",
    summary: "AI-draft the brief from a seed sentence and/or doc text.",
    params: "workspace_id (required), seed?, doc_text?",
    example: `{"workspace_id": 1, "seed": "Support tickets linked to customers"}`,
    sayInClaude: "Draft a brief for workspace 1: support tickets linked to customers.",
  },
  {
    name: "brief_set",
    group: "Workspace & brief",
    summary: "Patch one brief field (domain, aim, objectives, scope, roles).",
    params: "workspace_id, field, value",
    example: `{"workspace_id": 1, "field": "domain", "value": "Customer support"}`,
    sayInClaude: "Set the domain of workspace 1 to Customer support.",
  },
  {
    name: "brief_save",
    group: "Workspace & brief",
    summary: "Persist the brief (optional whole-object override).",
    params: "workspace_id (required), brief?",
    example: `{"workspace_id": 1}`,
    sayInClaude: "Save the brief for workspace 1.",
  },
  {
    name: "datasource_quiz",
    group: "Datasource",
    summary: "Field pack for a source kind (or list kinds if kind omitted).",
    params: "kind? (postgresql|mysql|oracle|docs|rest)",
    example: `{"kind": "postgresql"}`,
    sayInClaude: "What fields do I need to connect Postgres to Aryx?",
  },
  {
    name: "datasource_add",
    group: "Datasource",
    summary: "Register a datasource; secret is encrypted, never returned plain.",
    params: "workspace_id, name, kind, config?, secret?",
    example: `{"workspace_id": 1, "name": "prod-pg", "kind": "postgresql", "config": {"host": "db", "database": "app"}, "secret": "…"}`,
    sayInClaude: "Help me add a Postgres datasource to workspace 1 (ask me for fields).",
  },
  {
    name: "datasource_list",
    group: "Datasource",
    summary: "List datasources in a workspace (masked secrets only).",
    params: "workspace_id",
    example: `{"workspace_id": 1}`,
    sayInClaude: "List datasources in workspace 1.",
  },
  {
    name: "datasource_test",
    group: "Datasource",
    summary: "Probe credentials (SQL SELECT 1 + tables, etc.).",
    params: "datasource_id",
    example: `{"datasource_id": 3}`,
    sayInClaude: "Test datasource 3.",
  },
  {
    name: "datasource_delete",
    group: "Datasource",
    summary: "Hard-delete a datasource (no undo).",
    params: "datasource_id",
    example: `{"datasource_id": 3}`,
    sayInClaude: "Delete datasource 3.",
  },
  {
    name: "ingest_questions",
    group: "Ingest HITL",
    summary: "List pipeline clarifying questions (default: pending).",
    params: "workspace_id, status?, limit?",
    example: `{"workspace_id": 1, "status": "pending"}`,
    sayInClaude: "Any pending ingest questions in workspace 1?",
  },
  {
    name: "ingest_answer",
    group: "Ingest HITL",
    summary: "Answer a pending question to unblock the pipeline.",
    params: "question_id, answer, answered_by?",
    example: `{"question_id": 12, "answer": "Same", "answered_by": "you"}`,
    sayInClaude: "Answer ingest question 12 with: Same.",
  },
  {
    name: "ingest_status",
    group: "Ingest HITL",
    summary: "Question counts + optional job stage/progress.",
    params: "workspace_id, job_id?",
    example: `{"workspace_id": 1}`,
    sayInClaude: "What’s the ingest status for workspace 1?",
  },
  {
    name: "entities_preview",
    group: "Ingest HITL",
    summary: "Sample entities and edges from the live graph.",
    params: "workspace_id, limit?",
    example: `{"workspace_id": 1, "limit": 20}`,
    sayInClaude: "Preview what Aryx knows in workspace 1.",
  },
  {
    name: "ontology_get",
    group: "Ontology",
    summary: "Approved types (attrs + counts) and relationships.",
    params: "workspace_id",
    example: `{"workspace_id": 1}`,
    sayInClaude: "Show the ontology for workspace 1.",
  },
  {
    name: "ontology_export",
    group: "Ontology",
    summary: "Export ontology (postgres/mysql/snowflake/neo4j/turtle/json-ld…).",
    params: "workspace_id, target",
    example: `{"workspace_id": 1, "target": "turtle"}`,
    sayInClaude: "Export workspace 1 ontology as Turtle.",
  },
];
