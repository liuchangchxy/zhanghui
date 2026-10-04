"""Consistency runner — orchestrates all 7 patches.

Source: 借鉴 oh-story-claudecode/skills/story-long-write/references/tracking-transaction.md 的事务模式
Path in references: references/01-ai-webnovel-repos/upstream/02-skills/oh-story-claudecode/skills/story-import/references/tracking-transaction.md
"""
import json
import sys
from pathlib import Path

from .patch_base import Patch, CheckContext, ApplyContext, Blocker


def _import_atomic_write_json():
    """Lazy import: prefer security_utils, fallback to inline raw write."""
    try:
        # The plugin ships security_utils at a known path; allow running outside the plugin context.
        from security_utils import atomic_write_json  # type: ignore
        return atomic_write_json
    except ImportError:
        try:
            plugin_root = Path(__file__).resolve().parents[3] / ".claude" / "plugins" / "zhanghui" / "scripts"
            if str(plugin_root) not in sys.path:
                sys.path.insert(0, str(plugin_root))
            from security_utils import atomic_write_json  # type: ignore
            return atomic_write_json
        except ImportError:
            return None


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
        patches = [
            P1ForeshadowDAG(),
            P2VolumeAnchor(),
            P3EventMatrix(),
            P4PacingTracker(),
            P5StateRevision(),
            P6ReaderContract(),
            P7DerivedViews(),
        ]
        # Validate depends_on chain: every dependency must resolve to a patch
        # registered in the default set. Catches typos and missing imports at
        # init time rather than during a chapter check.
        names = {p.name for p in patches}
        for p in patches:
            for dep in p.depends_on:
                if dep not in names:
                    raise RuntimeError(f"Patch {p.name} depends on unknown patch {dep}")
        return patches

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
            try:
                patch_blockers = patch.check(ctx)
            except Exception as e:
                patch_blockers = [Blocker(
                    patch=patch.name,
                    chapter=ctx.chapter_num,
                    message=f"patch crashed: {type(e).__name__}: {e}",
                    fix_hint="检查 state.json 是否被手动改坏，或运行 consistency init 重建",
                )]
            all_blockers.extend(patch_blockers)
        return all_blockers

    def apply_all(self, chapter: int) -> None:
        """Apply all patches' state mutations and persist."""
        if self.patches is None:
            self.patches = self._default_patches()

        state = self._load_state()
        # Pop stale fields before applying (Fix F: prevent next check from immediately failing)
        state.pop("_expected_revision", None)
        state.pop("_load_error", None)
        for patch in self.patches:
            ctx = ApplyContext(
                project_root=self.project_root,
                chapter_num=chapter,
                state=state,
            )
            try:
                patch.apply(ctx)
            except Exception as e:
                # Don't let one bad patch abort the rest — log via state
                state.setdefault("_apply_errors", []).append(
                    f"{patch.name}: {type(e).__name__}: {e}"
                )
        # Stamp wall-clock timestamp at the end (P5 leaves the field for caller to fill)
        from datetime import datetime, timezone
        state.setdefault("state", {})["_last_modified_at"] = datetime.now(timezone.utc).isoformat()
        self._save_state(state)

    def _load_state(self) -> dict:
        state_path = self.project_root / ".webnovel" / "state.json"
        if not state_path.exists():
            return {}
        try:
            with open(state_path, encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, UnicodeDecodeError, OSError) as e:
            return {"_load_error": f"{type(e).__name__}: {e}"}

    def _save_state(self, state: dict) -> None:
        state_path = self.project_root / ".webnovel" / "state.json"
        state_path.parent.mkdir(parents=True, exist_ok=True)
        atomic_write_json = _import_atomic_write_json()
        if atomic_write_json is not None:
            atomic_write_json(state_path, state, use_lock=True, backup=True)
        else:
            state_path.write_text(
                json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8"
            )

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
