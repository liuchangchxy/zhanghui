#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Stage-2 audit repair regression tests.

Each test here pins one repaired defect from
`zhanghui_stage2_全仓缺陷与过度工程化审计_2026-10-20.md`, at the level the defect actually
lived at — runtime/CLI behaviour where possible, not SKILL.md prose.

  R01/R03  findings are routed by owner; advisory is not auto-revised
  R02/D01/D02  review validity follows the reviewed prose, not the whole draft
  R06      convergence counters reach the persisted metrics record
  R07      a closure claim needs a real verification stamp, not a target list
  R08      the score is published under its honest name
  F01      a declared hard length contract blocks; the default target does not
  F02      every documented `runtime ingest-draft` example carries `--chapter`
  A05      `install-plugin.sh --check` cannot report success without checking
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from data_modules.reconciliation import prose_only_text, prose_subject_sha256
from data_modules.review_schema import (
    compute_review_convergence,
    parse_review_output,
)
from data_modules.revision_planner import (
    OWNER_ADVISORY,
    OWNER_ARTIFACT_REPAIR,
    OWNER_GOVERNANCE_REPAIR,
    OWNER_PROSE_EDIT,
    build_revision_plan,
    classify_finding_owner,
    resolve_active_draft_identity,
)
from data_modules.write_gates.length_contract import check_chapter_length, count_hanzi
from data_modules.write_gates.precommit import run_precommit_gate
from review_pipeline import (
    ReviewDraftIdentityError,
    _bind_review_draft_identity,
    _build_review_metrics_record,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
PLUGIN_ROOT = REPO_ROOT / ".claude" / "plugins" / "zhanghui"


# --------------------------------------------------------------------------- #
# fixtures
# --------------------------------------------------------------------------- #


def _changes_block(extra_plot: str = "plot_a") -> str:
    return (
        "<chapter_changes>\n"
        + json.dumps(
            {
                "character_state_changes": [],
                "new_plot_points": [{"plot_id": extra_plot, "description": "推进"}],
                "foreshadowing_actions": [],
                "location_state_changes": [],
                "faction_state_changes": [],
                "time_progression": None,
                "item_transfers": [],
                "unresolved_questions": [],
            },
            ensure_ascii=False,
        )
        + "\n</chapter_changes>\n"
    )


PROSE = "林凡走进矿道。\n\n他听见深处传来脚步声。\n"


def _draft_text(plot_id: str = "plot_a") -> str:
    return PROSE + "\n" + _changes_block(plot_id)


def _write_active_draft(project_root: Path, chapter: int, text: str, draft_id: str) -> dict:
    runtime_dir = project_root / ".webnovel" / "runtime" / f"chapter_{chapter:03d}"
    runtime_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "draft_id": draft_id,
        "chapter": chapter,
        "draft_fingerprint": hashlib.sha256(text.encode("utf-8")).hexdigest(),
        "review_subject_fingerprint": prose_subject_sha256(text),
        "prose": text,
    }
    (runtime_dir / "draft.json").write_text(
        json.dumps(payload, ensure_ascii=False), encoding="utf-8"
    )
    return payload


# --------------------------------------------------------------------------- #
# R02 / D01 / D02 — review validity follows the reviewed prose
# --------------------------------------------------------------------------- #


def test_prose_subject_hash_ignores_changes_only_edits():
    before = _draft_text("plot_a")
    after = _draft_text("plot_b")  # proposal rewritten, prose byte-identical

    assert hashlib.sha256(before.encode()).hexdigest() != hashlib.sha256(after.encode()).hexdigest()
    assert prose_subject_sha256(before) == prose_subject_sha256(after)


def test_prose_subject_hash_changes_when_prose_changes():
    before = _draft_text()
    after = before.replace("他听见深处传来脚步声。", "他听见深处传来急促的脚步声。")
    assert prose_subject_sha256(before) != prose_subject_sha256(after)


def test_prose_only_text_falls_back_to_raw_text_without_changes_block():
    raw = "只有正文，没有 CHANGES 块。\n"
    assert prose_only_text(raw) == raw


def test_review_survives_changes_only_reingest(tmp_path: Path):
    """A `<chapter_changes>` fix mints a new draft but must not invalidate the review."""
    chapter = 4
    old_text = _draft_text("plot_a")
    old_draft = _write_active_draft(tmp_path, chapter, old_text, "draft-004-aaaaaaaa")
    review = parse_review_output(
        chapter=chapter,
        raw={
            "issues": [],
            "draft_id": old_draft["draft_id"],
            "draft_fingerprint": old_draft["draft_fingerprint"],
            "review_subject_fingerprint": old_draft["review_subject_fingerprint"],
        },
    )

    # Re-ingest: only the proposal changed.
    new_text = _draft_text("plot_b")
    new_draft = _write_active_draft(tmp_path, chapter, new_text, "draft-004-bbbbbbbb")
    assert new_draft["draft_fingerprint"] != old_draft["draft_fingerprint"]

    binding = _bind_review_draft_identity(tmp_path, chapter, review)
    assert binding["verified"] is True
    assert binding["mode"] == "declared_review_subject"


def test_review_is_refused_when_the_prose_changed(tmp_path: Path):
    chapter = 4
    old_text = _draft_text()
    old_draft = _write_active_draft(tmp_path, chapter, old_text, "draft-004-aaaaaaaa")
    review = parse_review_output(
        chapter=chapter,
        raw={
            "issues": [],
            "draft_id": old_draft["draft_id"],
            "draft_fingerprint": old_draft["draft_fingerprint"],
            "review_subject_fingerprint": old_draft["review_subject_fingerprint"],
        },
    )

    edited = old_text.replace("脚步声", "呼吸声")
    _write_active_draft(tmp_path, chapter, edited, "draft-004-cccccccc")

    with pytest.raises(ReviewDraftIdentityError):
        _bind_review_draft_identity(tmp_path, chapter, review)


def test_legacy_review_without_subject_fingerprint_keeps_strict_binding(tmp_path: Path):
    """Reviews that declare only the full-draft identity are checked exactly as before."""
    chapter = 5
    old_text = _draft_text()
    old_draft = _write_active_draft(tmp_path, chapter, old_text, "draft-005-aaaaaaaa")
    review = parse_review_output(
        chapter=chapter,
        raw={
            "issues": [],
            "draft_id": old_draft["draft_id"],
            "draft_fingerprint": old_draft["draft_fingerprint"],
        },
    )
    new_text = _draft_text("plot_b")  # prose unchanged, proposal rewritten
    _write_active_draft(tmp_path, chapter, new_text, "draft-005-bbbbbbbb")

    with pytest.raises(ReviewDraftIdentityError):
        _bind_review_draft_identity(tmp_path, chapter, review)


def test_resolve_active_draft_identity_reports_subject_fingerprint(tmp_path: Path):
    text = _draft_text()
    _write_active_draft(tmp_path, 6, text, "draft-006-aaaaaaaa")
    identity = resolve_active_draft_identity(tmp_path, 6)
    assert identity["available"] is True
    assert identity["review_subject_fingerprint"] == prose_subject_sha256(text)


# --------------------------------------------------------------------------- #
# R01 / R03 — findings are routed by owner
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "issue, expected",
    [
        (
            {
                "category": "do_not_copy_violation",
                "description": "无法读取 do_not_copy_check.json（文件不存在或格式错误）。",
                "evidence": "do_not_copy_check.json missing or invalid JSON",
            },
            OWNER_ARTIFACT_REPAIR,
        ),
        (
            # Craft identity is structural, so the ledger vocabulary in the explanation may
            # only refine *which* non-prose layer owns the finding.
            {
                "category": "foreshadow_compliance",
                "description": "FS-002 伏笔元数据未关联 loop_id",
                "gate_id": "story_craft.timed_lock",
            },
            OWNER_GOVERNANCE_REPAIR,
        ),
        (
            {
                "category": "beat_compliance",
                "description": "节奏曲线 WARNING：chapters_since_peak=9",
                "gate_id": "story_craft.rhythm_curve",
            },
            OWNER_ADVISORY,
        ),
        (
            {"category": "timeline", "description": "第三章时间倒退，与上一章冲突"},
            OWNER_PROSE_EDIT,
        ),
        (
            {"category": "continuity", "description": "上章钩子没有回应"},
            OWNER_PROSE_EDIT,
        ),
    ],
)
def test_classify_finding_owner(issue, expected):
    assert classify_finding_owner(issue) == expected


@pytest.mark.parametrize(
    "issue, expected",
    [
        # Conflict sample 1 — a prose finding that talks about metadata. The text patterns
        # used to run *before* the category checks, so this was filed as GOVERNANCE_REPAIR,
        # excluded from the plan, and the actual defect (the prose) was never revised.
        (
            {
                "category": "setting",
                "description": "设定元数据记录他是左撇子，正文第4段却写他右手持刀。",
                "evidence": "设定集/角色.md 与正文第4段冲突",
                "fix_hint": "以设定为准，改正文。",
            },
            OWNER_PROSE_EDIT,
        ),
        (
            {
                "category": "character",
                "description": "人物关系账本里他和老周是仇人，正文写成了旧友。",
                "evidence": "state.json 人物关系 vs 正文第2段",
            },
            OWNER_PROSE_EDIT,
        ),
        # The same holds when the explanation names a pipeline file. `category` is the
        # contract: the Reviewer files a genuinely missing artifact under
        # `do_not_copy_violation` (reviewer.md §10), so a prose category here means the
        # finding is about the prose.
        (
            {
                "category": "continuity",
                "description": "上一章摘要缺失，无法核对本章的呼应。",
                "evidence": "summary_result.json missing",
            },
            OWNER_PROSE_EDIT,
        ),
        # Conflict sample 2 — no structured identity at all: the text is the only signal, so
        # the artifact/ledger hints still decide.
        (
            {
                "category": "other",
                "description": "伏笔账本里这条记录未关联 loop_id",
            },
            OWNER_GOVERNANCE_REPAIR,
        ),
        (
            {
                "category": "other",
                "description": "无法读取 do_not_copy_check.json（文件不存在）",
            },
            OWNER_ARTIFACT_REPAIR,
        ),
    ],
)
def test_classify_finding_owner_never_reroutes_prose_by_text(issue, expected):
    """Structured identity decides ownership; free text may only refine a non-prose owner."""
    assert classify_finding_owner(issue) == expected


def _plan_for(issues, **kwargs):
    text = PROSE + "\n" + _changes_block()
    return build_revision_plan(
        text,
        {"issues": issues, "chapter": 7, "review_subject_fingerprint": prose_subject_sha256(text)},
        chapter=7,
        require_review_binding=False,
        **kwargs,
    )


def test_prose_finding_that_mentions_metadata_still_gets_revised():
    """The mis-routing must not just change a label — it must keep the finding in the plan."""
    plan = _plan_for([
        {
            "category": "setting",
            "description": "设定元数据记录他是左撇子，正文第4段却写他右手持刀。",
            "location": "第1段",
            "evidence": "设定集/角色.md 与正文第4段冲突",
            "fix_hint": "以设定为准，改正文。",
        },
    ])
    assert plan["summary"]["deferred"] == 0
    assert plan["summary"]["deferred_by_owner"][OWNER_GOVERNANCE_REPAIR] == 0
    assert [target["owner"] for target in plan["targets"]] == [OWNER_PROSE_EDIT]


def test_plan_defers_findings_that_prose_editing_cannot_fix():
    plan = _plan_for(
        [
            {"category": "timeline", "description": "时间倒退", "location": "第1段", "evidence": "原文"},
            {
                "category": "do_not_copy_violation",
                "description": "无法读取 do_not_copy_check.json（文件不存在）",
                "evidence": "do_not_copy_check.json missing",
            },
            {
                "category": "beat_compliance",
                "description": "节拍未到达 Midpoint",
                "gate_id": "story_craft.volume_beat",
            },
        ]
    )
    owners = {item["owner"] for item in plan["deferred"]}
    assert owners == {OWNER_ARTIFACT_REPAIR, OWNER_ADVISORY}
    assert plan["summary"]["deferred"] == 2
    assert all(t["owner"] == OWNER_PROSE_EDIT for t in plan["targets"])
    # deferred entries must tell the caller where to fix the problem instead
    assert all(item["repair_hint"] for item in plan["deferred"])


def test_plan_includes_advisory_only_when_explicitly_asked():
    issues = [
        {
            "category": "beat_compliance",
            "description": "节拍未到达 Midpoint",
            "gate_id": "story_craft.volume_beat",
        }
    ]
    assert _plan_for(issues)["summary"]["total"] == 0
    opted_in = _plan_for(issues, include_advisory=True)
    assert opted_in["summary"]["total"] == 1
    assert opted_in["targets"][0]["owner"] == OWNER_ADVISORY


# --------------------------------------------------------------------------- #
# R07 — closure requires a real verification stamp
# --------------------------------------------------------------------------- #


def _prev_review() -> dict:
    return {
        "draft_id": "draft-008-aaaaaaaa",
        "draft_fingerprint": "f" * 64,
        "review_subject_fingerprint": "a" * 64,
        "issues": [
            {
                "issue_id": "FS-002",
                "category": "continuity",
                "severity": "high",
                "description": "玉佩来历与前章冲突",
            }
        ],
    }


def test_target_list_without_verification_stamp_is_not_closure():
    curr = {
        "draft_id": "draft-008-bbbbbbbb",
        "draft_fingerprint": "e" * 64,
        "review_subject_fingerprint": "b" * 64,
        "issues": [],
    }
    convergence = compute_review_convergence(
        curr,
        _prev_review(),
        revision_evidence={"resolved_targets": ["FS-002"], "before_prose_sha256": "a" * 64},
    )
    assert convergence["resolved_count"] == 0
    assert convergence["uncertain_count"] == 1
    assert convergence["all_high_critical_closed"] is False


def test_verified_evidence_bound_to_the_review_subject_is_closure():
    curr = {
        "draft_id": "draft-008-bbbbbbbb",
        "draft_fingerprint": "e" * 64,
        "review_subject_fingerprint": "b" * 64,
        "issues": [],
    }
    convergence = compute_review_convergence(
        curr,
        _prev_review(),
        revision_evidence={
            "ok": True,
            "boundary_ok": True,
            "resolved_targets": ["FS-002"],
            "before_prose_sha256": "a" * 64,
            "after_prose_sha256": "b" * 64,
        },
    )
    assert convergence["resolved_count"] == 1
    assert convergence["all_high_critical_closed"] is True


def test_verified_evidence_for_a_different_prose_is_not_closure():
    curr = {
        "draft_id": "draft-008-bbbbbbbb",
        "draft_fingerprint": "e" * 64,
        "review_subject_fingerprint": "b" * 64,
        "issues": [],
    }
    convergence = compute_review_convergence(
        curr,
        _prev_review(),
        revision_evidence={
            "ok": True,
            "resolved_targets": ["FS-002"],
            "before_prose_sha256": "a" * 64,
            "after_prose_sha256": "9" * 64,
        },
    )
    assert convergence["resolved_count"] == 0
    assert convergence["uncertain_count"] == 1


# --------------------------------------------------------------------------- #
# R06 / R08 — convergence counters and the honest score name are persisted
# --------------------------------------------------------------------------- #


def test_metrics_carry_convergence_counters_and_defect_score():
    result = parse_review_output(
        chapter=9,
        raw={
            "issues": [
                {
                    "severity": "high",
                    "category": "continuity",
                    "description": "冲突",
                    "blocking": False,
                }
            ]
        },
    )
    metrics = result.to_metrics_dict()
    assert metrics["review_defect_score"] == 85.0
    assert metrics["overall_score"] == metrics["review_defect_score"]
    assert "defect" in metrics["score_semantics"]
    assert metrics["has_previous_review"] is False
    for key in (
        "previous_finding_count",
        "resolved_count",
        "persistent_count",
        "uncertain_count",
        "new_count",
        "finding_churn",
    ):
        assert key in metrics

    record = _build_review_metrics_record({**metrics, "resolved_count": 3, "finding_churn": 5})
    assert record.resolved_count == 3
    assert record.finding_churn == 5
    assert record.overall_score == 85.0


def test_core_mode_is_visible_in_metrics_and_never_reports_skipped_as_pass():
    result = parse_review_output(
        chapter=9,
        raw={
            "issues": [],
            "review_mode": "core",
            "dimension_results": [
                {"dimension": "setting", "conclusion": "pass"},
                {"dimension": "logic", "conclusion": "skipped", "reason": "core mode"},
            ],
        },
    )
    metrics = result.to_metrics_dict()
    assert metrics["review_mode"] == "core"
    assert metrics["skipped_dimensions"] == ["logic"]
    assert "review_mode=core" in metrics["notes"]


# --------------------------------------------------------------------------- #
# F01 — the length contract blocks only when it is explicitly hard
# --------------------------------------------------------------------------- #


def _state_only_project(tmp_path: Path, length_contract: dict | None = None) -> Path:
    root = tmp_path / "book"
    (root / ".webnovel").mkdir(parents=True, exist_ok=True)
    state: dict = {"project_info": {"title": "测试"}, "progress": {}, "entity_state": {}}
    if length_contract is not None:
        state["project_info"]["chapter_length_contract"] = length_contract
    (root / ".webnovel" / "state.json").write_text(
        json.dumps(state, ensure_ascii=False), encoding="utf-8"
    )
    return root


def test_count_hanzi_ignores_punctuation_and_latin():
    assert count_hanzi("你好，world！123") == 2


def test_default_target_is_advisory_not_blocking(tmp_path: Path):
    root = _state_only_project(tmp_path)
    report = check_chapter_length(root, 1, "字" * 1500)
    assert report["errors"] == []
    assert len(report["warnings"]) == 1
    assert report["contract"]["source"] == "default"
    assert report["contract"]["declared"] is False


def test_declared_hard_contract_blocks(tmp_path: Path):
    root = _state_only_project(tmp_path, {"min_chars": 2000, "hard": True})
    report = check_chapter_length(root, 1, "字" * 1973)
    assert len(report["errors"]) == 1
    assert report["errors"][0]["details"]["count"] == 1973


def test_declared_soft_contract_only_warns(tmp_path: Path):
    root = _state_only_project(tmp_path, {"min_chars": 2000})
    report = check_chapter_length(root, 1, "字" * 1973)
    assert report["errors"] == []
    assert len(report["warnings"]) == 1


def test_precommit_gate_reports_the_length_violation(tmp_path: Path):
    root = _state_only_project(tmp_path, {"min_chars": 2000, "hard": True})
    working = root / ".webnovel" / "tmp" / "chapter_0001_working.md"
    working.parent.mkdir(parents=True, exist_ok=True)
    working.write_text("字" * 1200 + "\n" + _changes_block(), encoding="utf-8")

    report = run_precommit_gate(root, 1)
    codes = {error["code"] for error in report["errors"]}
    assert "chapter_length_contract_violation" in codes
    assert report["details"]["chapter_length"]["count"] == 1200


def test_precommit_gate_does_not_block_on_the_default_target(tmp_path: Path):
    root = _state_only_project(tmp_path)
    working = root / ".webnovel" / "tmp" / "chapter_0001_working.md"
    working.parent.mkdir(parents=True, exist_ok=True)
    working.write_text("字" * 1200 + "\n" + _changes_block(), encoding="utf-8")

    report = run_precommit_gate(root, 1)
    codes = {error["code"] for error in report["errors"]}
    assert "chapter_length_contract_violation" not in codes


# --------------------------------------------------------------------------- #
# F02 — documented commands are executable
# --------------------------------------------------------------------------- #


def _ingest_draft_invocations():
    for path in sorted(PLUGIN_ROOT.glob("skills/*/SKILL.md")):
        text = path.read_text(encoding="utf-8")
        for match in re.finditer(r"runtime ingest-draft \\\n((?:\s+[^\n]*\\\n)*\s+[^\n]*\n)", text):
            yield path, match.group(0)


def test_every_documented_ingest_draft_passes_chapter():
    invocations = list(_ingest_draft_invocations())
    assert invocations, "no ingest-draft example found — the extraction regex drifted"
    missing = [str(path) for path, block in invocations if "--chapter" not in block]
    assert missing == []


def test_ingest_draft_cli_requires_chapter(tmp_path: Path):
    """The parser really does require it, so the docs above are not optional."""
    proc = subprocess.run(
        [
            sys.executable,
            str(PLUGIN_ROOT / "scripts" / "webnovel.py"),
            "--project-root",
            str(tmp_path),
            "runtime",
            "ingest-draft",
            "--package-fingerprint",
            "x",
            "--draft-file",
            "y",
        ],
        capture_output=True,
        text=True,
        env={
            **os.environ,
            "PYTHONPATH": os.pathsep.join(
                [
                    str(PLUGIN_ROOT / "scripts"),
                    str(PLUGIN_ROOT / "scripts" / "data_modules"),
                ]
            ),
        },
    )
    assert proc.returncode != 0
    assert "--chapter" in (proc.stderr + proc.stdout)


# --------------------------------------------------------------------------- #
# A05 — the install check cannot claim a pass it did not perform
# --------------------------------------------------------------------------- #


def test_install_check_skips_loudly_when_claude_is_absent(tmp_path: Path):
    """`--check` used to print WARN and `exit 0`, so callers read "skipped" as "verified"."""
    script = REPO_ROOT / "bin" / "install-plugin.sh"

    # A PATH with the shell utilities the script needs up to the `claude` probe, but
    # deliberately without `claude` itself.
    stub_bin = tmp_path / "bin"
    stub_bin.mkdir()
    for tool in ("dirname", "bash", "sh"):
        resolved = shutil.which(tool)
        if resolved:
            (stub_bin / tool).symlink_to(resolved)

    proc = subprocess.run(
        ["/bin/bash", str(script), "--check"],
        capture_output=True,
        text=True,
        env={"PATH": str(stub_bin), "HOME": str(Path.home())},
    )
    assert proc.returncode == 3
    assert "SKIPPED" in (proc.stderr + proc.stdout)


def test_install_check_documents_its_exit_codes():
    text = (REPO_ROOT / "bin" / "install-plugin.sh").read_text(encoding="utf-8")
    assert "--digest" in text
    assert "exit 3" in text or "3 = SKIPPED" in text


# --------------------------------------------------------------------------- #
# A03 — legacy/unlinked history is not presented as a current obligation
# --------------------------------------------------------------------------- #


def test_urgent_loop_fallback_excludes_non_obligation_rows(tmp_path: Path):
    from data_modules.config import DataModulesConfig
    from data_modules.context_manager import ContextManager

    root = _state_only_project(tmp_path)
    manager = ContextManager(DataModulesConfig.from_project_root(root))

    state = {
        "plot_threads": {
            "foreshadowing": [
                {"content": "真实未回收伏笔", "status": "active"},
                {"content": "旧数据无法关联 loop", "status": "legacy_unlinked"},
                {"content": "已经回收的伏笔", "status": "resolved"},
            ]
        }
    }
    loops = manager._load_urgent_loops(state)
    assert [item["content"] for item in loops] == ["真实未回收伏笔"]


# --------------------------------------------------------------------------- #
# A02 — the projection records which mutable external files it read
# --------------------------------------------------------------------------- #


def test_state_projection_reports_legacy_row_counts(tmp_path: Path):
    from data_modules.state_projection_writer import StateProjectionWriter

    root = _state_only_project(tmp_path)
    writer = StateProjectionWriter(root)
    state = {
        "plot_threads": {
            "foreshadowing": [
                {"content": "无法关联的旧数据", "status": "active"},
            ]
        }
    }
    commit_payload = {
        "meta": {"chapter": 3, "status": "accepted"},
        "extraction_result": {
            "accepted_events": [
                {
                    "event_id": "evt-loop-3",
                    "event_type": "open_loop_created",
                    "chapter": 3,
                    "subject": "谜团",
                    "payload": {"description": "新埋的伏笔"},
                }
            ]
        },
    }
    changed, report = writer._apply_foreshadowing(state, 3, commit_payload)
    assert changed == 1
    assert report["legacy_unlinked_rows"] == 1
    assert report["projected_rows"] >= 1
    assert report["active_rows"] >= 1


# --------------------------------------------------------------------------- #
# A12 — one authoritative copy of each shared CLI invocation
# --------------------------------------------------------------------------- #

CANONICAL_REFERENCE = (
    PLUGIN_ROOT / "references" / "draft-review-lifecycle.md"
)

# The three skills that carry the same draft->review->commit lifecycle. `webnovel-review`
# uses its own range/padding convention (`{end}` + `printf "%04d"`), so it is deliberately
# out of scope here.
_LIFECYCLE_SKILLS = ("webnovel-write", "webnovel-fast-write", "webnovel-revise")

# (label, regex matching the invocation block in a SKILL.md)
_SHARED_INVOCATIONS = {
    label: rf"{re.escape(label)} \\\n(?:\s+--[^\n]*\n)+"
    for label in (
        "runtime ingest-draft",
        "runtime reviewer-context",
        "review-pipeline",
        "runtime commit",
        "runtime publish-draft",
    )
}


def _normalize_invocation(block: str) -> str:
    """Compare invocations by meaning, not by indentation or placeholder spelling."""
    lines = [line.strip().rstrip("\\").strip() for line in block.splitlines()]
    text = " ".join(line for line in lines if line)
    text = re.sub(r"\$\{[^}]*\}", "{X}", text)
    return re.sub(r"\{[^}]*\}", "{X}", text)


def test_canonical_cli_invocations_are_identical_across_skills():
    """F02/F03 came from the same command being written out in several skills and drifting.

    The reference file is the one place to edit; this test fails the moment an inline copy
    disagrees with it, instead of letting the drift reach a real run.
    """
    reference = CANONICAL_REFERENCE.read_text(encoding="utf-8")
    skills = [PLUGIN_ROOT / "skills" / name / "SKILL.md" for name in _LIFECYCLE_SKILLS]
    assert all(skill.is_file() for skill in skills)

    problems: list[str] = []
    for label, pattern in _SHARED_INVOCATIONS.items():
        canonical_matches = re.findall(pattern, reference)
        if not canonical_matches:
            problems.append(f"reference file has no canonical {label!r} invocation")
            continue
        canonical = _normalize_invocation(canonical_matches[0])
        for skill in skills:
            text = skill.read_text(encoding="utf-8")
            for block in re.findall(pattern, text):
                if _normalize_invocation(block) != canonical:
                    problems.append(
                        f"{skill.relative_to(REPO_ROOT)}: {label!r} differs from the "
                        f"canonical copy in {CANONICAL_REFERENCE.name}"
                    )
    assert problems == [], "\n".join(problems)


def test_reference_documents_the_review_validity_rule():
    text = CANONICAL_REFERENCE.read_text(encoding="utf-8")
    assert "review_subject_fingerprint" in text
    assert "不需要重跑 Reviewer" in text or "否" in text


# --------------------------------------------------------------------------- #
# review-pipeline end to end: convergence is recorded, not silently skipped
# --------------------------------------------------------------------------- #


def test_review_pipeline_records_convergence_and_writes_authoritative_state(tmp_path: Path):
    """R06/D03: the counters must be persisted, and the authority writes must happen.

    The evidence file lives in `.webnovel/tmp/` (what the Skill writes) while the previous
    review lives in the runtime dir — looking for evidence only in the runtime dir meant a
    genuinely fixed finding still came back as `uncertain`.
    """
    from review_pipeline import build_review_artifacts

    chapter = 3
    old_text = _draft_text("plot_a")
    _write_active_draft(tmp_path, chapter, old_text, "draft-003-aaaaaaaa")

    runtime_dir = tmp_path / ".webnovel" / "runtime" / f"chapter_{chapter:03d}"
    runtime_dir.mkdir(parents=True, exist_ok=True)
    (runtime_dir / "last_review.json").write_text(
        json.dumps(
            {
                "draft_id": "draft-003-aaaaaaaa",
                "draft_fingerprint": hashlib.sha256(old_text.encode()).hexdigest(),
                "review_subject_fingerprint": prose_subject_sha256(old_text),
                "issues": [
                    {
                        "issue_id": "FS-002",
                        "category": "continuity",
                        "severity": "high",
                        "description": "玉佩来历与前章冲突",
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    new_text = old_text.replace("他听见深处传来脚步声。", "他听见深处传来沉重的脚步声。")
    _write_active_draft(tmp_path, chapter, new_text, "draft-003-bbbbbbbb")

    tmp_dir = tmp_path / ".webnovel" / "tmp"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    (tmp_dir / "verify_minimal_edit.json").write_text(
        json.dumps(
            {
                "ok": True,
                "boundary_ok": True,
                "resolved_targets": ["FS-002"],
                "before_prose_sha256": prose_subject_sha256(old_text),
                "after_prose_sha256": prose_subject_sha256(new_text),
            }
        ),
        encoding="utf-8",
    )

    review_path = tmp_dir / "review_results.json"
    review_path.write_text(
        json.dumps(
            {
                "issues": [],
                "draft_id": "draft-003-bbbbbbbb",
                "draft_fingerprint": hashlib.sha256(new_text.encode()).hexdigest(),
                "review_subject_fingerprint": prose_subject_sha256(new_text),
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    payload = build_review_artifacts(tmp_path, chapter, review_path)
    convergence = payload["review_result"]["convergence"]
    assert convergence["has_previous_review"] is True
    assert convergence["revision_evidence_found"] is True
    assert convergence["revision_evidence_path"].endswith("verify_minimal_edit.json")
    assert convergence["resolved_count"] == 1

    # metrics carry the counters through to the persisted record
    record = _build_review_metrics_record(payload["metrics"])
    assert record.resolved_count == 1

    # authoritative writes really happened
    assert (runtime_dir / "last_review.json").is_file()
    assert (runtime_dir / "draft_reviews" / "draft-003-bbbbbbbb.review.json").is_file()
