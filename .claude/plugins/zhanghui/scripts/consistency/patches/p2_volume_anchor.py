"""Patch 2: Volume anchor quota gate.

Source: 移植自 novel-creator-skill/scripts/outline_anchor_manager.py
Path in references: references/01-ai-webnovel-repos/upstream/02-skills/novel-creator-skill/scripts/outline_anchor_manager.py
"""
from ..core.patch_base import Patch, CheckContext, ApplyContext, PatchFinding


class P2VolumeAnchor(Patch):
    name = "volume_anchor"
    description = "大纲 anchor 配额门禁"
    depends_on = ()

    PROGRESS_THRESHOLD = 0.15  # 进度偏离阈值

    def _finding(self, ctx, issue_code, message, fix_hint, evidence, subject_id=None):
        return PatchFinding(
            patch=self.name, chapter=ctx.chapter_num, issue_code=issue_code,
            message=message, fix_hint=fix_hint, subject_id=subject_id, evidence=evidence,
            checker_id=self.name, checker_version="1",
            input_ref={"source": "state.story_craft.volume_anchors", "chapter_text_read": bool(ctx.chapter_text)},
        )

    @staticmethod
    def _anchor_subject(anchor):
        volume = anchor.get("volume") if isinstance(anchor, dict) else None
        if isinstance(volume, (int, str)) and not isinstance(volume, bool) and str(volume).strip():
            return f"volume:{volume}"
        return None

    def check(self, ctx: CheckContext) -> list[PatchFinding]:
        if "_load_error" in ctx.state:
            return [self._finding(ctx, "invalid_state", "无法读取 state.json", "修复 state.json 后重试",
                                  {"source": "state.json", "error_type": "load_error"})]

        anchors_data = ctx.state.get("story_craft", {}).get("volume_anchors")
        if anchors_data is None:
            return [self._finding(ctx, "missing_anchor", "volume_anchors 未初始化", "运行 consistency init",
                                  {"source_field": "story_craft.volume_anchors"})]

        if not isinstance(anchors_data, dict):
            return [self._finding(ctx, "malformed_anchor", "volume_anchors 必须是对象", "运行 consistency init 重建",
                                  {"source_field": "story_craft.volume_anchors", "reason": "not_object",
                                   "actual_type": type(anchors_data).__name__})]

        anchors = anchors_data.get("anchors", [])
        findings: list[PatchFinding] = []
        if not isinstance(anchors, list):
            return [self._finding(ctx, "malformed_anchor", "volume_anchors.anchors 必须是 list",
                                  "运行 consistency init 重建",
                                  {"source_field": "story_craft.volume_anchors.anchors", "reason": "not_list",
                                   "actual_type": type(anchors).__name__})]

        for i, anchor in enumerate(anchors):
            if not isinstance(anchor, dict):
                findings.append(self._finding(ctx, "malformed_anchor", f"anchors[{i}] 不是 dict，实际类型：{type(anchor).__name__}",
                                              "运行 consistency init 重建",
                                              {"source_field": f"story_craft.volume_anchors.anchors[{i}]",
                                               "reason": "not_object", "actual_type": type(anchor).__name__}))
                continue

            total = anchor.get("total_chapters", 0)
            current = anchor.get("current_chapter", 0)

            if (not isinstance(total, int) or isinstance(total, bool) or
                    not isinstance(current, int) or isinstance(current, bool) or total < 0 or current < 0):
                findings.append(self._finding(ctx, "malformed_anchor", "anchor total_chapters/current_chapter 必须是非负整数",
                                              "运行 consistency init 重建",
                                              {"volume": anchor.get("volume"), "total_chapters": total,
                                               "current_chapter": current, "reason": "invalid_progress"},
                                              self._anchor_subject(anchor)))
                continue
            if total == 0 or current == 0:
                # 还没开始写，跳过进度检查
                continue

            # 进度偏离检查
            actual_progress = current / total
            expected_progress = ctx.chapter_num / total  # 简化：用当前章 / 总章
            deviation = abs(actual_progress - expected_progress)

            if deviation > self.PROGRESS_THRESHOLD:
                findings.append(self._finding(ctx, "progress_deviation",
                                              f"第{anchor.get('volume', i+1)}卷进度偏离预期 {actual_progress:.0%} vs 期望 {expected_progress:.0%}（偏差 {deviation:.0%}）",
                                              "加快/放缓节奏，或调整剩余章纲",
                                              {"volume": anchor.get("volume"), "current_chapter": current,
                                               "total_chapters": total, "actual_progress": actual_progress,
                                               "expected_progress": expected_progress, "deviation": deviation,
                                               "threshold": self.PROGRESS_THRESHOLD},
                                              self._anchor_subject(anchor)))

            # must_not_reveal 检查（带类型守卫：必须为 list[str]）
            must_not_reveal = anchor.get("must_not_reveal", [])
            if not isinstance(must_not_reveal, list):
                findings.append(self._finding(ctx, "malformed_anchor",
                                              f"anchor[{i}].must_not_reveal 必须是 list，实际类型：{type(must_not_reveal).__name__}",
                                              "运行 consistency init 重建",
                                              {"volume": anchor.get("volume"), "source_field": "must_not_reveal",
                                               "reason": "not_list", "actual_type": type(must_not_reveal).__name__},
                                              self._anchor_subject(anchor)))
            elif ctx.chapter_text:
                for forbidden in must_not_reveal:
                    if not isinstance(forbidden, str) or len(forbidden) < 1:
                        continue
                    if forbidden in ctx.chapter_text:
                        findings.append(self._finding(ctx, "must_not_reveal", "正文触发 volume anchor must_not_reveal 规则",
                                                      "检查本章正文和 volume anchor 规则",
                                                      {"volume": anchor.get("volume"), "rule_index": must_not_reveal.index(forbidden),
                                                       "present": True}, self._anchor_subject(anchor)))

        return findings

    def apply(self, ctx: ApplyContext) -> None:
        anchors_data = ctx.state.setdefault("story_craft", {}).setdefault("volume_anchors", {"version": 1, "anchors": []})
        for anchor in anchors_data.get("anchors", []):
            if anchor.get("current_chapter", 0) < ctx.chapter_num:
                anchor["current_chapter"] = ctx.chapter_num
