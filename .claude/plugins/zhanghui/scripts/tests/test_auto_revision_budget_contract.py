"""Assert the Step-4 automatic revision budget is counted, enforced, and wired up.

Why this exists (2026-10-21, chapter-4 Full Write):

`skills/webnovel-write/SKILL.md` declares the budget as "初审 + 至多一次定向修订 + 复审",
i.e. at most 2 review rounds, and calls it a hard boundary. It was only prose. In the
chapter-4 run the main model's own reasoning read "We've exceeded the auto budget ...
But the medium issue about the first test not being verifiable is worth a tiny fix",
then ran a second and third revision round anyway — 4 reviewer calls, 1,090 s, of which
the 2 out-of-budget rounds were 730.9 s (67%). Every round reported `blocking=false`, and
the chapter was committed `ALLOW_WITH_ADVISORY` with `postcommit ok=true`, so the extra
rounds changed no admission decision.

Two defects let that happen, and these tests pin both:

1. Nothing counted rounds. `runtime reviewer-context` now counts them when the automatic
   write loop passes `--enforce-auto-budget`, and refuses round 3+ with exit code 2.
   The counting source is the command itself, not `draft_reviews/` — in that run
   `review-pipeline` was skipped for 2 of the 4 rounds, so a derived count would have
   under-counted exactly when the budget was being exceeded.

2. The closure evidence that would have shown "already resolved, stop" was written where
   `review_pipeline` never looks. The skills wrote
   `.webnovel/runtime/chapter_{chapter_padded}/verify_minimal_edit.json` (four-digit),
   but `review_pipeline.py` reads `.webnovel/tmp/verify_minimal_edit.json` and
   `.webnovel/runtime/chapter_{chapter:03d}/verify_minimal_edit.json`. All five fixed
   findings were recorded `uncertain` / `evidence_not_verified`.
"""
import re
import sys
from pathlib import Path

import pytest

PLUGIN_ROOT = Path(__file__).resolve().parents[2]  # tests/ → scripts/ → plugin/
sys.path.insert(0, str(PLUGIN_ROOT / "scripts"))
sys.path.insert(0, str(PLUGIN_ROOT / "scripts" / "data_modules"))

from data_modules.chapter_runtime import (  # noqa: E402
    AUTO_REVISION_MAX_ROUNDS,
    ChapterRuntime,
)

# Skills that drive the *automatic* write loop and must therefore enforce the budget.
AUTO_LOOP_SKILLS = ("webnovel-write", "webnovel-fast-write")


def _read(rel: str) -> str:
    return (PLUGIN_ROOT / rel).read_text(encoding="utf-8")


@pytest.fixture()
def project(tmp_path: Path) -> Path:
    root = tmp_path / "book"
    (root / ".webnovel").mkdir(parents=True, exist_ok=True)
    (root / ".webnovel" / "state.json").write_text('{"progress": {"current_chapter": 1}}', encoding="utf-8")
    return root


def _budget(project: Path, chapter: int, enforce: bool) -> dict:
    return ChapterRuntime(project)._auto_revision_budget(chapter, enforce=enforce)


def test_budget_allows_initial_review_and_one_rereview(project: Path) -> None:
    """初审 (round 1) + 复审 (round 2) are both within budget."""
    assert AUTO_REVISION_MAX_ROUNDS == 2

    first = _budget(project, 4, enforce=True)
    assert first["exhausted"] is False
    assert first["rounds_used"] == 1
    assert first["rounds_remaining"] == 1

    second = _budget(project, 4, enforce=True)
    assert second["exhausted"] is False
    assert second["rounds_used"] == 2
    assert second["rounds_remaining"] == 0


def test_budget_refuses_third_round(project: Path) -> None:
    """The chapter-4 failure mode: a third review round must be refused, not served."""
    _budget(project, 4, enforce=True)
    _budget(project, 4, enforce=True)

    third = _budget(project, 4, enforce=True)
    assert third["exhausted"] is True
    assert third["rounds_used"] == AUTO_REVISION_MAX_ROUNDS, "拒绝时不得继续累加计数"
    assert third["round_being_requested"] == 3

    fourth = _budget(project, 4, enforce=True)
    assert fourth["exhausted"] is True, "被拒绝的调用不得把预算越推越远"


def test_budget_refusal_raises_before_building_context(project: Path) -> None:
    """`get_reviewer_context` must refuse before paying for the governed context.

    The check sits at the top of the method precisely so an over-budget call cannot
    produce a context file that the reviewer would then consume.
    """
    from data_modules.chapter_runtime import AutoRevisionBudgetExhausted

    runtime = ChapterRuntime(project)
    runtime._auto_revision_budget(4, enforce=True)
    runtime._auto_revision_budget(4, enforce=True)

    with pytest.raises(AutoRevisionBudgetExhausted) as excinfo:
        runtime.get_reviewer_context(chapter=4, enforce_auto_budget=True)

    assert excinfo.value.budget["exhausted"] is True
    assert excinfo.value.budget["max_rounds"] == AUTO_REVISION_MAX_ROUNDS
    assert "预算" in str(excinfo.value)


def test_budget_reports_remaining_rounds_within_budget(project: Path) -> None:
    """A compliant round still reports the budget, so the orchestrator can see it."""
    runtime = ChapterRuntime(project)
    budget = runtime._auto_revision_budget(4, enforce=True)
    assert budget["rounds_used"] == 1
    assert budget["rounds_remaining"] == AUTO_REVISION_MAX_ROUNDS - 1
    assert budget["exhausted"] is False


def test_human_driven_review_does_not_consume_auto_budget(project: Path) -> None:
    """/webnovel-review and /webnovel-revise are human actions, not the auto loop."""
    for _ in range(5):
        assert _budget(project, 4, enforce=False)["rounds_used"] == 0

    assert _budget(project, 4, enforce=True)["rounds_used"] == 1


def test_budget_is_per_chapter(project: Path) -> None:
    _budget(project, 4, enforce=True)
    _budget(project, 4, enforce=True)
    assert _budget(project, 4, enforce=True)["exhausted"] is True
    assert _budget(project, 5, enforce=True)["exhausted"] is False


@pytest.mark.parametrize("skill", AUTO_LOOP_SKILLS)
def test_auto_loop_skills_enforce_the_budget(skill: str) -> None:
    """A prose-only budget was demonstrably not enough; the auto loop must opt in."""
    text = _read(f"skills/{skill}/SKILL.md")
    assert "runtime reviewer-context" in text, f"{skill} 不再拉取审查上下文？"
    assert "--enforce-auto-budget" in text, (
        f"skills/{skill}/SKILL.md 的 reviewer-context 调用没带 --enforce-auto-budget；"
        f"自动写章流程会再次跑出预算外的审查轮次。"
    )
    assert "--allow-over-budget" in text, (
        f"skills/{skill}/SKILL.md 没有说明越界出口（hard gate 阻断 / 人工恢复用 --allow-over-budget）。"
    )


def test_human_review_skills_do_not_enforce_the_budget() -> None:
    """The human-driven skills must stay repeatable — enforcing there would break them."""
    for skill in ("webnovel-review", "webnovel-revise"):
        text = _read(f"skills/{skill}/SKILL.md")
        assert "--enforce-auto-budget" not in text, (
            f"skills/{skill}/SKILL.md 是人工触发路径，不得按自动修订预算计数。"
        )


def test_closure_evidence_is_written_where_review_pipeline_reads_it() -> None:
    """`revise verify --output` must land in a path `review_pipeline` actually reads.

    `review_pipeline.py` builds its runtime dir as `chapter_{chapter:03d}`, while the
    skills used `chapter_padded` (four digits). The evidence was therefore never found.
    """
    pipeline = _read("scripts/review_pipeline.py")
    runtime_dir_expr = re.search(r'runtime_dir = project_root / "\.webnovel" / "runtime" / f"([^"]+)"', pipeline)
    assert runtime_dir_expr, "review_pipeline.py 的 runtime_dir 构造方式变了，请同步本测试"
    assert "03d" in runtime_dir_expr.group(1), (
        "review_pipeline 的 runtime 目录不再是三位章号；SKILL 的路径约定需同步。"
    )

    offenders: list[str] = []
    for skill_md in sorted((PLUGIN_ROOT / "skills").glob("*/SKILL.md")):
        for match in re.finditer(r"--output\s+\"\$\{PROJECT_ROOT\}/(\S*verify_minimal_edit\.json)\"", skill_md.read_text(encoding="utf-8")):
            target = match.group(1)
            reads_tmp = target == ".webnovel/tmp/verify_minimal_edit.json"
            reads_runtime = target.startswith(".webnovel/runtime/chapter_") and "{chapter_padded}" not in target
            if not (reads_tmp or reads_runtime):
                offenders.append(f"{skill_md.parent.name}: {target}")
    assert not offenders, (
        "这些 `revise verify --output` 落到了 review-pipeline 不读的位置，"
        "已修好的问题会被记成 uncertain：\n  " + "\n  ".join(offenders)
    )


def test_skills_do_not_build_runtime_dirs_from_chapter_padded() -> None:
    """`chapter_padded` is four digits and only names `.webnovel/tmp/` artifacts."""
    offenders: list[str] = []
    for skill_md in sorted((PLUGIN_ROOT / "skills").glob("*/SKILL.md")):
        text = skill_md.read_text(encoding="utf-8")
        for match in re.finditer(r"\.webnovel/runtime/chapter_\{(\w+)\}", text):
            if match.group(1) == "chapter_padded":
                offenders.append(f"{skill_md.parent.name}: {match.group(0)}")
    assert not offenders, (
        "Runtime 目录是 `chapter_{chapter:03d}`（三位章号），不能用四位 `chapter_padded` 拼：\n  "
        + "\n  ".join(offenders)
    )
