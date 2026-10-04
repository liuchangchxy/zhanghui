"""Patch 4: Pacing 3-tier tracker.

Source: 移植自 novel-creator-skill/scripts/pacing_tracker.py
Path in references: references/01-ai-webnovel-repos/upstream/02-skills/novel-creator-skill/scripts/pacing_tracker.py
"""
from ..core.patch_base import Patch, CheckContext, ApplyContext, Blocker


class P4PacingTracker(Patch):
    name = "pacing_tracker"
    description = "节奏 3 档追踪：连续快档上限 + 慢档配额"
    depends_on = ()

    def check(self, ctx: CheckContext) -> list[Blocker]:
        if "_load_error" in ctx.state:
            return [Blocker(patch=self.name, chapter=ctx.chapter_num,
                            message=f"无法读取 state.json: {ctx.state['_load_error']}",
                            fix_hint="修复 state.json 后重试")]

        ph = ctx.state.get("story_craft", {}).get("pacing_history")
        if ph is None:
            return [Blocker(patch=self.name, chapter=ctx.chapter_num, message="pacing_history 未初始化", fix_hint="运行 consistency init")]

        history = ph.get("history", [])
        if not isinstance(history, list):
            return [Blocker(patch=self.name, chapter=ctx.chapter_num,
                            message=f"pacing_history.history 必须是 list，实际类型：{type(history).__name__}",
                            fix_hint="运行 consistency init 重建")]
        rules = ph.get("rules", {"max_consecutive_fast": 1, "slow_per_4_chapters_min": 1})

        blockers = []

        # 1. 连续快档上限
        consecutive_fast = 0
        for entry in reversed(history):
            if entry.get("tier") == "fast":
                consecutive_fast += 1
            else:
                break
        if consecutive_fast > rules.get("max_consecutive_fast", 1):
            blockers.append(Blocker(
                patch=self.name,
                chapter=ctx.chapter_num,
                message=f"已连续 {consecutive_fast} 章快档（上限 {rules['max_consecutive_fast']}）",
                fix_hint="本章建议选 medium 或 slow"
            ))

        # 2. 每 4 章至少 1 慢档
        recent_4 = history[-4:]
        slow_count = sum(1 for e in recent_4 if e.get("tier") == "slow")
        if len(recent_4) == 4 and slow_count < rules.get("slow_per_4_chapters_min", 1):
            blockers.append(Blocker(
                patch=self.name,
                chapter=ctx.chapter_num,
                message=f"最近 4 章只有 {slow_count} 章慢档（要求至少 {rules['slow_per_4_chapters_min']}）",
                fix_hint="本章或下一章选 slow"
            ))

        return blockers

    def apply(self, ctx: ApplyContext) -> None:
        ph = ctx.state.setdefault("story_craft", {}).setdefault("pacing_history", {"version": 1, "history": [], "rules": {"max_consecutive_fast": 1, "slow_per_4_chapters_min": 1}})
        ph.setdefault("history", [])
