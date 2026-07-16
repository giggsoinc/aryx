# ML Deployment — 7-Path Deep Dive

Version: 1.0 · Used by: ml-ops-specialist at S8

---

## The 7 Deployment Paths

### Path 1 — Headless API (FastAPI / FastMCP)

**When to use:**
- Synchronous request/response pattern
- Response time < 2 seconds acceptable
- Caller is a service, app, or agent (not a human waiting)

**Stack:** FastAPI + Uvicorn + model loaded in-process or via subprocess
**FastMCP variant:** Expose model as an MCP tool — best for agent integration

**Infra:**
- 1–4 CPUs for small models; GPU if inference-heavy
- Auto-scaling via K8s HPA or AWS ALB + ECS

**Latency profile:** p50: 50–200ms · p95: 200–800ms · p99: < 2s

**What breaks:**
- Cold start on serverless (Lambda, Cloud Run) — keep warm instances or use provisioned concurrency
- Memory leaks in long-running processes — set max request counts, restart policy
- Model loading on every request — load once at startup, not per-request

**Gotcha:** Do NOT load the model inside the request handler. Load once at app startup.

---

### Path 2 — Batch Job (cron, Prefect, Airflow)

**When to use:**
- Latency insensitive (minutes to hours acceptable)
- High throughput needed (millions of rows)
- Scheduled processing (daily reports, nightly scoring)

**Stack:** Prefect / Airflow / cron + pandas/polars + model artifact

**Infra:**
- CPU-optimized for tabular; GPU for embeddings/generation
- Spot instances acceptable (checkpointing required)
- Object storage (S3/GCS) for input/output

**Latency profile:** Not applicable — measure throughput (rows/second)

**What breaks:**
- No checkpointing — a 4-hour job restarts from zero on failure
- Schema drift in input data — add data validation gate before model call
- Memory: processing 10M rows at once — use chunked processing

**Gotcha:** Always checkpoint. Always validate input schema. Always write output to staging before overwriting production.

---

### Path 3 — Streaming Worker (Kafka consumer, queue)

**When to use:**
- Near-real-time scoring (< 10 seconds)
- Event-driven architecture (new event → score it)
- High volume, continuous flow

**Stack:** Kafka + Python consumer + model in-process
**Alternatives:** RabbitMQ, AWS SQS + Lambda, GCP Pub/Sub + Cloud Function

**Infra:**
- Stateless workers, horizontally scalable
- GPU optional — quantize model for CPU if latency budget allows
- Dead-letter queue for failed events

**Latency profile:** p50: 100–500ms · p95: 1–3s · p99: < 10s (dependent on queue lag)

**What breaks:**
- Consumer lag — workers can't keep up with producers; scale horizontally
- Poison pill messages — events that crash the consumer; always use dead-letter queue
- Model reloading on worker restart — use persistent model server + thin consumer

**Gotcha:** Separate model serving from message consumption. Consumer should call a model server, not load the model itself — otherwise every scaling event reloads the model.

---

### Path 4 — Edge / On-Device (CoreML, ONNX, TFLite)

**When to use:**
- Privacy requirement (data must not leave device)
- Offline capability needed
- Ultra-low latency (< 50ms)
- Mobile, embedded, IoT

**Stack:** Export model → ONNX / CoreML / TFLite → deploy to device

**Export path:**
- PyTorch → ONNX → TFLite (cross-platform)
- PyTorch → CoreML (Apple devices)
- TF → TFLite (Android, microcontrollers)

**Constraints:**
- Max model size: 10–50MB for mobile (use quantization — INT8 minimum)
- No GPU assumption — CPU inference only (except Apple ANE / Qualcomm NPU)
- Update path: OTA model updates (not app store submissions)

**What breaks:**
- Quantization accuracy loss — always measure on holdout before shipping
- Different hardware → different numerical behavior → test on target device
- Model update latency — edge devices don't update instantly; version your API contract

**Gotcha:** Test quantized model accuracy on your specific dataset before committing to edge deployment. INT4 can drop 5–15% on non-LLM tasks.

---

### Path 5 — Agentic Loop (LangGraph / OpenAI Agents / custom MCP)

**When to use:**
- Multi-step reasoning required
- Model needs to call tools, search, or iterate
- Output quality depends on intermediate steps

**Stack:** LangGraph / OpenAI Agents SDK / custom agent + MCP tools

**Pattern:**
```
User request → Agent → [tool calls] → [model calls] → [verification] → output
```

**Infra:**
- Stateful session management (Redis or DB for agent state)
- Tool registry (MCP server or function registry)
- Timeout + max-turn limits (prevent infinite loops)

**Latency profile:** p50: 2–10s · p95: 10–30s · p99: < 60s — NOT for synchronous UX

**What breaks:**
- Infinite loops — always set max_turns and timeout
- Tool failures causing agent to hallucinate — handle tool errors explicitly, don't let agent infer
- State explosion in long sessions — cap context, summarize history

**Gotcha:** Agentic is NOT a substitute for a well-designed ML pipeline. Use it for tasks that genuinely require multi-step reasoning, not as a shortcut to avoid building proper features.

---

### Path 6 — Cluster (K8s + KServe / Ray Serve / Triton)

**When to use:**
- High throughput at scale (> 1000 req/s)
- Large models requiring GPU (> 7B parameters)
- Multi-model serving with shared GPU memory
- SLA requirements with auto-scaling

**Stack options:**
- **KServe:** K8s-native, ONNX/TF/PyTorch, autoscaling, good for standard models
- **Ray Serve:** Python-native, easy multi-model routing, good for custom pipelines
- **Triton Inference Server:** NVIDIA-optimized, highest throughput for GPU, production standard

**Infra:**
- GPU node pools (A100/H100 for LLMs; T4/A10G for smaller)
- Kubernetes with GPU operator
- Model storage: S3/GCS with model registry

**Latency profile:** p50: 20–100ms · p95: 100–300ms · p99: < 1s (with proper batching)

**What breaks:**
- GPU OOM — batch size tuning is critical; use dynamic batching
- Model loading time — pre-load all models at cluster start; use model warm pool
- Network bottleneck — keep model server and client in same region / AZ

**Gotcha:** Triton is the right answer for production GPU serving at scale. KServe is easier to start with. Don't run Ray Serve on CPU-only nodes for large models.

---

### Path 7 — Embedded in App (In-Process)

**When to use:**
- Ultra-simple deployment (no infra overhead)
- Model is small (< 100MB)
- Single-process app (CLI tool, desktop app, lambda)
- Development / prototyping

**Stack:** scikit-learn / LightGBM / ONNX Runtime loaded directly in app process

**Infra:** None beyond app runtime. Model file shipped with app binary or loaded from S3 on startup.

**Latency profile:** p50: 1–20ms (no network overhead)

**What breaks:**
- Memory: large model + large request payload in same process → OOM
- Scaling: horizontal scaling means N copies of model in memory → expensive
- Updates: model update requires app redeploy → use remote config + hot-reload instead

**Gotcha:** Correct for small models and simple use cases. Wrong for anything requiring GPU, large models, or independent scaling of model vs app.

---

## Decision Matrix

| Signal | → Path |
|---|---|
| Synchronous request/response, latency < 2s | **1 — Headless API** |
| High throughput, latency insensitive, scheduled | **2 — Batch Job** |
| Event-driven, near-real-time | **3 — Streaming Worker** |
| Privacy / offline / mobile | **4 — Edge** |
| Multi-step reasoning, tool use | **5 — Agentic** |
| Scale > 1000 req/s OR large GPU models | **6 — Cluster** |
| Simple, small model, single process | **7 — Embedded** |

When uncertain: start with **Path 1 (Headless API)** and migrate to Path 6 when scale demands it.
