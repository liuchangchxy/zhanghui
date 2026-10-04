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
        if "_load_error" in ctx.state:
            return [Blocker(patch=self.name, chapter=ctx.chapter_num,
                            message=f"无法读取 state.json: {ctx.state['_load_error']}",
                            fix_hint="修复 state.json 后重试")]

        anchors_data = ctx.state.get("story_craft", {}).get("volume_anchors")
        if anchors_data is None:
            return [Blocker(patch=self.name, chapter=ctx.chapter_num, message="volume_anchors 未初始化", fix_hint="运行 consistency init")]

        anchors = anchors_data.get("anchors", [])
        blockers = []

        for i, anchor in enumerate(anchors):
            if not isinstance(anchor, dict):
                blockers.append(Blocker(
                    patch=self.name,
                    chapter=ctx.chapter_num,
                    message=f"anchors[{i}] 不是 dict，实际类型：{type(anchor).__name__}",
                    fix_hint="运行 consistency init 重建"
                ))
                continue

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
                    message=f"第{anchor.get('volume', i+1)}卷进度偏离预期 {actual_progress:.0%} vs 期望 {expected_progress:.0%}（偏差 {deviation:.0%}）",
                    fix_hint="加快/放缓节奏，或调整剩余章纲"
                ))

            # must_not_reveal 检查（带类型守卫：必须为 list[str]）
            must_not_reveal = anchor.get("must_not_reveal", [])
            if not isinstance(must_not_reveal, list):
                blockers.append(Blocker(
                    patch=self.name,
                    chapter=ctx.chapter_num,
                    message=f"anchor[{i}].must_not_reveal 必须是 list，实际类型：{type(must_not_reveal).__name__}",
                    fix_hint="运行 consistency init 重建"
                ))
            elif ctx.chapter_text:
                for forbidden in must_not_reveal:
                    if not isinstance(forbidden, str) or len(forbidden) < 1:
                        continue
                    if forbidden in ctx.chapter_text:
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