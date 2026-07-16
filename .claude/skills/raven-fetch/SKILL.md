---
name: raven-fetch
description: >
  Use this skill whenever the user wants to fetch, list, view, browse, or look up tasks,
  projects, or work items from Odoo using the Go DO MCP connector. Trigger on phrases like:
  "raven fetch", "list my tasks", "show projects in Odoo", "what tasks are assigned to me",
  "get task details", "show tasks in project X", "fetch Odoo tasks", "what's on my board",
  "what am I working on", "open tasks", "my Odoo board", "project tasks", "show me task #123",
  or any request to read project or task data from Odoo. Always use this skill — do NOT answer
  from memory or make up task data. Always call the real MCP tools.
compatibility:
  mcp: Go DO (url: https://odoo-mcp.giggso.com)
  tools:
    - Go DO:project_list_projects
    - Go DO:project_list_tasks
    - Go DO:project_list_task_stages
---

# Odoo Task Fetcher

Fetches live task and project data from Odoo via the **Go DO MCP connector**.
Always call the real tools — never invent or cache data.

---

## Open Tasks Filtering (applies to ALL listing scenarios)

Odoo stages that are closed/done are marked `fold: true`. When listing tasks, **always exclude tasks in folded stages** so only open/active work is shown.

**Steps:**
1. Call `project_list_task_stages` for the relevant project(s) to get stage metadata.
2. Build a set of **closed stage IDs**: stage IDs where `fold === true` OR the stage name matches a closed pattern (case-insensitive): `done`, `cancelled`, `canceled`, `closed`, `rejected`.
3. After fetching tasks, filter client-side: **drop any task whose `stage_id` is in the closed set**.
4. If no stage data is available (MCP error or no stages returned), show all tasks but note: *(stages unavailable — showing all tasks including possibly completed ones)*.

For cross-project queries (e.g. "my tasks", "list all tasks"), call `project_list_task_stages` for each project that appears in the result set — collect all closed stage IDs before filtering.

---

## Default Behaviour — Bare "raven fetch"

When the user says **only** `raven fetch` (no project name, no extra keywords), execute the following steps automatically — no clarifying questions needed.

### Step 1 — Resolve the working project name from the manifest

Read `manifest.json` at the root of the current working directory. The working project name is stored at `manifest.project` (or `manifest.name` as a fallback). That string becomes the **Project** for this fetch.

```
Read: <cwd>/manifest.json
Extract: manifest.project  (fallback: manifest.name)
```

If `manifest.json` does not exist or the field is absent, **skip to Step 2b** (fetch across all Odoo projects).

### Step 2a — Resolve the Odoo project ID (manifest project found)

Call `project_list_projects` with `query: "<working project name>"` to find the matching Odoo project and its integer `id`.

```
Go DO:project_list_projects
  query: "<working project name>"
  limit: 5
```

If multiple results are returned, pick the one whose name is an exact (case-insensitive) match. If still ambiguous, list the candidates and ask the user to confirm. Then continue to **Step 3** using that single project ID.

### Step 2b — Fallback: fetch tasks across ALL projects (no manifest project)

If the manifest project is unavailable, call `project_list_tasks` with no `project_id` and `limit: 100`. The filter in Step 4 will apply across all results. Skip the per-project stage fetch in Step 5 and instead call `project_list_task_stages` for each unique `project_id` found in the user-filtered results.

```
Go DO:project_list_tasks
  project_id: null
  query: ""
  limit: 100
```

### Step 3 — Resolve the caller's Odoo user ID

Follow the same ID-resolution logic as **Scenario 4 — Step 1**:

- Extract the name prefix from `userEmail` (e.g. `m.abbasi@giggso.com` → `"abbasi"`).
- Call `project_list_tasks` with `query: "<extracted name>"` and `limit: 10`.
- Identify the numeric Odoo user ID that appears in `user_ids` across the returned tasks.
- Cache this ID in the session.

### Step 4 — Fetch tasks in the project and filter by user

For the **Step 2a** path:

```
Go DO:project_list_tasks
  project_id: <resolved project ID>
  query: ""
  limit: 100
```

Filter client-side: keep only tasks where `user_ids` **includes** the resolved caller's Odoo user ID.

For the **Step 2b** path, the tasks are already fetched — apply the same `user_ids` filter to those results.

### Step 5 — Filter to open tasks only

Call `project_list_task_stages` for the relevant project ID(s), build the closed stage set (see **Open Tasks Filtering**), and drop any task whose `stage_id` is in that set.

### Step 6 — Present results

**Single project (Step 2a path):**

```
## My Tasks — [Working Project Name]

| ID  | Title              | Stage       | Deadline   | Priority |
|-----|--------------------|-------------|------------|----------|
| 45  | Deploy to prod     | In Review   | 2026-07-01 | High     |
| 99  | Write tests        | To Do       | —          | Normal   |

> Project: **[Project Name]** · Assignee: **[Full Name]** (Odoo ID: N)
> Say "show task [ID]" to drill in, or "all tasks in [project]" to see the full project board.
```

**All projects (Step 2b path):** group results by project, same format as **Scenario 4 — Step 4**.

If no tasks are assigned to the caller, say:
> *"No open tasks assigned to you in **[Project Name / any project]**."*

---

## Supported Queries

### 1 — List All Projects

**Trigger phrases:** "list projects", "show all projects", "what projects exist", "my projects"

**Tool:** `Go DO:project_list_projects`

```
params:
  query: ""        ← empty = all projects
  limit: 50        ← raise if user expects more
```

**Output format:**
```
## Projects (N found)

| # | ID  | Name              | Description |
|---|-----|-------------------|-------------|
| 1 | 12  | Website Redesign  | ...         |
| 2 | 17  | Mobile App        | ...         |

> Tip: say "list tasks in [project name]" to drill in.
```

---

### 2 — List Tasks in a Particular Project

**Trigger phrases:** "tasks in [project]", "show [project] tasks", "what's in [project]"

**Steps:**
1. If user gave project name but no ID → call `project_list_projects` with `query: "<name>"` first to resolve the ID.
2. Call `project_list_task_stages` with the resolved `project_id` to identify closed stage IDs (`fold: true` or closed name pattern).
3. Call `project_list_tasks` with the resolved `project_id`.
4. Filter client-side: remove tasks whose `stage_id` is in the closed set (see **Open Tasks Filtering** above).

**Tool:** `Go DO:project_list_tasks`

```
params:
  project_id: <integer>   ← resolved from step 1
  query: ""               ← optional keyword filter
  limit: 50
```

**Output format:**
```
## Tasks — [Project Name] (N tasks)

| ID   | Title              | Stage       | Assignee       | Deadline   | Priority |
|------|--------------------|-------------|----------------|------------|----------|
| 101  | Fix login bug      | In Progress | ali@company.com| 2026-07-01 | High     |
| 102  | Update docs        | To Do       | —              | —          | Normal   |

> Say "get details of task 101" for full info.
```

---

### 3 — Get Details of a Particular Task

**Trigger phrases:** "details of task [ID/name]", "show task [ID]", "tell me about task [N]", "open task [ID]"

**Steps:**
1. If user gives a task ID → call `project_list_tasks` with `query: "<id or name>"` and `limit: 5`.
   - If user already listed tasks in this session, match from the prior result.
2. Present all available fields in a structured card.

**Tool:** `Go DO:project_list_tasks`

```
params:
  query: "<task name or id>"
  limit: 5
```

**Output format (Task Detail Card):**
```
## Task Detail — #[ID]: [Title]

- **Project:**   [project name]
- **Stage:**     [stage name]
- **Assignees:** [user1, user2]
- **Priority:**  [Normal / High]
- **Deadline:**  [date or —]
- **Tags:**      [tag1, tag2]
- **Description:**
  [full description text, or "(no description)"]
```

---

### 4 — List Tasks Assigned to Me

**Trigger phrases:** "my tasks", "tasks assigned to me", "what am I working on", "my board", "assigned to me"

**Important:** The Go DO connector does NOT auto-scope to the authenticated caller. `query: "me"` is unreliable.
Always resolve the caller's **numeric Odoo user ID** first, then filter task data by that ID.

**Steps:**

**Step 1 — Resolve caller's Odoo user ID**
- The caller's email is available in session context (`userEmail`).
- Extract the last name or username prefix from the email (e.g. `firstname.lastname@company.com` → `"lastname"`).
- Call `project_list_tasks` with `query: "<extracted name>"` and `limit: 10`.
- Inspect the `user_ids` arrays in the returned tasks. The numeric ID that consistently appears across tasks referencing the caller's name is their Odoo user ID.
- If no name-match tasks return a clear signal, call `project_list_tasks` with `limit: 100` (no query) and look for an onboarding/welcome task like `"Welcome [Full Name]!"` — the `user_ids` on that task contains the caller's ID.
- **Cache this numeric ID** in the session — do not re-resolve on follow-up queries.

**Step 2 — Fetch all tasks and filter client-side by user ID**
- Call `project_list_tasks` with no query and `limit: 100`.
- Filter client-side: keep only tasks where the `user_ids` array **includes** the resolved numeric ID.

**Step 3 — Filter to open tasks only**
- Collect the unique `project_id` values from the user-filtered results.
- For each project ID, call `project_list_task_stages` to get stage metadata.
- Build the closed stage ID set (see **Open Tasks Filtering** above).
- Drop tasks whose `stage_id` is in the closed set.

**Step 4 — Group and present**
- Group results by project.
- If the resolved ID is uncertain, state the assumption explicitly and ask the user to confirm their Odoo user ID.

**Tools:**

```
# Step 1 — ID resolution
Go DO:project_list_tasks
  query: "<name extracted from caller email>"
  limit: 10

# Step 2 — Full task fetch
Go DO:project_list_tasks
  project_id: null
  query: ""
  limit: 100
```

**Output format:**
```
## My Tasks — [Full Name] (N total)

### [Project A]
| ID  | Title         | Stage       | Deadline   | Priority |
|-----|---------------|-------------|------------|----------|
| 45  | Deploy to prod| In Review   | 2026-06-30 | High     |

### [Project B]
| ID  | Title         | Stage       | Deadline   | Priority |
|-----|---------------|-------------|------------|----------|
| 99  | Write tests   | To Do       | —          | Normal   |

> Resolved Odoo user ID: **[N]**. Say "show task [ID]" to drill in.
```

---

## Error Handling

| Error | Action |
|---|---|
| MCP returns empty list | Say "No results found" — do NOT fabricate data |
| Project name ambiguous | Show list of matches and ask user to confirm |
| Task ID not found | Say "Task not found" and suggest listing tasks in the project |
| MCP auth/connection error | Tell the user to check Go DO connector is connected in Settings |

---

## Tool Quick Reference

| Intent | Primary Tool | Key Params |
|---|---|---|
| List all projects | `project_list_projects` | `query`, `limit` |
| Tasks in project | `project_list_tasks` | `project_id`, `limit` |
| Task detail | `project_list_tasks` | `query: "<name/id>"`, `limit: 5` |
| My tasks (ID resolve) | `project_list_tasks` | `query: "<name from email>"`, `limit: 10` |
| My tasks (full fetch) | `project_list_tasks` | `project_id: null`, `limit: 100`, filter by `user_ids` |
| Stage names | `project_list_task_stages` | `project_id` |

---

## Rules

1. **Always call live MCP tools** — never answer from training data or session memory alone.
2. **Resolve names to IDs** — if user says a project name, call `project_list_projects` first.
3. **Show IDs in output** — users need task IDs for follow-up actions.
4. **Respect limits** — default to 50; if user says "all", raise to 100 and note if truncated.
5. **Group by project** when mixing tasks from multiple projects.
6. **Offer next steps** — after listing, suggest: drill into a task, filter by stage, or create/update a task.
7. **Default to open tasks only** — always apply the Open Tasks Filtering to exclude done/cancelled/closed stages unless the user explicitly asks to include completed tasks (e.g. "show all tasks including done", "show completed tasks").