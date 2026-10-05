"""Patch 7: Derived views — generated from state, must stay in sync.

Source: 借鉴 oh-story-claudecode tracking_commit.py 的"派生视图由工具生成"模式
Path in references: references/01-ai-webnovel-repos/upstream/02-skills/oh-story-claudecode/skills/story-import/references/state-tracking.md
"""
import re
import sys
from pathlib import Path

from ..core.patch_base import Patch, CheckContext, ApplyContext, Blocker
from .p1_foreshadow_dag import _get_dag


def _import_atomic_write_text():
    """Lazy import of security_utils.atomic_write_text (mirror of runner pattern)."""
    try:
        from security_utils import atomic_write_text  # type: ignore
        return atomic_write_text
    except ImportError:
        try:
            plugin_root = Path(__file__).resolve().parents[3] / ".claude" / "plugins" / "zhanghui" / "scripts"
            if str(plugin_root) not in sys.path:
                sys.path.insert(0, str(plugin_root))
            from security_utils import atomic_write_text  # type: ignore
            return atomic_write_text
        except ImportError:
            return None


class P7DerivedViews(Patch):
    name = "derived_views"
    description = "派生视图与 state 一致性"
    depends_on = ("state_revision",)

    def check(self, ctx: CheckContext) -> list[Blocker]:
        if "_load_error" in ctx.state:
            return [Blocker(patch=self.name, chapter=ctx.chapter_num,
                            message=f"无法读取 state.json: {ctx.state['_load_error']}",
                            fix_hint="修复 state.json 后重试")]

        views_dir = ctx.project_root / ".webnovel" / "views"
        if not views_dir.exists():
            return []

        blockers = []
        fs_table = views_dir / "foreshadow_table.md"
        if fs_table.exists():
            content = fs_table.read_text(encoding="utf-8")
            dag, _fmt = _get_dag(ctx.state)
            if not isinstance(dag, list):
                dag = []
            for fs in dag:
                if fs.get("id"):
                    pattern = r'\b' + re.escape(fs["id"]) + r'\b'
                    if not re.search(pattern, content):
                        blockers.append(Blocker(
                            patch=self.name,
                            chapter=ctx.chapter_num,
                            message=f"派生视图 foreshadow_table.md 缺少伏笔 {fs.get('id')}",
                            fix_hint="运行 consistency apply 重新生成 views/",
                            issue_code="missing_foreshadow_view_row",
                            subject_id=f"foreshadow:{fs['id']}",
                            evidence={"view": "foreshadow_table.md", "foreshadow_id": fs["id"], "present": False},
                        ))

        return blockers

    def apply(self, ctx: ApplyContext) -> None:
        views_dir = ctx.project_root / ".webnovel" / "views"
        views_dir.mkdir(parents=True, exist_ok=True)

        dag, _fmt = _get_dag(ctx.state)
        if not isinstance(dag, list):
            dag = []
        lines = ["# 伏笔表", "", "| ID | 内容 | 层级 | 埋设章 | 回收章 | 状态 |", "|---|---|---|---|---|---|"]
        for fs in dag:
            if not isinstance(fs, dict):
                continue
            paid_off = fs.get("paid_off_chapter")
            paid_off_str = str(paid_off) if paid_off is not None else "未回收"
            lines.append(
                f"| {fs.get('id', '')} | {fs.get('content', '')} | {fs.get('level', '')} | {fs.get('planted_chapter', '')} | {paid_off_str} | {fs.get('status', '')} |"
            )
        content = "\n".join(lines)
        atomic_write_text = _import_atomic_write_text()
        target = views_dir / "foreshadow_table.md"
        if atomic_write_text is not None:
            atomic_write_text(target, content, use_lock=False, backup=False)
        else:
            target.write_text(content, encoding="utf-8")
