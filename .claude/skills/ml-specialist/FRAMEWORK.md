# Raven ML Discipline Framework — 10-Stage Pipeline

Version: 1.0 · Owner: ml-specialist · Coordinates with: aiml-specialist (S4–S5), ml-ops-specialist (S8–S9)

---

## Why This Framework Exists

Loose ML advice produces loose ML systems. A user saying "help me build a classifier"
will get algorithm talk when they need a plan. This framework forces the conversation
through a structured pipeline so every session ends with a defensible, executable ML Plan —
not a vibe.

**The rule:** No stage is skippable. No silent advancement. Discipline is the product.

---

## The 10 Stages

### S0 — Entry Gate

**Goal:** Establish the business problem in one concrete sentence.

Ask:
> "What problem are we solving for the business? One sentence — no technical terms."

**Reject if:**
- "I want to do ML on my data" — too vague
- "Something with NLP" — no outcome
- "Make our app smarter" — unmeasurable

**Accept if:**
- "Classify customer support tickets into 8 categories to reduce triage time"
- "Predict churn 30 days out with ≥ 0.80 AUC so we can intervene"
- "Generate structured summaries of legal contracts under 200 tokens"

**Output:** A one-sentence problem statement the user has signed off on.

⏸ HITL GATE — get approval before S1.

---

### S1 — Problem Typing

**Goal:** Force the user to name the ML problem type. No guessing, no skipping.

Present the taxonomy and ask which fits:

| Type | Definition | Example |
|---|---|---|
| **Classification** | Assign to one of N categories | Spam/not spam, ticket category |
| **Regression** | Predict a continuous value | Price, score, duration |
| **Generation** | Produce new content | Summaries, code, answers |
| **Clustering** | Group without labels | Customer segments |
| **Ranking** | Order items by relevance | Search results, recommendations |
| **Recommendation** | Suggest items to users | "You may also like" |
| **Reinforcement** | Learn from feedback loops | Game play, routing |
| **Multi-task / Hybrid** | Multiple objectives combined | Classify + explain |

**If hybrid:** Decompose into constituent tasks. Handle each independently through S2–S10,
then recombine at S5 (Architecture).

**Output:** Confirmed problem type(s).

⏸ HITL GATE — get approval before S2.

---

### S2 — Data Audit

**Goal:** Know exactly what data exists before touching an algorithm.

Required questions:
- What data exists? Format (tabular, text, image, audio, time-series, graph)?
- Volume? (rows / tokens / hours / GB)
- Labels? (yes / no / partial — what % labeled?)
- Quality? (missing values, duplicates, schema drift?)
- Privacy class? (public / internal / PII / PHI / PCI)
- Drift expected? (seasonal, behavioral, distribution shift?)
- Streaming or batch?
- Multi-modal? (e.g., text + image)

**Output: Data Card**
```
Data Card
─────────────────────────────────────────────
Format:        [tabular / text / image / ...]
Volume:        [rows / tokens / GB]
Labels:        [yes / no / partial — X% labeled]
Quality:       [clean / issues: ...]
Privacy:       [public / PII / PHI / ...]
Streaming:     [yes / no / hybrid]
Drift risk:    [low / medium / high — reason]
Notes:         [anything else material]
─────────────────────────────────────────────
```

⏸ HITL GATE — get approval before S3.

---

### S3 — Success Metrics

**Goal:** Map business outcome → ML metric. These are not the same thing.

Force calibration:
> "What's the cost of a false positive vs a false negative in your system?"

Common mappings:

| Business outcome | ML metric(s) |
|---|---|
| "Accurate predictions" | Accuracy, macro F1 |
| "Catch all bad actors" | Recall (minimize false negatives) |
| "Don't annoy good users" | Precision (minimize false positives) |
| "Rank relevant items" | NDCG, MRR, MAP |
| "Good summaries" | ROUGE-L, BERTScore, human eval |
| "Revenue optimization" | Lift, A/B delta, counterfactual |
| "Churn prediction" | AUC-ROC, precision at K |

**Output: Metric Card**
```
Metric Card
─────────────────────────────────────────────
Primary metric:    [name — why chosen]
Guard metrics:     [name — threshold — reason]
Business outcome:  [what metric connects to]
FP cost:           [describe in business terms]
FN cost:           [describe in business terms]
Acceptable range:  [e.g. precision ≥ 0.85]
Human eval:        [yes / no — if generative]
─────────────────────────────────────────────
```

⏸ HITL GATE — get approval before S4.

---

### S4 — Algorithm Classes *(aiml-specialist leads)*

**Goal:** Present candidate algorithm families — never jump to one choice.

See `ALGORITHMS.md` for the full catalog. Always present 3+ candidates with tradeoffs:
- Cost (compute, data, infra)
- Latency (training and inference)
- Interpretability (black box vs explainable)
- Data need (labels, volume)
- Maintenance burden

**Output:** Candidate set (≥ 3) with signed-off recommendation.

⏸ HITL GATE — get approval before S5.

---

### S5 — Architecture *(aiml-specialist leads)*

**Goal:** Force plug-and-play discipline. No hardwired algorithm choices.

Required output components:
- **Swappable algorithm registry** — YAML config-driven, algorithm is a parameter not code
- **Per-domain / per-tenant config** — different behavior per org/segment
- **Versioned model artifacts** — model registry with semantic versioning
- **Feature store decision** — yes / no / which one (Feast, Tecton, Hopsworks, none)
- **Training / inference path separation** — training pipeline ≠ serving path

**Output: Architecture Card**
```
Architecture Card
─────────────────────────────────────────────
Algorithm registry:   [YAML / DB / code]
Config strategy:      [global / per-tenant / hybrid]
Model versioning:     [MLflow / W&B / custom / none]
Feature store:        [yes — which / no — reason]
Training path:        [batch / stream / on-demand]
Inference path:       [API / batch job / embedded / ...]
Separation enforced:  [yes / no]
─────────────────────────────────────────────
```

⏸ HITL GATE — get approval before S6.

---

### S6 — Training Strategy

**Goal:** Choose the training approach that matches data availability and cost budget.

Options (present as a decision tree based on data volume + label availability):

| Strategy | When | Data needed | Compute |
|---|---|---|---|
| **Zero-shot** | No training data | None | LLM API cost only |
| **Few-shot** | < 100 examples | 5–100 labeled | LLM API cost only |
| **RAG** | Facts change / external KB | Unlabeled docs | Embedding + retrieval |
| **Transfer learning** | < 10k labeled | Pre-trained base | 1 GPU, hours |
| **Fine-tuning** | 10k–1M labeled | Good labels | Multi-GPU, days |
| **Full training** | > 1M + custom domain | Clean large dataset | Multi-GPU, weeks |
| **Active learning** | Labels expensive | Grows over time | Iterative |
| **Self-supervised** | Unlabeled abundant | No labels | Multi-GPU |

**Output:** Signed-off training strategy with data + compute estimate.

⏸ HITL GATE — get approval before S7.

---

### S7 — Evaluation Harness

**Goal:** Define an evaluation plan that runs in CI — not ad hoc.

Required components:
- **Split strategy:** train/val/test · k-fold · temporal (for time-series — never shuffle)
- **Holdout policy:** final test set is locked — no peeking, no tuning
- **Calibration:** does confidence score match actual accuracy?
- **Adversarial / edge cases:** known hard examples, boundary conditions
- **Slice metrics:** per-class, per-tenant, per-domain (overall metrics can hide failures)
- **Human eval:** required if generative output

**Output: Eval Plan**
```
Eval Plan
─────────────────────────────────────────────
Split:           [train/val/test — ratios — method]
Holdout policy:  [locked / periodic refresh]
Primary metric:  [from Metric Card]
Guard metrics:   [from Metric Card — with thresholds]
Slice metrics:   [list segments]
Calibration:     [yes / no]
Human eval:      [yes / no — cadence]
CI gate:         [metric threshold that blocks deploy]
─────────────────────────────────────────────
```

⏸ HITL GATE — get approval before S8.

---

### S8 — Deployment Architecture *(ml-ops-specialist leads)*

**Goal:** Pick ONE primary deployment path + one fallback. Force tradeoff discussion.

See `DEPLOYMENT.md` for the full 7-path deep-dive.

**The 7 paths:**
1. Headless API (FastAPI / FastMCP)
2. Batch job (cron, Prefect, Airflow)
3. Streaming worker (Kafka consumer, queue)
4. Edge / on-device (CoreML, ONNX, TFLite)
5. Agentic loop (LangGraph / OpenAI agents / custom MCP)
6. Cluster (K8s + KServe / Ray Serve / Triton)
7. Embedded in app (in-process)

Force this question:
> "Given your data shape from S2 and latency budget from S3 — which deployment path fits?"

**Output: Deployment Card**
```
Deployment Card
─────────────────────────────────────────────
Primary path:    [name — why it fits S2 + S3]
Fallback path:   [name — when to switch]
Infra required:  [compute, memory, GPU?, storage]
Latency SLO:     [p50 / p95 / p99 targets]
Throughput:      [req/s or rows/batch]
Cold start:      [acceptable / mitigated how]
Cost estimate:   [$/month at expected volume]
─────────────────────────────────────────────
```

⏸ HITL GATE — get approval before S9.

---

### S9 — Monitoring + Lifecycle *(ml-ops-specialist leads)*

**Goal:** A model without monitoring is a liability, not an asset.

See `LIFECYCLE.md` for the full deep-dive.

Required components:
- **Drift detection:** data drift · label drift · concept drift
- **Regression alarms:** metric floor — if primary metric drops below threshold → alert
- **Retraining triggers:** N corrections accumulated · time elapsed · drift detected
- **Rollback strategy:** blue/green · shadow · canary
- **Cost monitoring:** inference cost per request, batch cost per run
- **Audit logs:** who called it, what input, what output, what version

**Output: Lifecycle Card**
```
Lifecycle Card
─────────────────────────────────────────────
Drift detection:     [data / label / concept — tool]
Regression alarm:    [metric — threshold — alerting]
Retraining trigger:  [N corrections / time / drift]
Rollback:            [blue-green / shadow / canary]
Cost monitoring:     [per-request / per-batch / total]
Audit logs:          [yes — what captured]
Retrain cadence:     [estimate]
─────────────────────────────────────────────
```

⏸ HITL GATE — get approval before S10.

---

### S10 — Risk + Ethics

**Goal:** Surface failure modes before they surface in production.

Required questions:
- **Hallucination surface:** (for generative) what can the model confidently get wrong?
- **Bias audit:** does accuracy differ across protected groups, segments, or tenants?
- **Cost ceiling:** what's the maximum acceptable inference cost / training budget?
- **Latency SLO:** what's the maximum acceptable p99 latency?
- **Privacy:** PII in training data? Can the model leak it? Training data exposure?
- **Compliance:** GDPR (right to erasure), SOC2, HIPAA (if PHI), CCPA?
- **Failure taxonomy:** list the top 5 ways this system can fail in production

**Output: Risk Card**
```
Risk Card
─────────────────────────────────────────────
Hallucination risk:  [low / medium / high — mitigation]
Bias audit:          [required / done — tool]
Cost ceiling:        [$/request or $/month]
Latency SLO:         [p99 — ms or s]
Privacy:             [PII present — handling]
Compliance:          [GDPR / HIPAA / SOC2 / none]
Failure modes:
  1. [mode — likelihood — mitigation]
  2. [mode — likelihood — mitigation]
  3. [mode — likelihood — mitigation]
─────────────────────────────────────────────
```

⏸ FINAL HITL GATE — review all cards before generating ML Plan.

---

## HITL Gate Contract

Every gate uses this format — no exceptions:

```
⏸ APPROVAL NEEDED: [what will be locked]
   Recommending: [one sentence]
   Why: [one sentence]
   Risk if wrong: [one sentence]
   → Say "go", "modify", or "skip"
```

**"skip" is never actually allowed for S0–S3 and S10.** For S4–S9, a skip is logged
in the ML Plan with the reason. The plan is the audit trail.

---

## Skill Coordination

| Stage | Lead | Support |
|---|---|---|
| S0–S3 | ml-specialist | — |
| S4–S5 | aiml-specialist | ml-specialist |
| S6–S7 | ml-specialist | aiml-specialist |
| S8–S9 | ml-ops-specialist | ml-specialist |
| S10 | ml-specialist | both |

See `HANDOFF.md` for coordination protocol.
