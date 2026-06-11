# Program State — updated by Conductor only
| Gap | Agent | Status | Branch | Blocked-by | Last-commit | Bench-P/R |
|-----|-------|--------|--------|------------|-------------|-----------|
| G4  | auth-warden     | DONE | gap/g4-auth   | —         | 6060af8 | n/a |
| G2  | block-smith     | DONE | gap/g2-block  | —         | 6cb7799 | n/a |
| G3  | survivor-smith  | DONE | gap/g3-golden | —         | 1ba642c | n/a |
| G12 | pool-fitter     | DONE | gap/g12-pool  | —         | 3655ad5 | n/a |
| G9  | bench-master    | DONE        | gap/g9-bench  | —         | a4932e3 | febrl1 P=1.00 R=0.59 |
| G10 | adjudicator     | READY       | —             | —         | —       | —   |
| G1+G5 | stream-scaler | BLOCKED   | —             | G2        | —       | n/a |
| G7  | confidence-smith| BLOCKED     | —             | G2        | —       | —   |
| G8  | projector       | BLOCKED     | —             | G1+G5     | —       | —   |
| G13 | action-architect| BLOCKED     | —             | G10       | —       | n/a |
Statuses: READY | IN_PROGRESS | REVIEW | DONE | BLOCKED | FAILED
