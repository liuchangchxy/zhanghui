"""Patch 2: Volume anchor quota gate.

Source: 移植自 novel-creator-skill/scripts/outline_anchor_manager.py
Path in references: references/01-ai-webnovel-repos/upstream/02-skills/novel-creator-skill/scripts/outline_anchor_manager.py
"""
from ..core.patch_base import Patch, CheckContext, ApplyContext, Blocker


class P2VolumeAnchor(Patch):
    name = "volume_anchor"
    description = "大纲 anchor 配额门禁"
    depends_on = ()

    PROGRESS_THRESHOLD = 0.15  # 进度偏离阈值

    def check(self, ctx: CheckContext) -> list[Blocker]:
        anchors_data = ctx.state.get("story_craft", {}).get("volume_anchors")
        if anchors_data is None:
            return [Blocker(patch=self.name, chapter=ctx.chapter_num, message="volume_anchors 未初始化", fix_hint="运行 consistency init")]

        anchors = anchors_data.get("anchors", [])
        blockers = []

        for anchor in anchors:
            total = anchor.get("total_chapters", 0)
            current = anchor.get("current_chapter", 0)

            if total == 0 or current == 0:
                # 还没开始写，跳过进度检查
                continue

            # 进度偏离检查
            actual_progress = current / total
            expected_progress = ctx.chapter_num / total  # 简化：用当前章 / 总章
            deviation = abs(actual_progress - expected_progress)

            if deviation > self.PROGRESS_THRESHOLD:
                blockers.append(Blocker(
                    patch=self.name,
                    chapter=ctx.chapter_num,
                    message=f"第{anchor['volume']}卷进度偏离预期 {actual_progress:.0%} vs 期望 {expected_progress:.0%}（偏差 {deviation:.0%}）",
                    fix_hint="加快/放缓节奏，或调整剩余章纲"
                ))

            # must_not_reveal 检查
            if ctx.chapter_text:
                for forbidden in anchor.get("must_not_reveal", []):
                    if forbidden and forbidden in ctx.chapter_text:
                        blockers.append(Blocker(
                            patch=self.name,
                            chapter=ctx.chapter_num,
                            message=f"正文泄露 anchor.must_not_reveal: '{forbidden}'",
                            fix_hint=f"删除 '{forbidden}' 相关内容，或调整 must_not_reveal 列表"
                        ))

        return blockers

    def apply(self, ctx: ApplyContext) -> None:
        anchors_data = ctx.state.setdefault("story_craft", {}).setdefault("volume_anchors", {"version": 1, "anchors": []})
        for anchor in anchors_data.get("anchors", []):
            if anchor.get("current_chapter", 0) < ctx.chapter_num:
                anchor["current_chapter"] = ctx.chapter_num