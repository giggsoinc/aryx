# ML Algorithm Catalog — S4 Reference

Version: 1.0 · Used by: aiml-specialist at S4 (Algorithm Classes)
Always present ≥ 3 candidates from the relevant family. Never recommend just one.

---

## How to Use This Catalog

1. Identify problem type from S1
2. Go to the relevant section
3. Select ≥ 3 candidates that fit the data profile from S2
4. Present tradeoffs across: cost · latency · interpretability · data need · maintenance
5. Recommend one with justification — but always show the others

---

## Classification

| Algorithm | Best when | Data needed | Latency | Interpretable | Maintenance |
|---|---|---|---|---|---|
| **Logistic Regression** | Baseline, linearly separable | Small (< 10k) | Sub-ms | ✅ Yes | Low |
| **Random Forest** | Tabular, mixed features, robust to noise | 1k–100k | Low | Partial (SHAP) | Low |
| **Gradient Boosting (XGBoost, LightGBM, CatBoost)** | Tabular, best accuracy without neural nets | 1k–1M | Low | Partial (SHAP) | Low |
| **SVM** | Small dataset, high-dimensional text | < 100k | Low | Partial | Medium |
| **kNN** | Similarity-based, instance-level explanation | Small (< 50k) | High at inference | ✅ Yes | Low |
| **Neural Network (MLP)** | Complex feature interactions | 10k–1M | Medium | ❌ Black box | Medium |
| **SetFit** | Text classification, few-shot (8–64 examples) | 8–1k labeled | Low (CPU) | ❌ Black box | Low |
| **LLM zero-shot** | No training data, flexible labels | 0 | API latency | ❌ Black box | Low |
| **LLM few-shot** | < 20 examples, complex label definitions | 5–20 | API latency | ❌ Black box | Low |
| **Fine-tuned LLM** | Complex text, nuanced categories, high accuracy | 500–50k | GPU needed | ❌ Black box | High |

**Decision shortcuts:**
- Tabular + accuracy matters → LightGBM first
- Text + labels scarce (< 100) → SetFit or LLM few-shot
- Text + labels abundant (> 1k) → Fine-tuned BERT-class or LightGBM on embeddings
- Need explanation → Random Forest + SHAP

---

## Regression

| Algorithm | Best when | Data needed | Latency | Interpretable | Maintenance |
|---|---|---|---|---|---|
| **Linear Regression** | Baseline, linear relationships | Small | Sub-ms | ✅ Yes | Low |
| **Ridge / Lasso** | Linear + regularization, feature selection | Small | Sub-ms | ✅ Yes | Low |
| **Gradient Boosting (XGBoost, LightGBM)** | Non-linear tabular, best accuracy | 1k–1M | Low | Partial (SHAP) | Low |
| **Neural Network (MLP)** | Complex feature interactions | 10k–1M | Medium | ❌ Black box | Medium |
| **GAM (Generalized Additive Model)** | Interpretable non-linear | 1k–100k | Low | ✅ Yes | Low |
| **Quantile Regression** | Predict intervals, not just point estimates | 1k–100k | Low | Partial | Low |
| **Prophet / NeuralProphet** | Time-series with seasonality | 100+ time points | Low | Partial | Low |
| **LSTM / Transformer** | Complex time-series patterns | 10k+ time points | Medium | ❌ Black box | High |

**Decision shortcuts:**
- Tabular + accuracy → LightGBM first
- Need uncertainty estimates → Quantile Regression
- Time-series with seasonality → Prophet
- Complex time-series → LSTM / TFT

---

## Generation

| Algorithm | Best when | Data needed | Latency | Cost | Quality |
|---|---|---|---|---|---|
| **LLM API (zero-shot)** | Generic tasks, no training data | 0 | 1–5s | $$$/token | Good |
| **LLM API (few-shot / prompt-engineered)** | Specific format, style, or domain | 5–50 examples | 1–5s | $$$/token | Better |
| **RAG** | Factual grounding, evolving knowledge | Document corpus | 2–8s | $$$/token + retrieval | Best for factual |
| **Fine-tuned LLM (LoRA/QLoRA)** | Custom style, domain-specific, cost reduction | 500–50k examples | GPU needed | $$$ training, $ inference | Best for domain |
| **Full fine-tune** | Maximum quality, unique domain | 100k+ examples | Multi-GPU days | $$$$ | Highest |
| **Diffusion (images/audio)** | Image/audio generation | Domain-specific | GPU needed | $$$$ | Best for media |

**Decision shortcuts:**
- No training data → LLM API + prompt engineering first
- Facts change often → RAG
- Cost sensitive + specific domain → Fine-tune (LoRA) on smaller model
- Highest quality + resources available → Full fine-tune

---

## Clustering

| Algorithm | Best when | Data needed | Scalability | Shape assumption |
|---|---|---|---|---|
| **k-Means** | Known number of clusters, spherical clusters | Any | High | Spherical |
| **HDBSCAN** | Unknown number, arbitrary shapes, noise | Medium | Medium | Any |
| **BERTopic** | Text clustering, interpretable topics | Text only | Medium | Topic-based |
| **GMM (Gaussian Mixture)** | Soft cluster assignment, elliptical clusters | Medium | Medium | Elliptical |
| **Agglomerative** | Hierarchical structure, dendrogram visualization | Small (< 10k) | Low | Any |
| **DBSCAN** | Density-based, known eps/min_samples | Medium | Medium | Density-based |

**Decision shortcuts:**
- Know number of clusters → k-Means baseline
- Don't know number → HDBSCAN
- Text + need interpretable topics → BERTopic
- Need hierarchy → Agglomerative

---

## Ranking / Recommendation

| Algorithm | Best when | Data needed | Complexity |
|---|---|---|---|
| **BM25** | Text search, no training data needed | Document corpus | Low |
| **Collaborative Filtering (ALS, SVD)** | User-item interactions, implicit feedback | User-item matrix | Medium |
| **Neural CF / Two-Tower** | Large-scale, cold start mitigation | 1M+ interactions | High |
| **LambdaRank / LightGBM Ranker** | Learning-to-rank with explicit labels | Labeled query-doc pairs | Medium |
| **Embedding similarity (FAISS, pgvector)** | Semantic similarity, cross-modal | Embeddings | Low |
| **Sequential (BERT4Rec, SASRec)** | Session-based, order matters | User sequences | High |

**Decision shortcuts:**
- Text search → BM25 + embedding reranking
- E-commerce recommendations → Two-Tower + ALS fallback
- Cold start problem → Content-based + collaborative hybrid

---

## Tradeoff Summary (quick reference)

| Dimension | Best → Worst |
|---|---|
| **Tabular accuracy** | LightGBM > RF > Linear > kNN |
| **Training speed** | Linear > RF > LightGBM > Neural |
| **Interpretability** | Linear > GAM > RF+SHAP > LightGBM+SHAP > Neural |
| **Data efficiency** | LLM few-shot > SetFit > Transfer > Fine-tune > Full-train |
| **Inference speed** | Linear > Tree > Neural > LLM API |
| **Maintenance burden** | Linear < Tree < Neural < LLM-fine-tune |
