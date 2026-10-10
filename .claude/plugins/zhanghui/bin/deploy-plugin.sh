# [DEPRECATED] deploy-plugin.sh
# 历史遗留脚本：原先用于将部分 whitelist 文件手工同步到旧全局 Marketplace 副本。
# 由于容易导致“新 Skill + 旧 Runtime”混装，现已废弃。
# 请使用仓库根目录的 canonical 安装/更新路径：
#   bin/install-plugin.sh
#
# 该脚本会自动将 Claude Code 注册到当前 canonical 仓库 (.claude/plugins/zhanghui/)，
# 直接读取完整最新的 Skill 与 Runtime，杜绝任何中间副本与 whitelist 遗漏。

echo "========================================================================" >&2
echo "NOTICE: bin/deploy-plugin.sh is DEPRECATED." >&2
echo "Claude Code now loads Zhanghui directly from the canonical repository." >&2
echo "Please run 'bin/install-plugin.sh' from the repository root instead." >&2
echo "========================================================================" >&2

if [ "${1:-}" != "--force" ]; then
    echo "To run this legacy script anyway, pass --force." >&2
    exit 1
fi
shift

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
    "scripts/_shared/safe_overwrite.py"   # NEW (2026-08-19 safe-rerun)
    "scripts/check_plan_artifacts.py"     # NEW (2026-08-19 SKILL.md landing)
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
    "scripts/tests/test_safe_overwrite.py"               # NEW (2026-08-19)
    "scripts/tests/test_check_plan_artifacts.py"         # NEW (2026-08-19)
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