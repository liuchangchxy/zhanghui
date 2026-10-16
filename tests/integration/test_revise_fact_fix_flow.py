#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""End-to-end governed fact correction (independent-acceptance follow-up, issue 1).

The scenario the review asked for, run through the **real CLI**:

    draft says  记录本上共有七行。
    Reviewer says it must be 八行
    the formal revise flow changes exactly that

and the flow must demonstrate, in order:

1. only the necessary span changed (verified boundary, not a chapter rewrite);
2. the change is *not* disguised as `STYLE_ONLY_SAFE` — it is a fact change and is labelled
   as one;
3. a legal fact correction is not rolled back without reason;
4. a new Draft Identity is produced;
5. the previous Reviewer result is invalidated (it cannot be reused for the new draft);
6. the new draft can enter re-review;
7. once that review passes, the formal commit contract still holds — and the *old* review is
   rejected outright with `REVIEW_DRAFT_MISMATCH`.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[2] / ".claude" / "plugins" / "zhanghui" / "scripts"
for path in (SCRIPTS, SCRIPTS.parent):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))


SEVEN_LINE = "记录本上共有七行。"
EIGHT_LINE = "记录本上共有八行。"

OUTLINE = """# 第一卷 潮痕

### 第1章：停用的潮位站
- 目标：按流程完成旧潮位站的资产清点并归档
- 阻力：老周以流程为由拖延开门
- 代价：为找清点依据翻开了不属于本次清点范围的记录本
- 必须覆盖节点：清点、命中尾页
- 本章禁区：不得引入超自然力量
- 章末未闭合问题：为什么记录本会少一行？
"""

PROSE = f"""许知远推开车门，走到登记台前，把清点单摊平。
{SEVEN_LINE}
他随手把这一页拍了下来。

<chapter_changes>
{{
  "character_state_changes": [
    {{"character_id": "xu_zhiyuan", "change_type": "status_update", "importance": "normal", "details": "核对记录本行数"}}
  ],
  "new_plot_points": [],
  "foreshadowing_actions": [],
  "location_state_changes": [],
  "faction_state_changes": [],
  "time_progression": null,
  "item_transfers": [],
  "unresolved_questions": []
}}
</chapter_changes>"""

_INIT_DIRS = (".webnovel", ".webnovel/backups", ".webnovel/archive", ".webnovel/summaries",
              "设定集", "大纲", "正文", "审查报告", ".webnovel/tmp")
_INIT_FILES = ("设定集/世界观.md", "设定集/力量体系.md", "设定集/主角卡.md", "设定集/反派设计.md",
               "大纲/总纲.md", ".env.example")


# --------------------------------------------------------------------------- #
# CLI harness
# --------------------------------------------------------------------------- #


class CliResult:
    def __init__(self, proc: subprocess.CompletedProcess):
        self.returncode = proc.returncode
        self.stdout = proc.stdout
        self.stderr = proc.stderr

    def json(self) -> dict:
        return json.loads(self.stdout)


def _run(root: Path, *argv: str) -> CliResult:
    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join(
        [str(SCRIPTS), str(SCRIPTS.parent), env.get("PYTHONPATH", "")]
    ).strip(os.pathsep)
    proc = subprocess.run(
        [sys.executable, "-X", "utf8", str(SCRIPTS / "webnovel.py"), "--project-root", str(root), *argv],
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=env,
    )
    return CliResult(proc)


def _project(tmp_path: Path) -> Path:
    for rel in _INIT_DIRS:
        (tmp_path / rel).mkdir(parents=True, exist_ok=True)
    for rel in _INIT_FILES:
        (tmp_path / rel).write_text(f"# {rel}\n", encoding="utf-8")
    (tmp_path / "大纲" / "第1卷-详细大纲.md").write_text(OUTLINE, encoding="utf-8")
    for name in ("第1卷-节拍表.md", "第1卷-时间线.md"):
        (tmp_path / "大纲" / name).write_text("# 内容\n", encoding="utf-8")
    state = {
        "project_info": {"title": "记录本", "genre": "悬疑"},
        "progress": {"current_volume": 1, "current_chapter": 0,
                     "volumes_planned": [{"volume": 1, "chapters_range": "1-12", "title": "潮痕"}]},
        "protagonist_state": {"name": "许知远"},
        "chapter_meta": {"1": {
            "beat_position": "Opening Image", "hook_type": "悬念式",
            "scene_goal": "完成清点", "scene_conflict": "老周拖延", "scene_setback": "越界翻看",
            "scene_resolution": "命中尾页", "sequel_reaction": "起疑",
            "sequel_dilemma": "上报 vs 自查", "sequel_decision": "先自查",
        }},
        "story_craft": {"timed_locks": [], "foreshadow_chain": [], "timed_locks_note": ""},
        "entity_state": {"xu_zhiyuan": {"name": "许知远", "identity": "档案管理员"}},
        "world_settings": {
            "characters": [{"name": "许知远", "id": "xu_zhiyuan"}],
            "locations": [], "items": [],
        },
    }
    (tmp_path / ".webnovel" / "state.json").write_text(
        json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (tmp_path / ".story-system").mkdir(parents=True, exist_ok=True)
    (tmp_path / ".story-system" / "MASTER_SETTING.json").write_text(
        json.dumps({"entities": [{"name": "许知远", "id": "xu_zhiyuan", "type": "角色"}]}, ensure_ascii=False),
        encoding="utf-8",
    )
    return tmp_path


def _ingest(root: Path, prose: str) -> dict:
    from data_modules.chapter_runtime import ChapterRuntime

    runtime = ChapterRuntime(root)
    prep = runtime.prepare(chapter=1, with_package=True)
    assert prep.ok is True, prep.blockers
    pkg = runtime.attach_creative_brief(chapter=1, creative_brief="## 一、基调\n冷峻克制。\n")
    result = runtime.ingest_draft(chapter=1, prose=prose, package_fingerprint=pkg.package_fingerprint)
    assert result.ok is True, result.error
    return {"draft_id": result.draft_id, "draft_fingerprint": result.draft_fingerprint}


def _review_finding(draft: dict, *, paragraph: int) -> dict:
    """Reviewer output that declares which draft it reviewed (the pipeline stamps this too)."""
    return {
        "chapter": 1,
        "draft_id": draft["draft_id"],
        "draft_fingerprint": draft["draft_fingerprint"],
        "summary": "记录本行数与后续叙述不一致。",
        "issues": [
            {
                "severity": "high",
                "category": "continuity",
                "location": f"第{paragraph}段",
                "description": "记录本的行数与前文台账对不上：台账记的是八行。",
                "fix_hint": "把这一段的「七行」改成「八行」，与本段以外的内容保持一致。",
                "blocking": True,
            }
        ],
    }


def _commit_artifacts(prose: str) -> dict:
    from data_modules.reconciliation import reconcile_changes, split_chapter_and_changes

    _, proposal = split_chapter_and_changes(prose)
    extraction_result = {
        "chapter_meta": {},
        "accepted_events": [
            {"event_type": "character_state_changed", "subject": "xu_zhiyuan",
             "summary": "核对记录本行数", "payload": {"status": "核对行数"}}
        ],
        "state_deltas": [],
        "entity_deltas": [{"entity_id": "xu_zhiyuan", "current": {"identity": "档案管理员"}}],
    }
    return {
        "review_result": {"chapter": 1, "blocking_count": 0, "must_check_results": [], "blocking_rule_results": []},
        "fulfillment_result": {"planned_nodes": [], "covered_nodes": [], "missed_nodes": [], "extra_nodes": []},
        "disambiguation_result": {"pending": []},
        "extraction_result": extraction_result,
        "reconciliation_result": reconcile_changes(proposal, extraction_result, chapter_text=prose),
    }


# --------------------------------------------------------------------------- #
# the mandated scenario
# --------------------------------------------------------------------------- #


def test_fact_correction_runs_through_the_formal_revise_flow(tmp_path: Path):
    root = _project(tmp_path)
    tmp = root / ".webnovel" / "tmp"

    # --- draft A: the prose says 七行 -------------------------------------
    draft_a = _ingest(root, PROSE)
    working = tmp / "chapter_0001_working.md"
    working.write_text(PROSE, encoding="utf-8")

    paragraph = next(
        i for i, line in enumerate([l for l in PROSE.splitlines() if l.strip()], 1)
        if SEVEN_LINE in line
    )

    review_a = tmp / "review_results.json"
    review_a.write_text(json.dumps(_review_finding(draft_a, paragraph=paragraph), ensure_ascii=False), encoding="utf-8")

    # --- revise plan: bound to draft A ------------------------------------
    plan_path = tmp / "revision_plan_0001.json"
    planned = _run(
        root, "revise", "plan",
        "--chapter", "1",
        "--draft-file", str(working),
        "--review-result", str(review_a),
        "--output", str(plan_path),
    )
    assert planned.returncode == 0, planned.stderr
    plan = json.loads(plan_path.read_text(encoding="utf-8"))

    assert plan["draft_sha256"] == draft_a["draft_fingerprint"]
    assert plan["review_binding"]["verified"] is True
    assert plan["review_binding"]["mode"] == "declared_fingerprint"
    local_fact = [t for t in plan["targets"] if t["kind"] == "LOCAL_FACT"]
    assert local_fact, plan["summary"]

    # --- host model rewrites exactly the offending sentence ---------------
    target = local_fact[0]
    assert SEVEN_LINE in target["before_text"]
    edits_path = tmp / "revision_edits_0001.json"
    edits_path.write_text(
        json.dumps(
            [{"target_id": target["issue_id"], "new_text": target["before_text"].replace(SEVEN_LINE, EIGHT_LINE)}],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    candidate = tmp / "step4_candidate_0001.md"
    applied = _run(
        root, "revise", "apply",
        "--draft-file", str(working),
        "--plan", str(plan_path),
        "--edits", str(edits_path),
        "--output", str(candidate),
    )
    assert applied.returncode == 0, applied.stderr
    assert applied.json()["changed"] is True

    # (1) only the necessary span changed
    verified = _run(
        root, "revise", "verify",
        "--before-file", str(working),
        "--after-file", str(candidate),
        "--plan", str(plan_path),
    )
    assert verified.returncode == 0, verified.stdout + verified.stderr
    verification = verified.json()
    assert verification["boundary_ok"] is True
    assert verification["out_of_scope_changes"] == []
    assert verification["before_sha256_matches_plan"] is True

    before_text = working.read_text(encoding="utf-8")
    after_text = candidate.read_text(encoding="utf-8")
    assert after_text.replace(EIGHT_LINE, SEVEN_LINE) == before_text, "只有那一处句段发生变化"

    # --- (2)/(3) the gate: declared fact correction, neither disguised as style
    #     nor rolled back for no reason ------------------------------------
    validated = _run(
        root, "prose", "validate",
        "--before-file", str(working),
        "--after-file", str(candidate),
        "--chapter", "1",
        "--revision-plan", str(plan_path),
    )
    assert validated.returncode == 0, validated.stdout + validated.stderr
    gate = validated.json()

    assert gate["status"] == "PENDING_REREVIEW"
    assert gate["semantic_outcome"] == "FACT_FIX_DECLARED"
    assert gate["semantic_outcome"] != "STYLE_ONLY_SAFE"  # 不伪装成风格修改
    assert gate["ok"] is False                            # 也绝不等于「已通过审查」
    assert gate["requires_rereview"] is True
    assert gate["rollback_reason"] is None                # 合法事实纠错不被无理由回滚
    assert any("ingest-draft" in a for a in gate["required_actions"])
    assert any("reviewer" in a for a in gate["required_actions"])

    # an out-of-scope edit declared as a fact fix is still refused
    overreach = tmp / "overreach_0001.md"
    overreach.write_text(after_text + "\n他把整本记录本重新抄了一遍。\n", encoding="utf-8")
    rejected = _run(
        root, "prose", "validate",
        "--before-file", str(working),
        "--after-file", str(overreach),
        "--chapter", "1",
        "--revision-plan", str(plan_path),
    )
    assert rejected.returncode == 1
    assert rejected.json()["status"] == "ROLLEDBACK"
    assert "越出 LOCAL_FACT 区间" in rejected.json()["rollback_reason"]

    # --- (4) adopt the correction and produce a NEW draft identity --------
    working.write_text(after_text, encoding="utf-8")
    draft_b = _ingest(root, after_text)
    assert draft_b["draft_id"] != draft_a["draft_id"]
    assert draft_b["draft_fingerprint"] != draft_a["draft_fingerprint"]

    # --- (5) the previous review is invalidated ---------------------------
    stale_plan = tmp / "stale_plan.json"
    refused = _run(
        root, "revise", "plan",
        "--chapter", "1",
        "--draft-file", str(candidate),   # candidate == new draft content
        "--review-result", str(review_a),  # review of draft A
        "--output", str(stale_plan),
    )
    assert refused.returncode == 4
    assert "draft_fingerprint" in refused.stderr or "草稿" in refused.stderr
    assert not stale_plan.exists()

    # applying the old plan to the new draft is refused too
    applied_stale = _run(
        root, "revise", "apply",
        "--draft-file", str(candidate),
        "--plan", str(plan_path),
        "--edits", str(edits_path),
        "--output", str(tmp / "should_not_exist.md"),
    )
    assert applied_stale.returncode == 4
    assert "草稿" in applied_stale.stderr
    assert not (tmp / "should_not_exist.md").exists()

    # --- (6) the new draft enters re-review -------------------------------
    # the re-review of the corrected draft finds nothing left to fix, which is what makes the
    # chapter committable again
    review_b = tmp / "review_results_b.json"
    clean_review = _review_finding(draft_b, paragraph=paragraph)
    clean_review["summary"] = "行数已与本段以外的叙述一致，无遗留问题。"
    clean_review["issues"] = []
    review_b.write_text(json.dumps(clean_review, ensure_ascii=False), encoding="utf-8")
    pipeline = _run(
        root, "review-pipeline",
        "--chapter", "1",
        "--review-results", str(review_b),
        "--save-metrics",
    )
    assert pipeline.returncode == 0, pipeline.stderr
    stamped = json.loads(review_b.read_text(encoding="utf-8"))
    assert stamped["draft_id"] == draft_b["draft_id"]
    assert stamped["draft_fingerprint"] == draft_b["draft_fingerprint"]

    # --- (7) the formal commit contract still holds -----------------------
    from data_modules.chapter_runtime import ChapterRuntime

    runtime = ChapterRuntime(root)
    artifacts = _commit_artifacts(after_text)
    artifacts["review_result"] = stamped

    committed = runtime.commit(chapter=1, draft_id=draft_b["draft_id"], **artifacts)
    assert committed.ok is True, f"{committed.error_code}: {committed.error}"
    assert committed.chapter_outcome == "accepted"
    # the accepted commit is bound to the corrected prose, not to the pre-fix version
    assert committed.to_dict()["commit_payload"]["review_result"]["draft_fingerprint"] == (
        draft_b["draft_fingerprint"]
    )
    assert EIGHT_LINE in after_text and SEVEN_LINE not in after_text


def test_unbound_review_is_refused_unless_explicitly_allowed(tmp_path: Path):
    """旧审查不得静默用于新草稿：未声明草稿身份的审查默认拒绝。"""
    root = _project(tmp_path)
    tmp = root / ".webnovel" / "tmp"
    _ingest(root, PROSE)
    working = tmp / "chapter_0001_working.md"
    working.write_text(PROSE, encoding="utf-8")

    unbound = tmp / "unbound_review.json"
    payload = _review_finding({"draft_id": "x", "draft_fingerprint": "y"}, paragraph=2)
    payload.pop("draft_id")
    payload.pop("draft_fingerprint")
    unbound.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    refused = _run(
        root, "revise", "plan", "--chapter", "1",
        "--draft-file", str(working), "--review-result", str(unbound),
        "--output", str(tmp / "plan.json"),
    )
    assert refused.returncode == 4
    assert "没有声明" in refused.stderr

    allowed = _run(
        root, "revise", "plan", "--chapter", "1",
        "--draft-file", str(working), "--review-result", str(unbound),
        "--allow-unbound-review", "--output", str(tmp / "plan.json"),
    )
    assert allowed.returncode == 0, allowed.stderr
    plan = json.loads((tmp / "plan.json").read_text(encoding="utf-8"))
    assert plan["review_binding"]["verified"] is False
    assert plan["review_binding"]["mode"] == "unbound"


def test_plan_refuses_when_the_working_draft_has_unregistered_changes(tmp_path: Path):
    """工作草稿在 ingest 之后被改动 → 计划必须拒绝，而不是照旧定位。"""
    root = _project(tmp_path)
    tmp = root / ".webnovel" / "tmp"
    draft_a = _ingest(root, PROSE)
    working = tmp / "chapter_0001_working.md"
    working.write_text(PROSE + "\n他又补了一句没有登记过的话。\n", encoding="utf-8")

    review = tmp / "review_results.json"
    review.write_text(json.dumps(_review_finding(draft_a, paragraph=2), ensure_ascii=False), encoding="utf-8")

    refused = _run(
        root, "revise", "plan", "--chapter", "1",
        "--draft-file", str(working), "--review-result", str(review),
        "--output", str(tmp / "plan.json"),
    )
    assert refused.returncode == 4
    assert "ingest" in refused.stderr
    assert not (tmp / "plan.json").exists()


def test_commit_side_rejects_a_review_bound_to_another_draft(tmp_path: Path):
    """Canon 保护不削弱：声明了别的草稿身份的审查不能进提交。"""
    root = _project(tmp_path)
    tmp = root / ".webnovel" / "tmp"
    draft_a = _ingest(root, PROSE)

    from data_modules.chapter_runtime import ChapterRuntime

    runtime = ChapterRuntime(root)
    artifacts = _commit_artifacts(PROSE)
    artifacts["review_result"] = _review_finding(draft_a, paragraph=2)
    artifacts["review_result"]["draft_fingerprint"] = "0" * 64  # 与本次提交的草稿不一致

    result = runtime.commit(chapter=1, draft_id=draft_a["draft_id"], **artifacts)
    assert result.ok is False
    assert result.error_code == "REVIEW_DRAFT_MISMATCH"
    assert not (root / ".story-system" / "commits" / "chapter_001.commit.json").is_file()
