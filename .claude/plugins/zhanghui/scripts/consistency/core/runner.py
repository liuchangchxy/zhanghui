"""Consistency runner — orchestrates all 7 patches.

Source: 借鉴 oh-story-claudecode/skills/story-long-write/references/tracking-transaction.md 的事务模式
Path in references: references/01-ai-webnovel-repos/upstream/02-skills/oh-story-claudecode/skills/story-import/references/tracking-transaction.md
"""
import json
import hashlib
import sys
from dataclasses import dataclass, replace
from copy import deepcopy
from pathlib import Path

from .patch_base import Patch, CheckContext, ApplyContext, PatchFinding
try:
    from data_modules.story_system_mode import is_story_system_project
except ImportError:  # pragma: no cover - standalone script import layout
    from scripts.data_modules.story_system_mode import is_story_system_project


@dataclass(frozen=True)
class InfrastructureDiagnostic:
    checker_id: str
    diagnostic_code: str
    error_type: str | None = None


@dataclass
class ConsistencyEvaluation:
    chapter: int
    status: str
    source_input_fingerprint: str
    findings: list[PatchFinding]
    diagnostics: list[InfrastructureDiagnostic]


@dataclass(frozen=True)
class ApplyOutcome:
    patch: str
    status: str
    error_type: str | None = None


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
    # These state.json fields are projections owned by accepted chapter commits.
    # Consistency maintenance may update Intent/craft metadata and infrastructure,
    # but it must not become another writer of chapter-derived story state.
    COMMIT_OWNED_STATE_KEYS = (
        "entity_state",
        "protagonist_state",
        "progress",
        "strand_tracker",
        "plot_threads",
    )

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
        patch_names: set[str] | None = None,
        chapter_outline: dict | None = None,
        chapter_text: str | None = None,
        previous_chapters: list[dict] | None = None,
        state: dict | None = None,
    ) -> ConsistencyEvaluation:
        if self.patches is None:
            self.patches = self._default_patches()
        selected_patches = self.patches
        if patch_names is not None:
            available = {patch.name for patch in self.patches}
            unknown = patch_names - available
            if unknown:
                raise ValueError(f"unknown consistency patch: {', '.join(sorted(unknown))}")
            selected_patches = [patch for patch in self.patches if patch.name in patch_names]

        if state is None:
            state = self._load_state()
        if previous_chapters is None:
            previous_chapters = self._load_summaries(chapter)

        if "_load_error" in state:
            error_type = str(state.get("_load_error", "ReadError")).split(":", 1)[0]
            fingerprint = self._fingerprint({
                "chapter": chapter,
                "state_read_error": error_type,
                "checkers": [{"checker_id": patch.name,
                              "checker_version": getattr(patch, "checker_version", "1")}
                             for patch in selected_patches],
            })
            return ConsistencyEvaluation(
                chapter=chapter, status="incomplete", source_input_fingerprint=fingerprint,
                findings=[], diagnostics=[InfrastructureDiagnostic("consistency.runner", "state_read_failed", error_type)],
            )

        diagnostics: list[InfrastructureDiagnostic] = []
        contexts: list[tuple[Patch, CheckContext]] = []
        for patch in selected_patches:
            external_inputs = self._capture_external_inputs(patch, diagnostics)
            contexts.append((patch, CheckContext(
                project_root=self.project_root,
                chapter_num=chapter,
                state=state,
                chapter_outline=chapter_outline,
                previous_chapters=previous_chapters,
                chapter_text=chapter_text,
                external_inputs=external_inputs,
            )))
        source_inputs = [self._patch_source_inputs(patch, ctx) for patch, ctx in contexts]
        try:
            source_input_fingerprint = self._fingerprint({"chapter": chapter, "checkers": source_inputs})
        except (TypeError, ValueError) as exc:
            error_type = type(exc).__name__
            fallback = self._fingerprint({
                "chapter": chapter, "snapshot_error": error_type,
                "checkers": [{"checker_id": patch.name,
                              "checker_version": getattr(patch, "checker_version", "1")}
                             for patch, _ctx in contexts],
            })
            return ConsistencyEvaluation(
                chapter=chapter, status="incomplete", source_input_fingerprint=fallback,
                findings=[], diagnostics=diagnostics + [InfrastructureDiagnostic(
                    "consistency.runner", "source_snapshot_serialization_failed", error_type,
                )],
            )
        all_findings: list[PatchFinding] = []
        incomplete = bool(diagnostics)
        for patch, ctx in contexts:
            try:
                patch_findings = patch.check(ctx)
            except Exception as exc:
                incomplete = True
                diagnostics.append(InfrastructureDiagnostic(
                    checker_id=patch.name, diagnostic_code="checker_failed", error_type=type(exc).__name__,
                ))
                continue
            if not isinstance(patch_findings, list):
                incomplete = True
                diagnostics.append(InfrastructureDiagnostic(
                    checker_id=patch.name, diagnostic_code="invalid_checker_result", error_type=type(patch_findings).__name__,
                ))
                continue
            for finding in patch_findings:
                if isinstance(finding, PatchFinding):
                    all_findings.append(replace(
                        finding,
                        input_ref={**finding.input_ref, "source_input_fingerprint": source_input_fingerprint},
                        checker_id=finding.checker_id or patch.name,
                        checker_version=getattr(patch, "checker_version", finding.checker_version),
                    ))
                else:
                    incomplete = True
                    diagnostics.append(InfrastructureDiagnostic(
                        checker_id=patch.name, diagnostic_code="invalid_finding_type", error_type=type(finding).__name__,
                    ))

        return ConsistencyEvaluation(
            chapter=chapter, status="incomplete" if incomplete else "evaluated",
            source_input_fingerprint=source_input_fingerprint,
            findings=all_findings, diagnostics=diagnostics,
        )

    def _capture_external_inputs(self, patch: Patch, diagnostics: list[InfrastructureDiagnostic]) -> dict[str, object]:
        if patch.name != "derived_views":
            return {}
        views_dir = self.project_root / ".webnovel" / "views"
        view = views_dir / "foreshadow_table.md"
        try:
            views_dir_present = views_dir.exists()
            present = view.exists() if views_dir_present else False
            content = view.read_text(encoding="utf-8") if present else None
            return {"foreshadow_table.md": {
                "path": str(view), "views_dir_present": views_dir_present,
                "present": present, "content": content,
            }}
        except (OSError, UnicodeDecodeError) as exc:
            diagnostics.append(InfrastructureDiagnostic(
                checker_id=patch.name, diagnostic_code="external_input_read_failed", error_type=type(exc).__name__,
            ))
            return {"foreshadow_table.md": {
                "path": str(view), "views_dir_present": True,
                "present": False, "read_error": type(exc).__name__,
            }}

    @staticmethod
    def _fingerprint(source_inputs: dict) -> str:
        canonical = json.dumps(source_inputs, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    def _patch_source_inputs(self, patch: Patch, ctx: CheckContext) -> dict:
        def read_path(root: dict, *path: str) -> dict:
            value = root
            for part in path:
                if not isinstance(value, dict) or part not in value:
                    return {"present": False}
                value = value[part]
            return {"present": True, "value": value}

        name = patch.name
        inputs: dict[str, object] = {"chapter": ctx.chapter_num}
        state = ctx.state
        if name == "foreshadow_dag":
            inputs["foreshadow_chain"] = read_path(state, "story_craft", "foreshadow_chain")
        elif name == "volume_anchor":
            inputs["volume_anchors"] = read_path(state, "story_craft", "volume_anchors")
            if ctx.chapter_text:
                inputs["chapter_text"] = ctx.chapter_text
        elif name == "event_matrix":
            inputs["event_matrix_state"] = read_path(state, "story_craft", "event_matrix_state")
        elif name == "pacing_tracker":
            inputs["pacing_history"] = read_path(state, "story_craft", "pacing_history")
        elif name == "state_revision":
            inputs["expected_revision"] = read_path(state, "_expected_revision")
            inputs["state_revision"] = read_path(state, "state", "_revision")
        elif name == "reader_contract":
            inputs["reader_contract"] = read_path(state, "story_craft", "reader_contract")
            if ctx.chapter_text:
                inputs["chapter_text"] = ctx.chapter_text
        elif name == "derived_views":
            inputs["foreshadow_chain"] = read_path(state, "story_craft", "foreshadow_chain")
            inputs["state_revision"] = read_path(state, "state", "_revision")
            inputs["view"] = ctx.external_inputs.get("foreshadow_table.md", {"present": False})
        else:
            # Unknown/third-party patches may read any CheckContext field.
            inputs.update({
                "state": ctx.state, "chapter_outline": ctx.chapter_outline,
                "previous_chapters": ctx.previous_chapters, "chapter_text": ctx.chapter_text,
            })
        return {
            "checker_id": name,
            "checker_version": getattr(patch, "checker_version", "1"),
            "inputs": inputs,
        }

    def apply_all(self, chapter: int) -> list[ApplyOutcome]:
        """Apply patches; Story System projects only filesystem-derived views."""
        if self.patches is None:
            self.patches = self._default_patches()

        state = self._load_state()
        if "_load_error" in state:
            error_type = str(state["_load_error"]).split(":", 1)[0]
            return [ApplyOutcome("consistency.runner", "failed", error_type)]
        if not isinstance(state, dict):
            return [ApplyOutcome("consistency.runner", "failed", "InvalidState")]
        if self._is_story_system_project():
            # Patches may infer chapter outcomes (for example, advancing a
            # volume anchor). In Story System mode none of their state mutations
            # may become durable outside a chapter commit. P7's explicit view
            # writer remains a rebuildable filesystem projection.
            outcomes: list[ApplyOutcome] = []
            for patch in self.patches:
                if patch.name != "derived_views":
                    outcomes.append(ApplyOutcome(patch.name, "skipped"))
                    continue
                try:
                    patch.apply(ApplyContext(
                        project_root=self.project_root,
                        chapter_num=chapter,
                        state=state,
                    ))
                    outcomes.append(ApplyOutcome(patch.name, "applied"))
                except Exception as exc:
                    # Keep consistency apply's legacy fault isolation without
                    # persisting patch-owned state in canonical mode.
                    outcomes.append(ApplyOutcome(patch.name, "failed", type(exc).__name__))
            return outcomes

        commit_owned = {
            key: deepcopy(state[key])
            for key in self.COMMIT_OWNED_STATE_KEYS
            if key in state
        }
        # Pop stale fields before applying (Fix F: prevent next check from immediately failing)
        state.pop("_expected_revision", None)
        state.pop("_load_error", None)
        outcomes = []
        for patch in self.patches:
            ctx = ApplyContext(
                project_root=self.project_root,
                chapter_num=chapter,
                state=state,
            )
            try:
                patch.apply(ctx)
                outcomes.append(ApplyOutcome(patch.name, "applied"))
            except Exception as e:
                # Don't let one bad patch abort the rest — log via state
                state.setdefault("_apply_errors", []).append(
                    f"{patch.name}: {type(e).__name__}: {e}"
                )
                outcomes.append(ApplyOutcome(patch.name, "failed", type(e).__name__))
        # Stamp wall-clock timestamp at the end (P5 leaves the field for caller to fill)
        from datetime import datetime, timezone
        state.setdefault("state", {})["_last_modified_at"] = datetime.now(timezone.utc).isoformat()
        for key in self.COMMIT_OWNED_STATE_KEYS:
            if key in commit_owned:
                state[key] = commit_owned[key]
            else:
                state.pop(key, None)
        try:
            self._save_state(state)
        except Exception as exc:
            return [ApplyOutcome("consistency.runner", "failed", type(exc).__name__)]
        return outcomes

    def _is_story_system_project(self) -> bool:
        """Use initialized Story System contracts, not presence of a commit."""
        return is_story_system_project(self.project_root)

    def _load_state(self) -> dict:
        state_path = self.project_root / ".webnovel" / "state.json"
        if not state_path.exists():
            return {}
        try:
            with open(state_path, encoding="utf-8") as f:
                state = json.load(f)
            if not isinstance(state, dict):
                return {"_load_error": "InvalidState: state.json must contain a JSON object"}
            return state
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
