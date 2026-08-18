#!/usr/bin/env bash
# Sync runtime files from this source plugin to the marketplace install.
# Claude Code loads skills from the marketplace copy, not from this source.
# Without this script, changes made here are invisible to AI in novel-writing dirs.
#
# Usage:
#   bin/deploy-plugin.sh                 # sync with defaults
#   bin/deploy-plugin.sh --dry-run       # show what would be synced
#   bin/deploy-plugin.sh --skip-tests    # skip test file sync
#
# Idempotent — safe to run multiple times.
# Run this after any merge into main.

set -euo pipefail

# Resolve source (this script's repo) and marketplace (where Claude Code loads from)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# Script lives at <plugin_root>/bin/deploy-plugin.sh, so plugin root is one level up
PLUGIN_SRC="$(cd "${SCRIPT_DIR}/.." && pwd)"

# Marketplace default location; override via MARKETPLACE_ROOT env var
DEFAULT_MARKETPLACE="${HOME}/.claude/plugins/marketplaces/webnovel-chang-marketplace/webnovel-writer_chang"
MARKETPLACE_ROOT="${MARKETPLACE_ROOT:-${DEFAULT_MARKETPLACE}}"

DRY_RUN=0
SKIP_TESTS=0

for arg in "$@"; do
    case "$arg" in
        --dry-run) DRY_RUN=1 ;;
        --skip-tests) SKIP_TESTS=1 ;;
        -h|--help)
            sed -n '2,12p' "$0"
            exit 0
            ;;
        *)
            echo "Unknown arg: $arg" >&2
            exit 1
            ;;
    esac
done

if [ ! -d "$MARKETPLACE_ROOT" ]; then
    echo "ERROR: marketplace plugin not found at $MARKETPLACE_ROOT" >&2
    echo "Set MARKETPLACE_ROOT or pass a custom path." >&2
    exit 1
fi

# Files to sync (relative to PLUGIN_SRC)
# Tests are excluded by default — they live in source only.
RUNTIME_FILES=(
    "scripts/data_modules/volume_state.py"
    "scripts/data_modules/ai_volume_drafter.py"
    "scripts/data_modules/promise_ledger.py"     # NEW
    "scripts/data_modules/chunked_write.py"      # NEW
    "scripts/init_project.py"
    "scripts/story_craft.py"
    "scripts/update_master_outline.py"
    "scripts/review_pipeline.py"          # NEW
    "dashboard/app.py"                    # NEW
    "skills/webnovel-init/SKILL.md"
    "skills/webnovel-init/references/multi-volume-ux.md"
    "skills/webnovel-plan/SKILL.md"
    "skills/webnovel-write/SKILL.md"             # NEW
    "templates/output/大纲-总纲.md"
    "README.md"
    "bin/deploy-plugin.sh"
)

# Test files to sync if --skip-tests is NOT set (e.g., if user wants e2e tests in marketplace)
TEST_FILES=(
    "scripts/tests/unit/test_volume_state.py"
    "scripts/tests/unit/test_ai_volume_drafter.py"
    "scripts/tests/unit/test_promise_ledger.py"           # NEW
    "scripts/tests/unit/test_chunked_write.py"            # NEW
    "scripts/tests/unit/test_story_craft_multivolume.py"  # NEW
    "scripts/tests/integration/test_init_multi_volume.py"
    "scripts/tests/integration/test_plan_v_plus_one_anchor.py"
    "scripts/tests/integration/test_plan_all_volumes.py"  # NEW
    "scripts/tests/integration/test_e2e_macro_micro.py"   # NEW
    "scripts/tests/integration/test_e2e_multi_volume_init.py"
    "scripts/tests/integration/test_update_master_outline_volumes.py"
)

echo "Source plugin:      $PLUGIN_SRC"
echo "Marketplace plugin: $MARKETPLACE_ROOT"
echo ""

synced=0
skipped=0
missing=0

sync_file() {
    local rel="$1"
    local src="${PLUGIN_SRC}/${rel}"
    local dst="${MARKETPLACE_ROOT}/${rel}"

    if [ ! -f "$src" ]; then
        echo "  WARN: $rel missing in source, skipping"
        missing=$((missing + 1))
        return
    fi

    if [ "$DRY_RUN" -eq 1 ]; then
        echo "  DRY: would copy $rel"
    else
        mkdir -p "$(dirname "$dst")"
        cp "$src" "$dst"
        echo "  ✓ $rel"
    fi
    synced=$((synced + 1))
}

echo "Runtime files:"
for f in "${RUNTIME_FILES[@]}"; do
    sync_file "$f"
done

if [ "$SKIP_TESTS" -eq 0 ]; then
    echo ""
    echo "Test files:"
    for f in "${TEST_FILES[@]}"; do
        sync_file "$f"
    done
else
    echo ""
    echo "Test files: skipped (--skip-tests)"
fi

echo ""
echo "Summary: $synced synced, $missing missing"

# Also bump version if needed
if [ "$DRY_RUN" -eq 0 ]; then
    if [ -f "${PLUGIN_SRC}/scripts/sync_plugin_version.py" ]; then
        echo ""
        echo "Running sync_plugin_version.py for version sync..."
        python3 "${PLUGIN_SRC}/scripts/sync_plugin_version.py" || \
            echo "  WARN: version sync skipped (script returned non-zero)"
    fi
fi

if [ "$DRY_RUN" -eq 0 ]; then
    echo ""
    echo "Done. Restart Claude Code sessions to pick up changes."
fi