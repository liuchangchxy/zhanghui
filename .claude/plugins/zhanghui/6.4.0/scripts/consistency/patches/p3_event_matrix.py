"""Patch 3: Event matrix — anti-pattern cooldown.

Source: 移植自 novel-creator-skill/scripts/event_matrix_scheduler.py
Path in references: references/01-ai-webnovel-repos/upstream/02-skills/novel-creator-skill/scripts/event_matrix_scheduler.py
"""
from ..core.patch_base import Patch, CheckContext, ApplyContext, Blocker


EVENT_TYPES = ["conflict_thrill", "tension_escalation", "bond_deepening", "faction_building", "world_painting"]
FAST_TYPES = {"conflict_thrill", "tension_escalation"}
SOFT_TYPES = {"bond_deepening", "faction_building", "world_painting"}


class P3EventMatrix(Patch):
    name = "event_matrix"
    description = "事件矩阵防模式化：冷却 / 连续 / gentle 配额"
    depends_on = ("foreshadow_dag",)

    def check(self, ctx: CheckContext) -> list[Blocker]:
        if "_load_error" in ctx.state:
            return [Blocker(patch=self.name, chapter=ctx.chapter_num,
                            message=f"无法读取 state.json: {ctx.state['_load_error']}",
                            fix_hint="修复 state.json 后重试")]

        ems = ctx.state.get("story_craft", {}).get("event_matrix_state")
        if ems is None:
            return [Blocker(patch=self.name, chapter=ctx.chapter_num, message="event_matrix_state 未初始化", fix_hint="运行 consistency init")]

        history = ems.get("history", [])
        if not isinstance(history, list):
            return [Blocker(patch=self.name, chapter=ctx.chapter_num,
                            message=f"event_matrix_state.history 必须是 list，实际类型：{type(history).__name__}",
                            fix_hint="运行 consistency init 重建")]
        if not history:
            return []

        window_size = max(ems.get("gentle_window", 5), ems.get("max_consecutive_fast", 2) + 1)
        recent = history[-window_size:]

        blockers = []

        # 1. 连续快档上限
        consecutive_fast = 0
        for entry in reversed(recent):
            primary = entry.get("primary", "")
            if primary in FAST_TYPES:
                consecutive_fast += 1
            else:
                break
        max_allowed = ems.get("max_consecutive_fast", 2)
        if consecutive_fast > max_allowed:
            blockers.append(Blocker(
                patch=self.name,
                chapter=ctx.chapter_num,
                message=f"连续 {consecutive_fast} 章使用快档事件类型（上限 {max_allowed}）",
                fix_hint="本章选 bond_deepening / world_painting / faction_building 中的一种"
            ))

        # 2. gentle 配额
        gentle_window = ems.get("gentle_window", 5)
        recent_window = history[-gentle_window:]
        has_soft = any(entry.get("primary") in SOFT_TYPES for entry in recent_window)
        if not has_soft and len(recent_window) == gentle_window:
            blockers.append(Blocker(
                patch=self.name,
                chapter=ctx.chapter_num,
                message=f"最近 {gentle_window} 章没有 soft 类型事件（gentle quota）",
                fix_hint="本章选 bond_deepening / world_painting / faction_building"
            ))

        return blockers

    def apply(self, ctx: ApplyContext) -> None:
        # No-op by default — apply_with_primary() is the explicit entry from skill
        ems = ctx.state.setdefault("story_craft", {}).setdefault("event_matrix_state", {"version": 1, "types": {}, "history": [], "gentle_window": 5, "max_consecutive_fast": 2})
        # ensure history exists
        ems.setdefault("history", [])