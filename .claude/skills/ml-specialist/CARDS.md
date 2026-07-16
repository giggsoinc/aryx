# ML Plan Card Templates

Version: 1.0 · Used by: ml-specialist at session end

Each card is filled during its stage. All 8 cards assembled into the final ML Plan
saved to `.raven/ml-plans/{date}-{topic-slug}.md`.

---

## Card 1 — Data Card (S2)

```markdown
## Data Card
Generated: {date} · Stage: S2 · Signed off: {yes/no}

| Field | Value |
|---|---|
| Format | tabular / text / image / audio / time-series / graph / multi-modal |
| Volume | rows / tokens / GB |
| Labels | yes / no / partial — X% labeled |
| Quality | clean / issues: {list} |
| Privacy class | public / internal / PII / PHI / PCI |
| Streaming | yes / no / hybrid |
| Drift risk | low / medium / high — {reason} |
| Schema | {brief description or link} |
| Notes | {anything material} |
```

---

## Card 2 — Metric Card (S3)

```markdown
## Metric Card
Generated: {date} · Stage: S3 · Signed off: {yes/no}

| Field | Value |
|---|---|
| Primary metric | {name} — {why chosen} |
| Guard metric 1 | {name} — threshold: {X} — reason: {why} |
| Guard metric 2 | {name} — threshold: {X} — reason: {why} |
| Business outcome | {what metric connects to} |
| FP cost | {in business terms} |
| FN cost | {in business terms} |
| Acceptable range | {e.g. precision ≥ 0.85} |
| Human eval required | yes / no — if yes, cadence: {frequency} |
```

---

## Card 3 — Architecture Card (S5)

```markdown
## Architecture Card
Generated: {date} · Stage: S5 · Signed off: {yes/no}

| Field | Value |
|---|---|
| Algorithm registry | YAML config / DB / code |
| Config strategy | global / per-tenant / per-domain / hybrid |
| Model versioning | MLflow / W&B / DVC / custom / none |
| Feature store | yes — {which} / no — {reason} |
| Training path | batch / stream / on-demand |
| Inference path | {from Deployment Card} |
| Train/serve separation | yes / no |
| Signed-off algorithm | {name from S4 candidate set} |
| Why chosen | {one sentence} |
```

---

## Card 4 — Training Plan (S6)

```markdown
## Training Plan
Generated: {date} · Stage: S6 · Signed off: {yes/no}

| Field | Value |
|---|---|
| Strategy | zero-shot / few-shot / RAG / transfer / fine-tune / full-train / active / self-supervised |
| Why this strategy | {one sentence — based on S2 data + S3 metric} |
| Data needed | {volume + label requirement} |
| Compute estimate | {GPU type, hours/days, cost estimate} |
| Base model (if any) | {name + version} |
| Framework | PyTorch / TF / JAX / scikit-learn / HuggingFace / other |
| Hyperparameter plan | grid / random / Bayesian / Optuna / none |
| Checkpointing | yes — cadence: {frequency} / no |
```

---

## Card 5 — Eval Plan (S7)

```markdown
## Eval Plan
Generated: {date} · Stage: S7 · Signed off: {yes/no}

| Field | Value |
|---|---|
| Split strategy | train/val/test: {ratios} / k-fold: {k} / temporal |
| Holdout policy | locked until deploy / periodic refresh |
| Primary metric | {from Metric Card} — CI threshold: {value} |
| Guard metrics | {from Metric Card} — thresholds |
| Slice metrics | {list: per-class, per-tenant, per-domain} |
| Calibration check | yes / no |
| Adversarial cases | {list top 3 edge cases} |
| Human eval | yes — cadence: {frequency} / no |
| CI gate | {metric} must be ≥ {threshold} to allow deploy |
```

---

## Card 6 — Deployment Card (S8)

```markdown
## Deployment Card
Generated: {date} · Stage: S8 · Signed off: {yes/no}

| Field | Value |
|---|---|
| Primary path | {headless API / batch / streaming / edge / agentic / cluster / embedded} |
| Why primary | {one sentence — connects to S2 data shape + S3 latency} |
| Fallback path | {name — when to use} |
| Infra required | {compute type, memory, GPU?, storage} |
| Latency SLO | p50: {X}ms / p95: {X}ms / p99: {X}ms |
| Throughput target | {req/s or rows/batch} |
| Cold start risk | low / medium / high — mitigation: {how} |
| Cost estimate | ${X}/request or ${X}/month at {volume} |
```

---

## Card 7 — Lifecycle Card (S9)

```markdown
## Lifecycle Card
Generated: {date} · Stage: S9 · Signed off: {yes/no}

| Field | Value |
|---|---|
| Drift detection | data / label / concept — tool: {name} |
| Regression alarm | metric: {name} — floor: {threshold} — alert: {channel} |
| Retraining trigger | {N corrections} OR {time elapsed} OR {drift score} |
| Rollback strategy | blue-green / shadow mode / canary |
| Cost monitoring | per-request / per-batch / monthly total |
| Audit logs | yes — captures: {input, output, version, timestamp, caller} |
| Retrain cadence | estimated: {frequency} |
| Model registry | {MLflow / W&B / DVC / other} |
```

---

## Card 8 — Risk Card (S10)

```markdown
## Risk Card
Generated: {date} · Stage: S10 · Signed off: {yes/no}

| Field | Value |
|---|---|
| Hallucination risk | low / medium / high — mitigation: {how} |
| Bias audit | required / done — tool: {name} — outcome: {result} |
| Cost ceiling | ${X}/request or ${X}/month |
| Latency SLO | p99 ≤ {X}ms |
| Privacy | PII present: yes/no — handling: {method} |
| Training data leakage | risk: low/medium/high — mitigation: {how} |
| Compliance | GDPR / HIPAA / SOC2 / CCPA / none |

### Failure Modes (top 5)
| # | Mode | Likelihood | Mitigation |
|---|---|---|---|
| 1 | {mode} | low/medium/high | {mitigation} |
| 2 | {mode} | low/medium/high | {mitigation} |
| 3 | {mode} | low/medium/high | {mitigation} |
| 4 | {mode} | low/medium/high | {mitigation} |
| 5 | {mode} | low/medium/high | {mitigation} |
```

---

## ML Plan — Final Assembly Template

Saved to `.raven/ml-plans/{YYYY-MM-DD}-{topic-slug}.md`

```markdown
# ML Plan — {topic}
Date: {YYYY-MM-DD} · Owner: {team/person} · Status: draft / approved

## Problem Statement (S0)
{one sentence from S0 gate}

## Problem Type (S1)
{type} — {brief rationale}

{Data Card}
{Metric Card}
{Architecture Card}
{Training Plan}
{Eval Plan}
{Deployment Card}
{Lifecycle Card}
{Risk Card}

## Sign-Off Summary
| Stage | Approved | Notes |
|---|---|---|
| S0 Entry Gate | yes/no | {notes} |
| S1 Problem Type | yes/no | {notes} |
| S2 Data Audit | yes/no | {notes} |
| S3 Success Metrics | yes/no | {notes} |
| S4 Algorithm Classes | yes/no | {notes} |
| S5 Architecture | yes/no | {notes} |
| S6 Training Strategy | yes/no | {notes} |
| S7 Eval Harness | yes/no | {notes} |
| S8 Deployment | yes/no | {notes} |
| S9 Lifecycle | yes/no | {notes} |
| S10 Risk + Ethics | yes/no | {notes} |

## Deferred / Skipped
{list any stages skipped with reason — honesty required}

## Next Steps
{list of action items, owners, dates}
```
