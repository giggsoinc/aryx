# Benchmarks

Append-only. Each row is self-describing.

| date | commit | dataset | blocker | adj_mode | P | R | F1 | blocking_recall | candidates | wall_s | auto_merge | adj_from |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 2026-06-11 | 6cb77993 | febrl1 | multi-key | always_reject | 1.0000 | 0.5900 | 0.7421 | 0.8520 | 6528 | 3.06 | 0.92 | 0.90 |
| 2026-06-11 | 6cb77993 | febrl1 | multi-key | always_accept | 1.0000 | 0.6460 | 0.7849 | 0.8520 | 6528 | 6.44 | 0.92 | 0.90 |
| 2026-06-11 | 6cb77993 | febrl1 | legacy-prefix | always_reject | 1.0000 | 0.5140 | 0.6790 | 0.7280 | 2749 | 0.48 | 0.92 | 0.90 |
| 2026-06-11 | 6cb77993 | mfg-500 | multi-key | always_reject | 0.9819 | 0.6520 | 0.7837 | 0.8560 | ~3500 | 3.5 | 0.92 | 0.90 |
| 2026-06-11 | 6cb77993 | mfg-500 | legacy-prefix | always_reject | 0.9808 | 0.6140 | 0.7552 | 0.7440 | ~900 | 0.3 | 0.92 | 0.90 |
| 2026-06-11 | 6cb77993 | mfg-10k | multi-key | always_reject | 0.8380 | 0.6166 | 0.7105 | 0.8424 | 1271094 | 93.27 | 0.92 | 0.90 |
| 2026-06-11 | 6cb77993 | mfg-10k | legacy-prefix | always_reject | 0.8343 | 0.5832 | 0.6865 | 0.7366 | 636363 | 65.87 | 0.92 | 0.90 |
