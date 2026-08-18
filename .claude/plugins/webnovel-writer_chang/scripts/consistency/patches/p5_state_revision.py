"""Patch 5: expected_state_revision — prevent stale commits.

Source: 借鉴 oh-story-claudecode/skills/story-import/references/state-tracking.md 的 state_revision 防 stale 机制
Path in references: references/01-ai-webnovel-repos/upstream/02-skills/oh-story-claudecode/skills/story-import/references/state-tracking.md
"""
from ..core.patch_base import Patch, CheckContext, ApplyContext, Blocker


class P5StateRevision(Patch):
    name = "state_revision"
    description = "state_revision 防 stale：提交时验证 revision 匹配"
    depends_on = ()

    def check(self, ctx: CheckContext) -> list[Blocker]:
        expected_rev = ctx.state.get("_expected_revision")
        if expected_rev is None:
            return []  # caller 没传 expected = 跳过

        current_rev = ctx.state.get("state", {}).get("_revision", 0)

        if expected_rev != current_rev:
            return [Blocker(
                patch=self.name,
                chapter=ctx.chapter_num,
                message=f"state_revision 不匹配：期望 {expected_rev}，实际 {current_rev}",
                fix_hint="重新读取 state.json 后重试"
            )]
        return []

    def apply(self, ctx: ApplyContext) -> None:
        from datetime import datetime, timezone
        state_meta = ctx.state.setdefault("state", {})
        state_meta["_revision"] = state_meta.get("_revision", 0) + 1
        state_meta["_last_modified_by"] = f"webnovel-write/ch{ctx.chapter_num}"
        # Stamp real wall-clock timestamp here so apply() is no longer a no-op.
        # The runner also stamps this defensively after apply_all, but doing it here
        # ensures the field is correct even when apply() is called individually.
        state_meta["_last_modified_at"] = datetime.now(timezone.utc).isoformat()