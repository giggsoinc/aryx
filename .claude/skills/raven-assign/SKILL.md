---
name: raven-assign
description: Recommend the best-fit developer for a job card by scoring capability match, current workload, contribution history, and IAM hygiene — for the PM to vet and assign via the Odoo MCP. Gates sensitive/deploy work to hygienic identities.
metadata:
  phase: Plan
  trigger: After raven-spec, before a card is assigned
  primary_actor: PM (assisted)
---

# raven-assign

## Purpose
Replace ad-hoc assignment with an objective, hygiene-aware recommendation.

## When it triggers
After `raven-spec` produces the cards, before assignment.

## Inputs
- Card required capability + criticality
- Developer workload (Odoo)
- Contribution history (Raven / raven-contribute)
- IAM Hygiene Score (GREaaS)

## What it does
1. Scores candidate developers on capability match, current load, relevant contribution history, and IAM hygiene.
2. Gates sensitive or deploy-path work to identities at/above **FAIR** hygiene.
3. Returns a ranked recommendation with rationale; the PM vets and assigns via the **Odoo MCP**.

## Output
```json
{ "recommended_assignee": "", "rationale": "", "alternates": [], "hygiene_flag": "OK|REVIEW" }
```

## Why it's required
Ad-hoc assignment overloads some, under-uses others, and can place sensitive work on a low-hygiene identity.

## Benefit
Right person, balanced load, and hygiene-gated assignment for sensitive work.

## Interactions 
Reads **Odoo (MCP)** assigns the **raven-spec** card.
