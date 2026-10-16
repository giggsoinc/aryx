#!/usr/bin/env bash
# raven-core/install-asset-inventory-hooks.sh
#
# Installs Raven asset inventory hooks:
#   pre-commit  — validate project link when API files are staged
#   post-commit — scan repo and ingest inventory into Asset Identification DB
#
# Usage:
#   bash raven-core/install-asset-inventory-hooks.sh [--dry-run] [--uninstall]

set -e
DRY_RUN=false
UNINSTALL=false
for arg in "$@"; do
  [[ "$arg" == "--dry-run" ]] && DRY_RUN=true
  [[ "$arg" == "--uninstall" ]] && UNINSTALL=true
done

if ! REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null)"; then
  echo "❌ $(pwd) is not a git repository"
  exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
CORE_DIR="$REPO_ROOT/raven-core"
GLOBAL_SCRIPTS="${HOME}/.claude/scripts"
HOOKS_DIR="$REPO_ROOT/.git/hooks"
PRE_COMMIT="$HOOKS_DIR/pre-commit"
POST_COMMIT="$HOOKS_DIR/post-commit"
PRE_MARKER="# raven-asset-inventory-pre-commit"
POST_MARKER="# raven-asset-inventory-post-commit"

_resolve_inventory_dir() {
  if [[ -f "$CORE_DIR/asset-inventory-commit.py" ]]; then
    echo "$CORE_DIR"
    return
  fi
  if [[ -f "$SCRIPT_DIR/asset-inventory-commit.py" ]]; then
    echo "$SCRIPT_DIR"
    return
  fi
  if [[ -f "$GLOBAL_SCRIPTS/asset-inventory-commit.py" ]]; then
    echo "$GLOBAL_SCRIPTS"
    return
  fi
  return 1
}

INVENTORY_DIR="$(_resolve_inventory_dir)" || {
  echo "❌ missing asset-inventory-commit.py (install Raven agent scripts first)"
  exit 1
}

mkdir -p "$CORE_DIR"
for dep in asset-inventory-commit.py project_link_common.py project_resolve.py \
           skill_route_scanner.py skill_scan_common.py skill_asset_inventory.py \
           raven-skill-asset-inventory.py skill-scanner-requirements.txt; do
  if [[ ! -f "$CORE_DIR/$dep" && -f "$INVENTORY_DIR/$dep" ]]; then
    cp "$INVENTORY_DIR/$dep" "$CORE_DIR/$dep"
  fi
done
INVENTORY_DIR="$(_resolve_inventory_dir)"

if [[ "$UNINSTALL" == "true" ]]; then
  for HOOK in "$PRE_COMMIT" "$POST_COMMIT"; do
    if [[ -f "$HOOK" ]] && grep -qF "$PRE_MARKER" "$HOOK" 2>/dev/null; then
      [[ "$DRY_RUN" == "false" ]] && sed -i.bak "/$PRE_MARKER/,/^$/d" "$HOOK" 2>/dev/null || true
      echo "✅ removed asset inventory block from $(basename "$HOOK")"
    fi
    if [[ -f "$HOOK" ]] && grep -qF "$POST_MARKER" "$HOOK" 2>/dev/null; then
      [[ "$DRY_RUN" == "false" ]] && sed -i.bak "/$POST_MARKER/,/^$/d" "$HOOK" 2>/dev/null || true
      echo "✅ removed asset inventory block from $(basename "$HOOK")"
    fi
  done
  exit 0
fi

PRE_BLOCK=$(cat <<EOF

$PRE_MARKER
REPO_ROOT="\$(git rev-parse --show-toplevel)"
if [[ -f "\$REPO_ROOT/raven-core/asset-inventory-commit.py" ]]; then
  INV_DIR="\$(cd "\$REPO_ROOT/raven-core" && pwd)"
elif [[ -f "\$HOME/.claude/scripts/asset-inventory-commit.py" ]]; then
  INV_DIR="\$(cd "\$HOME/.claude/scripts" && pwd)"
else
  echo "raven-asset-inventory: missing asset-inventory-commit.py" >&2
  exit 1
fi
python3 "\$INV_DIR/asset-inventory-commit.py" --phase pre-commit || exit 1
EOF
)

POST_BLOCK=$(cat <<EOF
#!/usr/bin/env bash
$POST_MARKER
REPO_ROOT="\$(git rev-parse --show-toplevel)"
if [[ -f "\$REPO_ROOT/raven-core/asset-inventory-commit.py" ]]; then
  INV_DIR="\$(cd "\$REPO_ROOT/raven-core" && pwd)"
elif [[ -f "\$HOME/.claude/scripts/asset-inventory-commit.py" ]]; then
  INV_DIR="\$(cd "\$HOME/.claude/scripts" && pwd)"
else
  echo "raven-asset-inventory: missing asset-inventory-commit.py" >&2
  exit 0
fi
python3 "\$INV_DIR/asset-inventory-commit.py" --phase post-commit || true
EOF
)

append_block() {
  local hook_path="$1"
  local marker="$2"
  local block="$3"
  if [[ -f "$hook_path" ]] && grep -qF "$marker" "$hook_path"; then
    echo "  ℹ️  $(basename "$hook_path") already has asset inventory hook"
    return
  fi
  if [[ "$DRY_RUN" == "true" ]]; then
    echo "  would append asset inventory hook to $(basename "$hook_path")"
    return
  fi
  if [[ ! -f "$hook_path" ]]; then
    printf '%s\n' "#!/usr/bin/env bash" "$block" > "$hook_path"
    chmod +x "$hook_path"
  else
    printf '\n%s\n' "$block" >> "$hook_path"
  fi
  chmod +x "$hook_path"
  echo "  ✅ updated $(basename "$hook_path")"
}

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  Raven — Asset Inventory Hook Installer"
[[ "$DRY_RUN" == "true" ]] && echo "  DRY RUN — no files written"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

append_block "$PRE_COMMIT" "$PRE_MARKER" "$PRE_BLOCK"
append_block "$POST_COMMIT" "$POST_MARKER" "$POST_BLOCK"

echo ""
echo "Scanner: Raven skill scanner (skill_route_scanner.py) — no git_scanner clone required."
echo "Optional: set RAVEN_SCANNER_ROOT to override with an external git_scanner checkout."
echo "Link this folder first: python raven-core/raven-project-link.py"
echo "Manual scan+ingest: python raven-core/skill_asset_inventory.py run"
echo ""
