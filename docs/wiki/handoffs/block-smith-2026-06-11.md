agent: block-smith
gap: G2
status: DONE
commit: 134255f
files_touched:
  - src/aryx/resolution/blocking.py
  - src/aryx/resolution/classical.py
  - tests/test_blocking.py
  - docs/wiki/gaps/G2.md
acceptance:
  tests: 13/13 pass
unblocks: [G9, G10, G7, G1+G5]
decisions_appended: []
warnings:
  - "block-size cap default=5000 -- tune after G9 measures real skew on production data"
  - "Soundex table in original spec had a typo (27-char right string vs 26-char left);
     corrected to standard ABCDEFGHIJKLMNOPQRSTUVWXYZ / 01230120022455012623010202"
  - "normalize() moved from classical.py to blocking.py to break circular import;
     classical.py re-exports it for backward compatibility via __all__"
next_agent_must_read:
  - docs/wiki/gaps/G2.md
