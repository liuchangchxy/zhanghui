"""Consistency runner — orchestrates all 7 patches.

Source: 借鉴 oh-story-claudecode/skills/story-long-write/references/tracking-transaction.md 的事务模式
Path in references: references/01-ai-webnovel-repos/upstream/02-skills/oh-story-claudecode/skills/story-import/references/tracking-transaction.md
"""
from pathlib import Path
from .patch_base import Patch, CheckContext, Blocker


class ConsistencyRunner:
    def __init__(self, project_root: Path, patches: list[Patch] | None = None):
        self.project_root = project_root
        self.patches = patches

    def _default_patches(self) -> list[Patch]:
        raise NotImplementedError("Default patches not yet wired; pass explicit list")

    def run_all(
        self,
        chapter: int,
        *,
        chapter_outline: dict | None = None,
        chapter_text: str | None = None,
        previous_chapters: list[dict] | None = None,
        state: dict | None = None,
    ) -> list[Blocker]:
        if self.patches is None:
            self.patches = self._default_patches()

        if state is None:
            state = self._load_state()
        if previous_chapters is None:
            previous_chapters = self._load_summaries(chapter)

        all_blockers: list[Blocker] = []
        for patch in self.patches:
            ctx = CheckContext(
                project_root=self.project_root,
                chapter_num=chapter,
                state=state,
                chapter_outline=chapter_outline,
                previous_chapters=previous_chapters,
                chapter_text=chapter_text,
            )
            all_blockers.extend(patch.check(ctx))
        return all_blockers

    def _load_state(self) -> dict:
        state_path = self.project_root / ".webnovel" / "state.json"
        if not state_path.exists():
            return {}
        import json
        with open(state_path, encoding="utf-8") as f:
            return json.load(f)

    def _load_summaries(self, chapter: int) -> list[dict]:
        summaries_dir = self.project_root / ".webnovel" / "summaries"
        if not summaries_dir.exists():
            return []
        result = []
        for i in range(max(1, chapter - 5), chapter):
            p = summaries_dir / f"ch{i:04d}.md"
            if p.exists():
                result.append({"chapter": i, "path": str(p)})
        return result
