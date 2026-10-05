"""Patch 4: Pacing 3-tier tracker.

Source: 移植自 novel-creator-skill/scripts/pacing_tracker.py
Path in references: references/01-ai-webnovel-repos/upstream/02-skills/novel-creator-skill/scripts/pacing_tracker.py
"""
from ..core.patch_base import Patch, CheckContext, ApplyContext, PatchFinding


class P4PacingTracker(Patch):
    name = "pacing_tracker"
    description = "节奏 3 档追踪：连续快档上限 + 慢档配额"
    depends_on = ()

    def _finding(self, ctx, issue_code, message, fix_hint, evidence):
        return PatchFinding(
            patch=self.name, chapter=ctx.chapter_num, issue_code=issue_code,
            message=message, fix_hint=fix_hint, evidence=evidence,
            checker_id=self.name, checker_version="1",
            input_ref={"source": "state.story_craft.pacing_history"},
        )

    def check(self, ctx: CheckContext) -> list[PatchFinding]:
        if "_load_error" in ctx.state:
            return [self._finding(ctx, "invalid_state", "无法读取 state.json", "修复 state.json 后重试",
                                  {"source": "state.json", "error_type": "load_error"})]

        ph = ctx.state.get("story_craft", {}).get("pacing_history")
        if ph is None:
            return [self._finding(ctx, "invalid_state", "pacing_history 未初始化", "运行 consistency init",
                                  {"source_field": "story_craft.pacing_history", "reason": "missing"})]
        if not isinstance(ph, dict):
            return [self._finding(ctx, "invalid_state", "pacing_history 必须是对象", "运行 consistency init 重建",
                                  {"source_field": "story_craft.pacing_history", "reason": "not_object",
                                   "actual_type": type(ph).__name__})]

        history = ph.get("history", [])
        if not isinstance(history, list):
            return [self._finding(ctx, "malformed_history", "pacing_history.history 必须是 list",
                                  "运行 consistency init 重建",
                                  {"source_field": "state.story_craft.pacing_history.history", "reason": "not_list",
                                   "actual_type": type(history).__name__})]
        if any(not isinstance(entry, dict) for entry in history):
            return [self._finding(ctx, "malformed_history", "pacing_history.history 含非对象记录",
                                  "运行 consistency init 重建",
                                  {"source_field": "state.story_craft.pacing_history.history", "reason": "non_object_entry"})]
        rules = ph.get("rules", {"max_consecutive_fast": 1, "slow_per_4_chapters_min": 1})
        if not isinstance(rules, dict):
            return [self._finding(ctx, "malformed_history", "pacing_history.rules 必须是对象",
                                  "运行 consistency init 重建",
                                  {"source_field": "state.story_craft.pacing_history.rules", "reason": "not_object",
                                   "actual_type": type(rules).__name__})]
        max_fast = rules.get("max_consecutive_fast", 1)
        required_slow = rules.get("slow_per_4_chapters_min", 1)
        invalid_max = not isinstance(max_fast, int) or isinstance(max_fast, bool) or max_fast < 0
        invalid_slow = not isinstance(required_slow, int) or isinstance(required_slow, bool) or required_slow < 0
        if invalid_max or invalid_slow:
            bad_value = max_fast if invalid_max else required_slow
            bad_field = "max_consecutive_fast" if invalid_max else "slow_per_4_chapters_min"
            return [self._finding(ctx, "invalid_state", f"pacing_history.rules.{bad_field} 的值无效",
                                  "运行 consistency init 重建",
                                  {"source_field": f"state.story_craft.pacing_history.rules.{bad_field}",
                                   "reason": "invalid_limit", "actual_type": type(bad_value).__name__})]

        findings: list[PatchFinding] = []

        # 1. 连续快档上限
        consecutive_fast = 0
        for entry in reversed(history):
            if entry.get("tier") == "fast":
                consecutive_fast += 1
            else:
                break
        if consecutive_fast > max_fast:
            maximum = max_fast
            findings.append(self._finding(ctx, "consecutive_fast",
                                          f"已连续 {consecutive_fast} 章快档（上限 {maximum}）",
                                          "本章建议选 medium 或 slow",
                                          {"observed": consecutive_fast, "maximum": maximum,
                                           "window_size": len(history)}))

        # 2. 每 4 章至少 1 慢档
        recent_4 = history[-4:]
        slow_count = sum(1 for e in recent_4 if e.get("tier") == "slow")
        if len(recent_4) == 4 and slow_count < required_slow:
            required = required_slow
            findings.append(self._finding(ctx, "slow_quota",
                                          f"最近 4 章只有 {slow_count} 章慢档（要求至少 {required}）",
                                          "本章或下一章选 slow",
                                          {"window_size": len(recent_4), "observed_slow_count": slow_count,
                                           "required_slow_count": required}))

        return findings

    def apply(self, ctx: ApplyContext) -> None:
        ph = ctx.state.setdefault("story_craft", {}).setdefault("pacing_history", {"version": 1, "history": [], "rules": {"max_consecutive_fast": 1, "slow_per_4_chapters_min": 1}})
        ph.setdefault("history", [])
