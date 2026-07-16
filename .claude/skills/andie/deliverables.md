# Andie Deliverables — Loaded at Session Close

## Deliverable Contracts

### Deep Mode Deliverable Template
```markdown
# Deep Session — {topic} — {date}

## Expert Used
{Name} — {domain} specialist

## Framework Applied
{Framework name} — {why it fit}

## Core Understanding
{Feynman-clarity explanation}

## Mental Model
- {concept 1} = {analogy}
- {concept 2} = {analogy}

## What Breaks (Edge Cases)
- {failure mode 1}
- {failure mode 2}

## Next Level Down
- {deeper topic 1} → for the next session
- {deeper topic 2} → resources/framework

## Session Stats
- Mode: Deep · Rounds: N · Tokens: ~N
```

### Kaizen Mode Deliverable Template
```markdown
# Kaizen Session — {topic} — {date}

## Method Used
{Kaizen Cycle / Ishikawa / 5 Whys / DMAIC / Pareto / A3}

## Cycles Completed
| Cycle | Root Cause | Fix Hypothesis | Verify Criteria | Status |
|-------|-----------|----------------|-----------------|--------|

## Root Causes Fixed
- [ ] {cause 1} → fixed by {action}
- [ ] {cause 2} → fixed by {action}

## Remaining
- [ ] {cause 3 — for next cycle}

## Pattern Observed
{Systemic insight from this session}

## Recommendation
{What to do next}

## Session Stats
- Method: {X} · Cycles: N · Tokens: ~N
```

### War Mode Deliverable Template
```markdown
# Incident Report — {topic} — {date}

## Timeline
| Time | Action | Result | Owner |
|------|--------|--------|-------|

## Root Cause (if identified)
{X}

## Containment
- {action 1}
- {action 2}

## Resolution
{What fixed it}

## Prevention
{How to stop recurrence}

## Escalation (if triggered)
- {who} at {time}
- {escalation chain}

## Status
🟢 Resolved / 🟡 Monitoring / 🔴 Ongoing

## Session Stats
- T+{minutes} resolution · Tokens: ~N
```

### Drama Mode Deliverable Template
```markdown
# Drama Session — {topic} — {date}

## Decision
{One clear sentence}

## Rationale
{Why this won}

## Panel Members
- {Name} ({role}) → final position
- {Name} ({role}) → final position
- {Name} ({role}) → final position

## Alternatives Rejected
| Option | Why Rejected |
|--------|-------------|

## Action Plan
| # | Action | Owner | By When | Priority |
|---|--------|-------|---------|----------|

## Risks
- **Blocked Dev**: {risk if this breaks at 3am}
- **Boundary Pusher**: {risk if assumption is wrong}
- **CFO/Legal/Customer**: {compliance/adoption risk if any}

## Open Questions
- [ ] {question} → needs {who/what}

## Session Stats
- Rounds: N · Panel: {count} · Tokens: ~N
```

## Visuals — Diagram Offerings

RULE: Offer at session close; do not auto-generate. User chooses diagram type + tool.

### Diagram Types (by Mode)

**Deep Mode Diagrams:**
- 🧠 **Concept Map** — topic hierarchy, connections, dependencies (best in Napkin.ai or Excalidraw)
- 📚 **Learning Path** — sequence of concepts, prerequisites (Mermaid flowchart)
- 🎯 **Mental Model** — how pieces fit together (Excalidraw whiteboard)

**Kaizen Mode Diagrams:**
- 🔁 **Kaizen Cycle** — PDCA loop, improvement iterations (Mermaid)
- 🦴 **Ishikawa Fishbone** — causes by 6M category (draw.io or Napkin.ai)
- 📊 **Pareto Chart** — vital few (80/20) visualization
- 📋 **A3 Thinking** — single-page problem summary (Napkin.ai)

**War Mode Diagrams:**
- 📅 **Incident Timeline** — annotated by status (Mermaid or Napkin.ai)
- 🚨 **Escalation Tree** — decision path, owners, SLAs (Mermaid)

**Drama Mode Diagrams:**
- ⚙️  **Architecture Decision** — option A vs B, trade-offs (draw.io or Excalidraw)
- 🎭 **Decision Tree** — choices, branches, outcomes (Mermaid)
- 📍 **Risk Map** — likelihood × impact (Napkin.ai)

### Tool Comparison

| Tool | Best For | Export | Effort |
|------|----------|--------|--------|
| **Mermaid** | code-based, GitHub-native, OODA/timeline | GitHub/Notion/Claude native | Low |
| **Napkin.ai** | auto-layout, sharing, concept maps | PNG/SVG/PDF | Low |
| **Excalidraw** | whiteboard feel, freehand, brainstorm | PNG/SVG | Medium |
| **draw.io** | structured, professional, PDF export | SVG/PDF/XML | Medium |

### Offering Template

```
Want me to visualize this?

Diagram options:
  🧠 Concept Map   — topic hierarchy
  📚 Learning Path — prerequisites
  🔁 Kaizen Cycle  — PDCA iterations
  🦴 Fishbone      — causes by category
  📅 Timeline      — incident sequence
  🎭 Decision Tree — option branches

Tool: Mermaid (default) / Napkin.ai / Excalidraw / draw.io

Pick one (or say "skip" if no diagram needed).
```

## Handoff Contract

Every handoff must include:
- Target skill or owner
- Current mode
- Goal
- Constraints
- Decisions already accepted
- Open questions
- Risks
- Recommended next step

RULE: The receiving specialist should be able to continue without rereading the whole conversation.
