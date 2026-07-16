---
name: raven-blueteaming
description: Defensive remediation skill. Triggered after raven-trinity when user declines to commit due to MEDIUM/HIGH risk. Loads trinity attack results and recommendations, calls Andie in Kaizen mode to root-cause and patch the vulnerable API code, saves a full audit report, then offers to re-run trinity to verify fixes closed the vulnerabilities.
allowed-tools:
  - Bash
  - Read
  - Edit
  - Write
---

# /raven-blueteaming

Defensive counterpart to `/raven-trinity`. Where trinity finds vulnerabilities, blueteaming fixes them.

**Critical Rule:** Never apply code fixes without showing the diff and receiving explicit user confirmation. All Andie outputs are proposals until the user types Y.

---

## Step 1 — Load Trinity Context

If invoked from trinity Step 8 (data passed directly) → use passed context.
If invoked manually:
- No argument → find most recent `reports/trinity-*.json` by timestamp:
  `python -c "import glob,os; files=glob.glob('reports/trinity-*.json'); print(max(files, key=os.path.getmtime) if files else '')"`
- Argument provided → use that path directly.

If no report found → `"No trinity report found in reports/. Run /raven-trinity first."` → exit.

Display summary:
```
BLUE-TEAM SESSION
─────────────────
Asset:      <asset_name>
URL:        <endpoint_url>
Risk Level: <HIGH / MEDIUM>
Attacks:    <successful_attacks> / <total_prompts>
Categories: <cat1> (n), <cat2> (n), ...
Recs:       <count> recommendations
Report:     <trinity_report_path>
```

Extract and store: `attack_results[]`, `recommendations[]`, `risk_level`, `risk_breakdown`, `asset_name`, `endpoint_url`, `request_path`, `response_path`, `trinity_report_path`.
Read `user_email`, `project_name`, `raven_version` from `.raven/manifest.json`.

## Step 2 — Mode Selection

Auto-select Andie mode based on risk and attack spread:

| Condition | Suggested mode |
|---|---|
| HIGH risk (≥5 attacks) OR multiple attack categories | Kaizen — DMAIC |
| MEDIUM risk (2–4 attacks), single category | Kaizen — 5 Whys |
| Single attack, tightly scoped problem | Kaizen — A3 Thinking |

Show suggestion — **STOP. WAIT for confirmation.**
> "Andie mode: `<suggested>` — confirm (Enter) or choose:
>  1. DMAIC (systematic, multi-vulnerability)
>  2. 5 Whys (single failure chain, root cause)
>  3. A3 Thinking (focused, one-page clarity)
>  4. Deep (understand the attacks first, then fix)"

Store `andie_mode`.

If Deep selected → run Andie Deep mode rounds to explain the attack vectors. After Deep completes, ask:
> "Ready to fix? Switch to Kaizen now? [Y/n]"
→ If Y: re-present Kaizen option menu and continue from Step 3.

## Step 3 — Find API Code

Locate the route handler for `asset_name`:
- `git log --name-only --pretty=format: -5` → filter Python files
- `grep -rn "@app.\|@router." --include="*.py"` → match route path to `asset_name`
- If not found → **STOP. Ask:**
  > "Which file contains the route handler for `<asset_name>`? Type path:"

Read the handler file. Follow one import hop to the Pydantic model (same logic as trinity Step 2).
Scan handler for system prompt / LLM context strings (`system`, `context`, `instructions`, `SYSTEM_PROMPT`).
Store `handler_file`, `handler_code`, `model_code`, `system_prompt_snippet` (if found).

## Step 4 — Build Andie Brief + Invoke

Load `skills/andie/SKILL.md` then load only the selected mode file:
- DMAIC / 5 Whys / A3 → `skills/andie/modes/kaizen.md`
- Deep → `skills/andie/modes/deep.md`

Pass this brief to Andie:

```
BLUE-TEAM BRIEF
───────────────
Asset:    <asset_name> (<endpoint_url>)
Risk:     <risk_level> — <successful_attacks> attacks succeeded

SUCCESSFUL ATTACKS:
[1] Category: <category>
    Prompt:   <prompt>
    Response: <response>
[2] ...

TRINITY RECOMMENDATIONS:
• <rec 1>
• <rec 2>
• ...

API CODE — route handler (<handler_file>):
<handler_code>

API CODE — request model:
<model_code>

SYSTEM PROMPT (if present):
<system_prompt_snippet>

TASK:
Using <andie_mode>, root-cause each successful attack and produce specific,
implementable code patches. For each fix:
  - State which attack(s) it closes
  - Show exact code change (before → after)
  - Explain why it closes the vulnerability
```

Andie runs its method:
- **DMAIC:** Define (what vulnerability) → Measure (attack rate) → Analyze (why it works) → Improve (code patch) → Control (prevent recurrence)
- **5 Whys:** Chain of why for each attack vector → root cause → targeted fix
- **A3 Thinking:** Background → Current state → Target state → Gap → Countermeasures → Verification plan

## Step 5 — HITL Gate + Apply Fixes

After Andie produces the fix plan, display it in full. **STOP. WAIT.**
> "Apply these fixes to `<handler_file>`? [Y/n/edit]"
- **Y** → apply each patch using Edit tool. Show diff per file before writing.
- **n** → end session. No files changed.
- **edit** → user types override instructions. Andie revises. Return to this gate.

Apply in order (if all present):
1. Input validation / sanitization (before model call)
2. System prompt hardening (constrain model scope)
3. Output filtering / guard layer (after model response)
4. Reject patterns for known attack structures

Store `files_modified[]`, `fix_summary` (one-line per fix).

## Step 6 — Save Blueteam Report

Timestamp: `python -c "from datetime import datetime; print(datetime.utcnow().strftime('%Y-%m-%d-%H-%M'))"`
Slug: replace `/` in `asset_name` with `-`
Git commit: `git rev-parse HEAD`
Branch: `git rev-parse --abbrev-ref HEAD`
OS user: env `USERNAME`

Write `reports/blueteam-<timestamp>-<slug>.json`:
```json
{
  "timestamp_utc":            "<ISO 8601>",
  "email":                    "<user_email>",
  "project_name":             "<project_name>",
  "raven_version":            "<raven_version>",
  "git_branch":               "<branch>",
  "git_commit_before_fix":    "<commit hash>",
  "os_user":                  "<USERNAME>",
  "asset_name":               "<asset_name>",
  "endpoint_url":             "<endpoint_url>",
  "trinity_report":           "<trinity_report_path>",
  "trinity_risk_level":       "<HIGH|MEDIUM>",
  "andie_mode":               "<DMAIC|5 Whys|A3 Thinking|Deep+DMAIC>",
  "vulnerabilities_addressed": [
    {"category": "...", "attack_prompt": "...", "fix_applied": "..."}
  ],
  "fix_summary":              "<Andie plan summary>",
  "files_modified":           ["<path1>", "<path2>"],
  "rerun_result":             "pending",
  "rerun_report":             null
}
```

Write `reports/blueteam-<timestamp>-<slug>.md`:
```
BLUE-TEAM REMEDIATION REPORT
─────────────────────────────
Asset:        <asset_name>
URL:          <endpoint_url>
Trinity Risk: <risk_level>
Andie Mode:   <andie_mode>
Files Fixed:  <handler_file>

FIXES APPLIED:
  [1] <category> — <one-line fix description>
  [2] ...

RECOMMENDATIONS ADDRESSED:
  • <rec 1>
  • ...

Status: PENDING VERIFICATION
Run /raven-trinity to verify fixes.
```

Show: `"Report saved: \`reports/blueteam-<timestamp>-<slug>.md\`"`

## Step 7 — Verify Loop

> "Fixes applied. Re-run /raven-trinity to verify vulnerabilities are closed? [Y/n]"

**If Y:**
Invoke `/raven-trinity` with `endpoint_url` and `asset_name` pre-filled.
Skip trinity Step 1 (endpoint already known). Start from trinity Step 2.

After trinity completes:
- Update `reports/blueteam-<timestamp>-<slug>.json`:
  - `rerun_result` → new trinity risk level
  - `rerun_report` → path to new trinity report
- Append to `.md` report:

If CLEAR or LOW:
```
VERIFICATION PASSED ✓
New risk level: <CLEAR|LOW>
All critical vulnerabilities closed.
Commit is clear to proceed.
```

If MEDIUM or HIGH:
```
VERIFICATION INCOMPLETE ✗
Remaining risk: <level> — <n> attacks still succeeded.
Run /raven-blueteaming again to address remaining vulnerabilities.
```

**If N:** End session. Report `rerun_result` stays `"pending"`.
