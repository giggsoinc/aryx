# Using Raven with Aryx

Aryx ships a **Claude Code** Raven setup: `.claude/` (hooks, skills, agents) plus `.raven/manifest.json` (stack declaration). You do **not** need to clone or vendor the Raven product repo.

1. Install [Claude Code](https://docs.anthropic.com/en/docs/claude-code) and open this repository as the project root.
2. Use the committed manifest — Raven will not run correctly without `.raven/manifest.json` (and `CLAUDE.md` session boot).
3. Confirm hooks load from `.claude/settings.json` → `.claude/scripts/`.
4. Smoke-check: in Claude Code run `/raven-debug`.
5. Optional slash commands: `/raven-sync`, `/raven-scaffold`, `/raven-review`, `/raven-security`.
6. Only if the manifest was deleted: run `/raven-init` to recreate it (prefer restoring from git).
7. Do **not** commit secrets: `.env`, `.raven/manifest.secrets.json`, `.raven/.model-session.json`, `.raven/state/`.

Product docs and engine releases: [giggsoinc/raven](https://github.com/giggsoinc/raven) — reference only, not a second copy inside Aryx.
