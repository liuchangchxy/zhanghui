"""Patch 3: Event matrix — anti-pattern cooldown.

Source: 移植自 novel-creator-skill/scripts/event_matrix_scheduler.py
Path in references: references/01-ai-webnovel-repos/upstream/02-skills/novel-creator-skill/scripts/event_matrix_scheduler.py
"""
from ..core.patch_base import Patch, CheckContext, ApplyContext, PatchFinding


EVENT_TYPES = ["conflict_thrill", "tension_escalation", "bond_deepening", "faction_building", "world_painting"]
FAST_TYPES = {"conflict_thrill", "tension_escalation"}
SOFT_TYPES = {"bond_deepening", "faction_building", "world_painting"}


class P3EventMatrix(Patch):
    name = "event_matrix"
    description = "事件矩阵防模式化：冷却 / 连续 / gentle 配额"
    depends_on = ("foreshadow_dag",)

    def _finding(self, ctx, issue_code, message, fix_hint, evidence):
        return PatchFinding(
            patch=self.name, chapter=ctx.chapter_num, issue_code=issue_code,
            message=message, fix_hint=fix_hint, evidence=evidence,
            checker_id=self.name, checker_version="1",
            input_ref={"source": "state.story_craft.event_matrix_state"},
        )

    def check(self, ctx: CheckContext) -> list[PatchFinding]:
        if "_load_error" in ctx.state:
            return [self._finding(ctx, "invalid_state", "无法读取 state.json", "修复 state.json 后重试",
                                  {"source": "state.json", "error_type": "load_error"})]

        ems = ctx.state.get("story_craft", {}).get("event_matrix_state")
        if ems is None:
            return [self._finding(ctx, "invalid_state", "event_matrix_state 未初始化", "运行 consistency init",
                                  {"source_field": "story_craft.event_matrix_state", "reason": "missing"})]
        if not isinstance(ems, dict):
            return [self._finding(ctx, "invalid_state", "event_matrix_state 必须是对象", "运行 consistency init 重建",
                                  {"source_field": "story_craft.event_matrix_state", "reason": "not_object",
                                   "actual_type": type(ems).__name__})]

        history = ems.get("history", [])
        if not isinstance(history, list):
            return [self._finding(ctx, "malformed_history", "event_matrix_state.history 必须是 list",
                                  "运行 consistency init 重建",
                                  {"source_field": "story_craft.event_matrix_state.history", "reason": "not_list",
                                   "actual_type": type(history).__name__})]
        if any(not isinstance(entry, dict) for entry in history):
            return [self._finding(ctx, "malformed_history", "event_matrix_state.history 含非对象记录",
                                  "运行 consistency init 重建",
                                  {"source_field": "story_craft.event_matrix_state.history", "reason": "non_object_entry"})]
        for index, entry in enumerate(history):
            if "primary" in entry and not isinstance(entry["primary"], str):
                return [self._finding(ctx, "malformed_history", "event_matrix_state.history.primary 必须是文本",
                                      "运行 consistency init 重建",
                                      {"source_field": "story_craft.event_matrix_state.history.primary",
                                       "reason": "not_text", "entry_index": index,
                                       "actual_type": type(entry["primary"]).__name__})]
        gentle_window = ems.get("gentle_window", 5)
        max_allowed = ems.get("max_consecutive_fast", 2)
        invalid_gentle = not isinstance(gentle_window, int) or isinstance(gentle_window, bool) or gentle_window < 1
        invalid_max = not isinstance(max_allowed, int) or isinstance(max_allowed, bool) or max_allowed < 0
        if invalid_gentle or invalid_max:
            bad_value = gentle_window if invalid_gentle else max_allowed
            bad_field = "gentle_window" if invalid_gentle else "max_consecutive_fast"
            return [self._finding(ctx, "invalid_state", f"event_matrix_state.{bad_field} 的值无效",
                                  "运行 consistency init 重建",
                                  {"source_field": f"story_craft.event_matrix_state.{bad_field}",
                                   "reason": "invalid_limit", "actual_type": type(bad_value).__name__})]
        if not history:
            return []

        window_size = max(gentle_window, max_allowed + 1)
        recent = history[-window_size:]

        findings: list[PatchFinding] = []

        # 1. 连续快档上限
        consecutive_fast = 0
        for entry in reversed(recent):
            primary = entry.get("primary", "")
            if primary in FAST_TYPES:
                consecutive_fast += 1
            else:
                break
        if consecutive_fast > max_allowed:
            findings.append(self._finding(ctx, "consecutive_fast",
                                          f"连续 {consecutive_fast} 章使用快档事件类型（上限 {max_allowed}）",
                                          "本章选 bond_deepening / world_painting / faction_building 中的一种",
                                          {"observed": consecutive_fast, "maximum": max_allowed,
                                           "window_size": len(recent)}))

        # 2. gentle 配额
        recent_window = history[-gentle_window:]
        has_soft = any(entry.get("primary") in SOFT_TYPES for entry in recent_window)
        if not has_soft and len(recent_window) == gentle_window:
            findings.append(self._finding(ctx, "gentle_quota",
                                          f"最近 {gentle_window} 章没有 soft 类型事件（gentle quota）",
                                          "本章选 bond_deepening / world_painting / faction_building",
                                          {"window_size": gentle_window, "observed_soft_count": 0,
                                           "required_soft_count": 1, "history_length": len(recent_window)}))

        return findings

    def apply(self, ctx: ApplyContext) -> None:
        # No-op by default — apply_with_primary() is the explicit entry from skill
        ems = ctx.state.setdefault("story_craft", {}).setdefault("event_matrix_state", {"version": 1, "types": {}, "history": [], "gentle_window": 5, "max_consecutive_fast": 2})
        # ensure history exists
        ems.setdefault("history", [])
