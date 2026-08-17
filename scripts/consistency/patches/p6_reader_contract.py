"""Patch 6: Reader contract 5 dimensions.

Source: 借鉴 oh-story-claudecode/skills/story-long-write/references/reader-contract-and-progression.md
Path in references: references/01-ai-webnovel-repos/upstream/02-skills/oh-story-claudecode/skills/story-long-write/references/reader-contract-and-progression.md
Dimensions: 因果权 / 期待债 / 终局储备 / 换书债 / 履约爽文
"""
from ..core.patch_base import Patch, CheckContext, ApplyContext, Blocker


class P6ReaderContract(Patch):
    name = "reader_contract"
    description = "读者契约 5 维度：因果权 + 期待债 + 终局储备 + 换书债 + 履约爽文"
    depends_on = ("foreshadow_dag", "pacing_tracker")

    DEBT_LIMIT = 10  # 未偿期待债上限
    ENDGAME_RESERVE_USED_LIMIT = 1  # 单卷最多用 1 个终局底牌

    def check(self, ctx: CheckContext) -> list[Blocker]:
        rc = ctx.state.get("story_craft", {}).get("reader_contract")
        if rc is None:
            return [Blocker(patch=self.name, chapter=ctx.chapter_num, message="reader_contract 未初始化", fix_hint="运行 consistency init")]

        blockers = []

        # 1. 期待债堆积
        debts = [d for d in rc.get("expectation_debt", []) if d.get("satisfied_chapter") is None]
        if len(debts) > self.DEBT_LIMIT:
            blockers.append(Blocker(
                patch=self.name,
                chapter=ctx.chapter_num,
                message=f"未偿期待债 {len(debts)} 项，超过上限 {self.DEBT_LIMIT}",
                fix_hint="本章偿还至少 1 项期待债，或减少新增"
            ))

        # 2. 因果权：主角用了未铺垫的能力
        if ctx.chapter_text:
            setup_needed = rc.get("causal_credits", {}).get("protagonist_actions_used_without_setup", [])
            for action in setup_needed:
                if action and action in ctx.chapter_text:
                    blockers.append(Blocker(
                        patch=self.name,
                        chapter=ctx.chapter_num,
                        message=f"主角使用未铺垫的能力/事件：'{action}'",
                        fix_hint=f"在前文铺垫 '{action}' 或在本章加入解释"
                    ))

        # 3. 终局底牌超用
        endgame_used = sum(
            1 for r in rc.get("endgame_reserves", [])
            if r.get("used_chapter") is not None and r["used_chapter"] <= ctx.chapter_num
        )
        if endgame_used > self.ENDGAME_RESERVE_USED_LIMIT:
            blockers.append(Blocker(
                patch=self.name,
                chapter=ctx.chapter_num,
                message=f"终局底牌已用 {endgame_used} 个（单卷上限 {self.ENDGAME_RESERVE_USED_LIMIT}）",
                fix_hint="推迟使用剩余底牌，留到高潮"
            ))

        return blockers

    def apply(self, ctx: ApplyContext) -> None:
        rc = ctx.state.setdefault("story_craft", {}).setdefault(
            "reader_contract",
            {"version": 1, "expectation_debt": [], "causal_credits": {"protagonist_actions_used_without_setup": []}, "endgame_reserves": [], "swap_debts": []}
        )
        rc.setdefault("expectation_debt", [])
        rc.setdefault("causal_credits", {"protagonist_actions_used_without_setup": []})
        rc.setdefault("endgame_reserves", [])
        rc.setdefault("swap_debts", [])
