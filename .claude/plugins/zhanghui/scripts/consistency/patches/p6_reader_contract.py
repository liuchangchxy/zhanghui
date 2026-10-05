"""Patch 6: Reader contract 5 dimensions.

Source: 借鉴 oh-story-claudecode/skills/story-long-write/references/reader-contract-and-progression.md
Path in references: references/01-ai-webnovel-repos/upstream/02-skills/oh-story-claudecode/skills/story-long-write/references/reader-contract-and-progression.md
Dimensions: 因果权 / 期待债 / 终局储备 / 换书债 / 履约爽文
"""
from ..core.patch_base import Patch, CheckContext, ApplyContext, PatchFinding


class P6ReaderContract(Patch):
    name = "reader_contract"
    description = "读者契约 5 维度：因果权 + 期待债 + 终局储备 + 换书债 + 履约爽文"
    depends_on = ("foreshadow_dag", "pacing_tracker")

    DEBT_LIMIT = 10  # 未偿期待债上限
    ENDGAME_RESERVE_USED_LIMIT = 1  # 单卷最多用 1 个终局底牌

    def _finding(self, ctx, issue_code, message, fix_hint, evidence, subject_id=None):
        return PatchFinding(
            patch=self.name, chapter=ctx.chapter_num, issue_code=issue_code,
            message=message, fix_hint=fix_hint, subject_id=subject_id, evidence=evidence,
            checker_id=self.name, checker_version="1",
            input_ref={"source": "state.story_craft.reader_contract", "chapter_text_read": bool(ctx.chapter_text)},
        )

    def check(self, ctx: CheckContext) -> list[PatchFinding]:
        if "_load_error" in ctx.state:
            return [self._finding(ctx, "invalid_state", "无法读取 state.json", "修复 state.json 后重试",
                                  {"source": "state.json", "error_type": "load_error"})]

        rc = ctx.state.get("story_craft", {}).get("reader_contract")
        if rc is None:
            return [self._finding(ctx, "invalid_state", "reader_contract 未初始化", "运行 consistency init",
                                  {"source_field": "story_craft.reader_contract", "reason": "missing"})]
        if not isinstance(rc, dict):
            return [self._finding(ctx, "invalid_state", "reader_contract 必须是对象", "运行 consistency init 重建",
                                  {"source_field": "story_craft.reader_contract", "reason": "not_object",
                                   "actual_type": type(rc).__name__})]

        findings: list[PatchFinding] = []

        # 1. 期待债堆积
        debts = [d for d in rc.get("expectation_debt", []) if isinstance(d, dict) and d.get("satisfied_chapter") is None]
        if len(debts) > self.DEBT_LIMIT:
            findings.append(self._finding(ctx, "high_expectation_debt",
                                          f"未偿期待债 {len(debts)} 项，超过上限 {self.DEBT_LIMIT}",
                                          "本章偿还至少 1 项期待债，或减少新增",
                                          {"observed": len(debts), "limit": self.DEBT_LIMIT,
                                           "unsatisfied_count": len(debts)}))

        # 2. 因果权：主角用了未铺垫的能力
        if ctx.chapter_text:
            causal_credits = rc.get("causal_credits", {})
            setup_needed = causal_credits.get("protagonist_actions_used_without_setup", []) if isinstance(causal_credits, dict) else []
            if not isinstance(setup_needed, list):
                setup_needed = []
            for action_index, action in enumerate(setup_needed):
                if isinstance(action, str) and action and action in ctx.chapter_text:
                    findings.append(self._finding(ctx, "unsetup_action", "正文触发未铺垫能力/事件规则",
                                                  "检查本章正文是否需要前文铺垫或解释",
                                                  {"action_index": action_index, "present": True}))

        # 3. 终局底牌超用（带类型守卫：entries may be dicts OR plain strings）
        endgame_reserves = rc.get("endgame_reserves", [])
        if not isinstance(endgame_reserves, list):
            endgame_reserves = []
        endgame_used = sum(
            1 for r in endgame_reserves
            if isinstance(r, dict) and r.get("used_chapter") is not None and r["used_chapter"] <= ctx.chapter_num
        )
        if endgame_used > self.ENDGAME_RESERVE_USED_LIMIT:
            findings.append(self._finding(ctx, "endgame_limit",
                                          f"终局底牌已用 {endgame_used} 个（单卷上限 {self.ENDGAME_RESERVE_USED_LIMIT}）",
                                          "推迟使用剩余底牌，留到高潮",
                                          {"observed": endgame_used, "limit": self.ENDGAME_RESERVE_USED_LIMIT}))

        # 4. 换书债（swap_debts）：risk=high 时阻断新书接续
        swap_debts = rc.get("swap_debts", [])
        if isinstance(swap_debts, list):
            for debt_index, debt in enumerate(swap_debts):
                if not isinstance(debt, dict):
                    continue
                if debt.get("risk") == "high":
                    findings.append(self._finding(ctx, "high_swap_risk", "换书债风险高",
                                                  "降低换书债风险或暂缓换书",
                                                  {"risk": "high", "debt_index": debt_index}))

        # 5. 履约爽文（contract_fulfillment）：status=broken 时阻断
        fulfillment = rc.get("contract_fulfillment", [])
        if isinstance(fulfillment, list):
            for promise in fulfillment:
                if not isinstance(promise, dict):
                    continue
                if promise.get("status") == "broken":
                    promise_id = promise.get("promise_id")
                    findings.append(self._finding(ctx, "broken_promise",
                                                  f"履约爽文失败：{promise_id} (承诺第{promise.get('chapter_promised')}章，应在第{promise.get('chapter_satisfied')}章兑现)",
                                                  "立即兑现承诺或更新 contract_fulfillment.status='deferred'",
                                                  {"promise_id": promise_id, "status": "broken",
                                                   "chapter_promised": promise.get("chapter_promised"),
                                                   "chapter_satisfied": promise.get("chapter_satisfied")},
                                                  subject_id=f"promise:{promise_id}" if isinstance(promise_id, str) and promise_id.strip() else None))

        return findings

    def apply(self, ctx: ApplyContext) -> None:
        rc = ctx.state.setdefault("story_craft", {}).setdefault(
            "reader_contract",
            {"version": 1, "expectation_debt": [], "causal_credits": {"protagonist_actions_used_without_setup": []}, "endgame_reserves": [], "swap_debts": [], "contract_fulfillment": []}
        )
        rc.setdefault("expectation_debt", [])
        rc.setdefault("causal_credits", {"protagonist_actions_used_without_setup": []})
        rc.setdefault("endgame_reserves", [])
        rc.setdefault("swap_debts", [])
        rc.setdefault("contract_fulfillment", [])
