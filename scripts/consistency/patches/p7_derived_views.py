"""Patch 7: Derived views — generated from state, must stay in sync.

Source: 借鉴 oh-story-claudecode tracking_commit.py 的"派生视图由工具生成"模式
Path in references: references/01-ai-webnovel-repos/upstream/02-skills/oh-story-claudecode/skills/story-import/references/state-tracking.md
"""
from ..core.patch_base import Patch, CheckContext, ApplyContext, Blocker


class P7DerivedViews(Patch):
    name = "derived_views"
    description = "派生视图与 state 一致性"
    depends_on = ("state_revision",)

    def check(self, ctx: CheckContext) -> list[Blocker]:
        views_dir = ctx.project_root / ".webnovel" / "views"
        if not views_dir.exists():
            return []

        blockers = []
        fs_table = views_dir / "foreshadow_table.md"
        if fs_table.exists():
            content = fs_table.read_text(encoding="utf-8")
            dag = ctx.state.get("story_craft", {}).get("foreshadow_chain", {}).get("dag", [])
            for fs in dag:
                if fs.get("id") and fs["id"] not in content:
                    blockers.append(Blocker(
                        patch=self.name,
                        chapter=ctx.chapter_num,
                        message=f"派生视图 foreshadow_table.md 缺少伏笔 {fs.get('id')}",
                        fix_hint="运行 consistency apply 重新生成 views/",
                    ))

        return blockers

    def apply(self, ctx: ApplyContext) -> None:
        views_dir = ctx.project_root / ".webnovel" / "views"
        views_dir.mkdir(parents=True, exist_ok=True)

        dag = ctx.state.get("story_craft", {}).get("foreshadow_chain", {}).get("dag", [])
        lines = ["# 伏笔表", "", "| ID | 内容 | 层级 | 埋设章 | 回收章 | 状态 |", "|---|---|---|---|---|---|"]
        for fs in dag:
            paid_off = fs.get("paid_off_chapter")
            paid_off_str = str(paid_off) if paid_off is not None else "未回收"
            lines.append(
                f"| {fs.get('id', '')} | {fs.get('content', '')} | {fs.get('level', '')} | {fs.get('planted_chapter', '')} | {paid_off_str} | {fs.get('status', '')} |"
            )
        (views_dir / "foreshadow_table.md").write_text("\n".join(lines), encoding="utf-8")
