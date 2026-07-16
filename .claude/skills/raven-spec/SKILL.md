---
name: raven-spec
description: Turn a PRD and a Technical Design Document into ready-to-build job cards — each carrying an objective/intent, a formatted base prompt, and a core (non-negotiable) + extended test set. Invoke at sprint planning before any card is created.
metadata:
  phase: Plan
  trigger: Architect / PM at sprint planning
  primary_actor: Architect / Project Manager
---

# raven-spec

## Purpose
Standardise **step 0** of the loop: the person who understands the product (architect/PM) authors intent on the board, before any code, instead of leaving the developer to reverse-engineer it.

## When it triggers
At sprint planning, run by the architect/PM, reading the project's **PRD** and **TDD** (which contains the core test cases that define success).

## Inputs
- PRD (scope, goals, features)
- TDD with **core test cases** (the non-negotiable definition of success) and any extended cases
- Repo/codebase context (via Raven)

## What it does
1. Parses the PRD + TDD and identifies the features/changes for the sprint.
2. Decomposes them into a sprint and a set of job cards (and sub-tasks) with proper HTML formatting.
3. For each card, emits a standard artifact: **objective/intent**, a **base prompt** (what/why/constraints/acceptance — never the *how*), the **core tests + extended tests**, a **deadline** (sprint end = today + 1 day), and **tags** from the PRD/TDD context.
4. Presents the cards for the PM to vet, then hands off to `raven-assign` and pushes to Odoo via the Claude Odoo MCP.

## Output — standard artifact (per card)
```json
{
  "title": "", "objective": "", "base_prompt": "",
  "acceptance_criteria": [], "core_tests": [], "extended_tests": [],
  "priority": "", "suggested_assignee": null, "project": "",
  "deadline": "", "tags": []
}
```

## Deadline rule
Each sprint is **1 day**. Set the `deadline` of every card to `today + sprint_number` days:
- Sprint 1 → today + 1 day
- Sprint 2 → today + 2 days
- Sprint 3 → today + 3 days
- Sprint N → today + N days

The PM may override any deadline explicitly.

## Tags
Every card must include relevant `tags` drawn from the PRD/TDD context (e.g. feature area, component, priority label). Propose tags and confirm with the PM before pushing to Odoo.

## Why it's required
Intent must be authored by the right person, on the board, before code — and every card must ship with an objective definition of success.

## Benefit
Every card carries traceable intent and a success definition: spec-driven AI development straight from the board.

## Interactions
Feeds **raven-assign**; cards pushed to **Odoo (MCP)**; consumed downstream by **Andie** 
