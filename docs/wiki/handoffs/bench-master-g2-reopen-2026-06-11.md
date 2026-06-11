---
agent: bench-master
gap: G2 (reopen request)
date: 2026-06-11
status: FINDING
severity: P3
---

## Finding — Blocking Recall Below Acceptance Gate

The G9 spec sets the gate at blocking recall ≥ 0.95 on Febrl. Measured with
the new MultiKeyBlocker:

| Dataset | Blocking recall | Gate | Verdict |
|---|---|---|---|
| Febrl1 | 0.8520 | ≥ 0.95 | **FAIL** |
| mfg-500 | 0.8560 | ≥ 0.95 | **FAIL** |
| mfg-10k | 0.8424 | ≥ 0.95 | **FAIL** |

~14.5% of true match pairs never share any block and are unrecoverable
downstream — the scorer and adjudicator never see them.

For context: the multi-key blocker is still a large win over legacy
(0.852 vs 0.728 on Febrl1), so this is a reopen for improvement, not a
regression.

## Root-Cause Candidates (in suspected order)

1. **Sparse text** — Febrl records with NaN given_name/surname produce short
   normalized text; prefix and Soundex keys degenerate.
2. **Token-set truncation** — `"tokens:" + "|".join(sorted(set(tokens)))[:32]`
   truncates at 32 chars; long multi-token names lose distinguishing tokens,
   and two variants of the same name can truncate differently.
3. **Single-token Soundex** — only the FIRST token is Soundex-encoded; a typo
   in the first token (e.g. "lachlan" → "lachaln") changes the code while the
   prefix key also breaks, leaving only the token-set key, which the same typo
   also breaks.

## Suggested Experiments

- Soundex on every token, not just the first (cost: more keys per record).
- N-gram (bigram/trigram) keys on the normalized text.
- Remove the 32-char truncation; hash the full token set instead.
- Sorted-neighborhood pass as a fourth key family.

## How to Reproduce

```
PYTHONPATH=src python -m benchmarks.run_bench --dataset febrl1
# blocking_recall printed in the metrics line
```

This does NOT block the G9 → G10 chain. G10 should note its recall ceiling
is 0.852 until this lands.
