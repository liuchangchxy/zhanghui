"""Consistency runner — orchestrates all 7 patches.

Source: 借鉴 oh-story-claudecode/skills/story-long-write/references/tracking-transaction.md 的事务模式
Path in references: references/01-ai-webnovel-repos/upstream/02-skills/oh-story-claudecode/skills/story-import/references/tracking-transaction.md
"""
from pathlib import Path
from .patch_base import Patch, CheckContext, ApplyContext, Blocker


class ConsistencyRunner:
    def __init__(self, project_root: Path, patches: list[Patch] | None = None):
        self.project_root = project_root
        self.patches = patches

    def _default_patches(self) -> list[Patch]:
        from ..patches.p1_foreshadow_dag import P1ForeshadowDAG
        from ..patches.p2_volume_anchor import P2VolumeAnchor
        from ..patches.p3_event_matrix import P3EventMatrix
        from ..patches.p4_pacing_tracker import P4PacingTracker
        from ..patches.p5_state_revision import P5StateRevision
        from ..patches.p6_reader_contract import P6ReaderContract
        from ..patches.p7_derived_views import P7DerivedViews
        return [
            P1ForeshadowDAG(),
            P2VolumeAnchor(),
            P3EventMatrix(),
            P4PacingTracker(),
            P5StateRevision(),
            P6ReaderContract(),
            P7DerivedViews(),
        ]

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

    def apply_all(self, chapter: int) -> None:
        """Apply all patches' state mutations and persist."""
        if self.patches is None:
            self.patches = self._default_patches()

        state = self._load_state()
        for patch in self.patches:
            ctx = ApplyContext(
                project_root=self.project_root,
                chapter_num=chapter,
                state=state,
            )
            patch.apply(ctx)
        self._save_state(state)

    def _load_state(self) -> dict:
        state_path = self.project_root / ".webnovel" / "state.json"
        if not state_path.exists():
            return {}
        import json
        with open(state_path, encoding="utf-8") as f:
            return json.load(f)

    def _save_state(self, state: dict) -> None:
        state_path = self.project_root / ".webnovel" / "state.json"
        state_path.parent.mkdir(parents=True, exist_ok=True)
        import json
        state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")

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
