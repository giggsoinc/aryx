# Raven Damage-Control — Hook Scripts

Defense-in-depth PreToolUse hooks for Claude Code. Three scripts, one config file:

| Script | Matcher | Purpose |
| ------ | ------- | ------- |
| `bash-tool-damage-control.py`  | `Bash`  | Blocks destructive commands (`rm -rf`, `git reset --hard`, `terraform destroy`, ...) |
| `edit-tool-damage-control.py`  | `Edit`  | Blocks edits to protected files (`.env`, `*.pem`, `~/.ssh/`, lockfiles, ...) |
| `write-tool-damage-control.py` | `Write` | Blocks writes to those same protected paths |

All three load `patterns.json` from the script's own directory.

## Runtime

Plain `python3` (≥ 3.8). No third-party dependencies. The scripts ship with stdlib-only logic — `json`, `re`, `os`, `fnmatch`, `pathlib`. PyYAML is auto-detected if a legacy `patterns.yaml` is present (back-compat for v4.3.1 and earlier).

## Config (`patterns.json`)

Four arrays:

- **`bashToolPatterns`** — list of `{ "pattern": "<regex>", "reason": "...", "ask"?: true }`. Matched case-insensitively against the bash command. `ask: true` triggers a confirmation dialog instead of an outright block.
- **`zeroAccessPaths`** — paths/globs that block **all** operations (read, write, edit, delete). Use for secrets and credentials.
- **`readOnlyPaths`** — paths/globs where reads are allowed but every mutating operation is blocked. Use for system dirs, lockfiles, build outputs.
- **`noDeletePaths`** — paths/globs that block deletion only. Use for important docs / config files that you may still need to edit.

Both literal paths (prefix-matched) and glob patterns (`*.pem`, `.env*`) are supported. Tilde (`~`) is expanded.

## Exit codes

| Code | Meaning |
| ---- | ------- |
| 0    | Allow operation |
| 0 + JSON `{hookSpecificOutput: {permissionDecision: "ask"}}` | Show user confirmation dialog |
| 2    | Block operation (message on stderr is shown to Claude) |

## Customizing

Edit `patterns.json`:

```jsonc
{
  "bashToolPatterns": [
    { "pattern": "\\bnpm\\s+publish\\b", "reason": "npm publish (requires approval)", "ask": true }
  ],
  "zeroAccessPaths": [ "secrets/" ]
}
```

After editing, hooks pick up the change on next tool call — no restart needed.

## Local smoke test

```bash
echo '{"tool_name":"Bash","tool_input":{"command":"rm -rf /tmp/foo"}}' \
  | python3 bash-tool-damage-control.py
# stderr: SECURITY: Blocked: rm with recursive or force flags
# exit:   2

echo '{"tool_name":"Write","tool_input":{"file_path":"/home/me/.env"}}' \
  | python3 write-tool-damage-control.py
# stderr: SECURITY: Blocked write to zero-access path .env*
# exit:   2
```
