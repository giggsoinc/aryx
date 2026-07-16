---
name: raven-dashboard
description: Open the Raven local HTML dashboard showing session cost, tokens, PRs, commits, and recommendations for the current project. Runs dashboard.py --html --open to rebuild and launch in browser.
metadata:
  phase: Observe
  trigger: Developer wants to view local activity dashboard
  primary_actor: Developer
---

# raven-dashboard

## Purpose
Open the Raven local activity dashboard in your browser. Shows real session cost, token usage, PR count, commits, guard violations, and recommendations — rebuilt fresh every time.

## When to use
- You want to see your current session cost and token usage
- You want to check PR and commit activity for this project
- You want to see guard violations or policy recommendations
- After finishing a work session to review what was done

## What it does
Runs `dashboard.py --html --open --current-project` which:
1. Reads `.raven/` project data and `~/RavenVault/.metrics/` aggregated history
2. Filters to the current project via `.raven/manifest.json`
3. Rebuilds `~/RavenVault/dashboard.html` with the latest data
4. Opens it in your default browser (cross-platform: Windows, macOS, Linux)

## Usage
```
/raven-dashboard
```

## Instructions for Claude
When this skill is invoked, run the following command immediately — do not ask for confirmation:

```bash
python3 "$HOME/.claude/scripts/dashboard.py" --html --open --current-project
```

> **Windows note**: Use `python` instead of `python3` if `python3` is not on PATH.
> Claude Code on Windows runs hooks via Git Bash, so `$HOME` resolves correctly.

After running, tell the user the dashboard has been opened in their browser and the file is at `~/RavenVault/dashboard.html`.
