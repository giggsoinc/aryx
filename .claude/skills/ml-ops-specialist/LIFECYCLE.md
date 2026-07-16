# ML Lifecycle — S9 Deep Dive

Version: 1.0 · Used by: ml-ops-specialist at S9
A model without monitoring is a liability. This stage makes monitoring non-negotiable.

---

## The Four Drift Types

Understanding drift is the foundation of lifecycle management. Each type requires
a different detection approach.

### 1. Data Drift (Covariate Shift)

**What:** The distribution of input features changes after deployment.
**Example:** Model trained on summer traffic patterns, deployed in winter — feature distributions shift.
**Detection:** Statistical tests on input feature distributions vs training baseline.

Tools:
- **Evidently AI** — open source, rich drift reports, integrates with any pipeline
- **Nannyml** — confidence-based drift, works without ground truth labels
- **Alibi Detect** — statistical tests (KS, MMD, LSDD)
- **WhyLogs** — lightweight, streaming-friendly, integrates with MLflow

**Threshold guidance:** Flag at p-value < 0.05 on KS test; alert at < 0.01.

---

### 2. Label Drift (Prior Probability Shift)

**What:** The distribution of target labels changes.
**Example:** Fraud model trained when 1% fraud rate, deployed when 3% fraud rate — precision/recall breakdown.
**Detection:** Monitor predicted class distribution vs training distribution.

**Threshold guidance:** Alert if predicted positive rate deviates > 20% from training baseline.

---

### 3. Concept Drift (Posterior Shift)

**What:** The relationship between features and labels changes.
**Example:** "Virus" used to mean biological — now mostly refers to computer virus.
**Detection:** Requires ground truth labels from production (delayed feedback).

**Approach:** Collect samples + delayed labels → compute metric on rolling window → compare to holdout metric.

---

### 4. Model Performance Degradation (Regression Alarm)

**What:** Model accuracy / primary metric drops below an acceptable floor.
**Detection:** Continuous monitoring of primary metric on labeled production samples.

**Threshold guidance:**
- Set floor at (holdout_metric - 0.05) — alert if metric drops below this
- Hard block deploy if metric drops below (holdout_metric - 0.10)

---

## Retraining Triggers

Use the first of these to fire:

| Trigger | When to use | Recommendation |
|---|---|---|
| **N corrections accumulated** | Human-in-loop pipeline (labelers correct model output) | Retrain at N = 500–1000 corrections |
| **Time elapsed** | Periodic cadence regardless of drift | Retrain monthly (high-change domain) or quarterly (stable domain) |
| **Drift score exceeded** | Automated drift detection | Retrain when KS p-value < 0.01 on ≥ 3 features |
| **Performance floor breached** | Metric regression alarm | Retrain immediately when metric < floor |
| **Manual trigger** | New data source, label schema change | Ad hoc |

**Recommended:** All four triggers active simultaneously. First to fire wins.

---

## Rollback Strategies

### Blue-Green

**What:** Two identical environments — one live (blue), one staging (green). Swap on deploy.
**When:** Predictable cutover, rollback in < 5 minutes.
**Rollback:** Switch DNS / load balancer back to blue. Instant.

### Canary

**What:** Route X% of traffic to new model, rest to current model. Gradually increase %.
**When:** Want to validate in production before full cutover.
**Schedule:** 1% → 5% → 25% → 50% → 100% with metric gate at each step.
**Rollback:** Route 100% back to current model. Set canary % to 0.

### Shadow Mode

**What:** New model receives same traffic but responses not returned to users.
Compare outputs and metrics offline.
**When:** High-stakes systems where even 1% bad output is unacceptable.
**Rollback:** Not needed — shadow model never serves real users.

**Recommended order:** Shadow → Canary → Blue-Green for production ML.

---

## Audit Log Specification

Every model call in production must log:

```json
{
  "timestamp": "ISO-8601",
  "request_id": "UUID",
  "model_name": "string",
  "model_version": "semantic version",
  "caller_id": "service/user identifier",
  "input_hash": "SHA-256 of input (not raw input — privacy)",
  "output_hash": "SHA-256 of output",
  "latency_ms": "integer",
  "confidence": "float (if available)",
  "drift_score": "float (if computed)",
  "cost_usd": "float (if LLM API)"
}
```

**Why hashes not raw:** PII protection. Raw inputs stored separately under access control if needed.

**Retention:** Minimum 90 days. 1 year for regulated industries.

---

## Cost Monitoring

| Deployment path | What to monitor | Alert threshold |
|---|---|---|
| LLM API | Tokens per request, cost per request, daily total | > 2x baseline cost per request |
| Batch job | Runtime per row, total cost per run | > 1.5x baseline runtime |
| GPU serving | GPU utilization, memory, cost per hour | GPU util < 30% (waste) or > 95% (bottleneck) |
| Headless API | Requests per second, cost per 1000 requests | > 1.5x baseline cost/1k req |

---

## Model Registry Best Practices

| Field | Required | Notes |
|---|---|---|
| Model name | ✅ | Consistent slug, no version in name |
| Version | ✅ | Semantic versioning (major.minor.patch) |
| Training run ID | ✅ | Links to experiment tracker |
| Dataset version | ✅ | Hash or version of training data |
| Primary metric (holdout) | ✅ | What was measured, what value |
| Training date | ✅ | ISO-8601 |
| Owner | ✅ | Team or person |
| Status | ✅ | staging / canary / production / deprecated |
| Deprecation date | When applicable | When to retire |

**Tools:** MLflow (open source, full-featured) · W&B (best UX) · DVC (Git-based) · SageMaker Model Registry (AWS)

---

## Lifecycle Checklist (ship only when all pass)

- [ ] Drift detection configured and tested
- [ ] Regression alarm threshold set and tested
- [ ] At least one retraining trigger active
- [ ] Rollback strategy documented and tested
- [ ] Audit logging live and verified
- [ ] Cost monitoring in place with alert threshold
- [ ] Model registered with all required fields
- [ ] On-call rotation knows the rollback procedure
