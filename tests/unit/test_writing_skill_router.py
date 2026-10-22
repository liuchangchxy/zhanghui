#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Writing Skill Router regressions.

The router is an AI step, so these tests cover the deterministic contract around it:
discovery is a directory scan (hot-plug), the selection validator refuses anything that
would leak theory or exceed the per-chapter budget, and the Writer prompt carries only
the translated chapter guidance.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from data_modules.chapter_runtime import ChapterRuntime
from data_modules.writing_skill_registry import (
    build_router_catalog,
    build_router_input,
    discover_writing_skills,
    list_with_diagnostics,
    load_skill_file,
    render_writer_skills,
    selection_fingerprint,
    validate_selection,
)


def _write_skill(root: Path, skill_id: str, *, guidance: str = "让这一场的阻力真正挡住主角。", **meta) -> Path:
    fields = {
        "id": skill_id,
        "name": meta.pop("name", skill_id),
        "purpose": meta.pop("purpose", "解决一个具体创作问题。"),
        "applies_when": meta.pop("applies_when", ["本章需要它"]),
        "avoid_when": meta.pop("avoid_when", ["本章不需要它"]),
    }
    fields.update(meta)
    lines = ["---"]
    for key, value in fields.items():
        if isinstance(value, list):
            lines.append(f"{key}:")
            lines.extend(f"  - {item}" for item in value)
        else:
            lines.append(f"{key}: {value}")
    lines.extend(["---", "", "## 方法", "", guidance, "", "## 正例", "", "短正例。", "", "## 反例", "", "短反例。", ""])
    path = root / skill_id / "SKILL.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def _base_project(tmp_path: Path) -> Path:
    root = tmp_path / "book"
    (root / ".webnovel").mkdir(parents=True, exist_ok=True)
    (root / ".story-system").mkdir(parents=True, exist_ok=True)
    (root / "大纲").mkdir(parents=True, exist_ok=True)
    state = {
        "project_info": {"title": "海港旧信", "genre": "悬疑", "target_readers": "悬疑读者"},
        "progress": {"current_volume": 1, "current_chapter": 1},
        "protagonist_state": {"name": "许知远", "entity_id": "xu_zhiyuan"},
        "entity_state": {"xu_zhiyuan": {"location": {"current": "旧潮位站"}}},
        "chapter_meta": {},
    }
    (root / ".webnovel" / "state.json").write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")
    (root / ".story-system" / "anti_patterns.json").write_text("[]", encoding="utf-8")
    (root / ".story-system" / "MASTER_SETTING.json").write_text(
        json.dumps(
            {
                "meta": {"schema_version": "story-system/v1", "contract_type": "MASTER_SETTING", "generator_version": "test"},
                "route": {"primary_genre": "悬疑", "canonical_genre": "悬疑", "genre_filter": "悬疑"},
                "master_constraints": {"core_tone": "高压克制", "pacing_strategy": "冷硬克制"},
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (root / "大纲" / "第1卷-详细大纲.md").write_text(
        """### 第1章：只负责看站的人

**目标**：从老周口中问出潮位站停用前后的情况。
**阻力**：老周拒绝回答任何实质问题。
**核心冲突**：想追问 vs 每问一句都在把自己变成被观察对象。
**本章变化**：他表面认错，实际确认有人在盯着自己的动向。
**钩子**：回到工位，他发现那条调阅驳回记录被人删掉了。

**新增 craft 必填字段**：

- **beat_position**：Setup
- **scene_goal**：从老周口中问出潮位站停用前后的情况。
- **scene_conflict**：老周拒绝回答任何实质问题。
- **scene_setback**：老周把他来废站的事报给了档案科。
- **scene_resolution**：他确认有人在盯着自己的动向。
- **sequel_dilemma**：想追问 vs 正在被观察。
- **sequel_decision**：改走公开渠道查证。
""",
        encoding="utf-8",
    )
    return root


# --- Discovery / hot plug ---------------------------------------------------------

def test_discovery_is_a_directory_scan_with_diagnostics(tmp_path):
    root = tmp_path / "skills"
    _write_skill(root, "alpha")
    _write_skill(root, "beta")
    broken = root / "broken" / "SKILL.md"
    broken.parent.mkdir(parents=True)
    broken.write_text("no frontmatter", encoding="utf-8")

    report = list_with_diagnostics(roots=[root])

    assert [s["id"] for s in report["skills"]] == ["alpha", "beta"]
    assert len(report["skipped"]) == 1
    assert "broken" in report["skipped"][0]["path"]


def test_new_skill_is_discovered_without_any_code_change(tmp_path):
    """Hot-plug: dropping a new SKILL.md in the directory is the whole registration."""
    root = tmp_path / "skills"
    _write_skill(root, "alpha")
    assert [s["id"] for s in discover_writing_skills(roots=[root])] == ["alpha"]

    _write_skill(
        root,
        "test-sensory-detail",
        name="感官细节",
        purpose="用具体感官信息替代形容词堆叠。",
        applies_when=["情绪转折", "场景首次进入"],
        avoid_when=["连续动作段"],
        guidance="只挑一个与当前冲突有关的感官细节，放在人物做选择的那一刻。",
    )

    skills = discover_writing_skills(roots=[root])
    assert [s["id"] for s in skills] == ["alpha", "test-sensory-detail"]
    catalog = build_router_catalog(skills)
    picked = validate_selection(
        {"selected_skills": [{"id": "test-sensory-detail", "reason": "情绪转折", "chapter_guidance": "在许知远停住脚步的那一拍，只写一个他听见的声音。"}]},
        catalog,
    )
    assert picked["ok"] is True
    assert picked["selected_skills"][0]["id"] == "test-sensory-detail"


def test_project_root_skills_override_bundled_ones(tmp_path):
    bundled = tmp_path / "bundled"
    project = tmp_path / "project"
    _write_skill(bundled, "voice-style", guidance="内置版本。")
    _write_skill(project, "voice-style", guidance="项目版本。")

    skills = discover_writing_skills(roots=[bundled, project])
    assert len(skills) == 1
    assert skills[0]["guidance"] == "项目版本。"


def test_missing_required_field_is_skipped_not_crashing(tmp_path):
    root = tmp_path / "skills"
    bad = root / "bad" / "SKILL.md"
    bad.parent.mkdir(parents=True)
    bad.write_text("---\nid: bad\nname: bad\n---\n\nbody\n", encoding="utf-8")

    assert discover_writing_skills(roots=[root]) == []
    with pytest.raises(ValueError):
        load_skill_file(bad)


def test_bundled_skills_are_all_loadable():
    from data_modules.writing_skill_registry import PLUGIN_SKILLS_DIR

    skills = discover_writing_skills(roots=[PLUGIN_SKILLS_DIR])
    ids = {s["id"] for s in skills}
    assert {
        "scene-sequel",
        "reader-pull",
        "information-gap",
        "character-agency",
        "dialogue-subtext",
        "voice-style",
        "emotion-interiority",
        "pov-distance",
        "sensory-description",
    } <= ids
    for skill in skills:
        assert skill["purpose"]
        assert skill["applies_when"]
        assert skill["avoid_when"]
        assert skill["guidance"]


def test_voice_style_stays_inside_its_own_boundary():
    """Emotion, POV and sensory detail belong to their own skills, not voice-style.

    The old body told the Writer "只写身体，不写情绪结论", which forbade interiority
    outright and overlapped two other skills. Guard the narrowing so it is not undone.
    """
    from data_modules.writing_skill_registry import PLUGIN_SKILLS_DIR

    skills = {s["id"]: s for s in discover_writing_skills(roots=[PLUGIN_SKILLS_DIR])}
    body = skills["voice-style"]["guidance"]
    assert "只写身体" not in body
    assert "叙事距离" not in body
    assert "感官" not in body
    # The narrowed skill still owns prose-level voice.
    assert "句" in body and "比喻" in body


# --- Selection validation --------------------------------------------------------

def _catalog(tmp_path, *ids):
    root = tmp_path / "catalog"
    for skill_id in ids:
        _write_skill(root, skill_id)
    return build_router_catalog(discover_writing_skills(roots=[root]))


def test_unknown_skill_is_rejected(tmp_path):
    result = validate_selection(
        {"selected_skills": [{"id": "does-not-exist", "chapter_guidance": "写点具体的。"}]},
        _catalog(tmp_path, "alpha"),
    )
    assert result["ok"] is False
    assert any("unknown skill id" in e for e in result["errors"])


def test_empty_guidance_is_rejected_so_theory_cannot_reach_the_writer(tmp_path):
    result = validate_selection(
        {"selected_skills": [{"id": "alpha", "reason": "looks relevant"}]},
        _catalog(tmp_path, "alpha"),
    )
    assert result["ok"] is False
    assert any("chapter_guidance is required" in e for e in result["errors"])


@pytest.mark.parametrize("leak", ["请运用 Scene-Sequel 理论", "按潜台词理论写", "按 scene_goal 字段写", "use this Skill", "hook_type 设为悬念"])
def test_theory_leak_is_rejected(tmp_path, leak):
    result = validate_selection(
        {"selected_skills": [{"id": "alpha", "chapter_guidance": leak}]},
        _catalog(tmp_path, "alpha"),
    )
    assert result["ok"] is False
    assert any("leaks" in e for e in result["errors"])


def test_selection_cap_keeps_order_and_reports_duplicates(tmp_path):
    ids = ["s1", "s2", "s3", "s4", "s5", "s6"]
    catalog = _catalog(tmp_path, *ids)
    raw = {
        "selected_skills": [
            {"id": sid, "chapter_guidance": f"第{i}条具体写法。"}
            for i, sid in enumerate(ids, start=1)
        ]
        + [{"id": "s1", "chapter_guidance": "重复项。"}]
    }
    result = validate_selection(raw, catalog, max_skills=5)

    assert result["ok"] is True
    assert [s["id"] for s in result["selected_skills"]] == ["s1", "s2", "s3", "s4", "s5"]
    assert any("duplicate" in w for w in result["warnings"])
    assert any("keeping the first 5" in w for w in result["warnings"])


def test_fingerprint_is_stable_and_changes_with_guidance():
    one = [{"id": "a", "chapter_guidance": "写法一"}]
    two = [{"id": "a", "chapter_guidance": "写法二"}]
    assert selection_fingerprint(one) == selection_fingerprint([dict(one[0])])
    assert selection_fingerprint(one) != selection_fingerprint(two)


# --- Router input -----------------------------------------------------------------

def test_router_input_carries_plan_and_catalog_but_not_the_whole_canon(tmp_path):
    root = _base_project(tmp_path)
    gov = ChapterRuntime(root).get_governed_context(1)
    catalog = _catalog(tmp_path, "alpha", "beta")

    payload = build_router_input(
        chapter=1,
        story_identity=gov["story_identity"],
        current_intent=gov["current_intent"],
        governed_canon=gov["governed_canon"],
        creative_brief="【任务书】他只想问出一个具体答案。",
        catalog=catalog,
        writer_context=gov["writer_context"],
    )

    assert payload["chapter"] == 1
    assert payload["book"]["genre"] == "悬疑"
    assert "问出潮位站停用前后的情况" in payload["chapter_intent"]["goal"]
    assert payload["scene"]["scene_goal"].startswith("从老周口中问出")
    assert [s["id"] for s in payload["available_skills"]] == ["alpha", "beta"]
    assert "他只想问出一个具体答案" in payload["creative_brief"]
    assert payload["rules"]["select_count"] == "2-5"
    # A compact router view, not a Canon dump.
    assert "canon_items" not in json.dumps(payload, ensure_ascii=False)


# --- Writer prompt ----------------------------------------------------------------

def test_writer_prompt_renders_only_translated_guidance(tmp_path):
    root = _base_project(tmp_path)
    selection = [
        {"id": "dialogue-subtext", "reason": "两条台词在互相试探", "chapter_guidance": "老周不要解释自己为什么拒绝；让他用合上登记簿这个动作回答。"},
        {"id": "character-agency", "reason": "主角容易被动接收信息", "chapter_guidance": "许知远必须主动改一次策略，并承担被档案科注意到的后果。"},
    ]
    pkg = ChapterRuntime(root).get_writer_package(1, creative_brief="【任务书】", writing_skills=selection)

    with_skills = pkg.to_writer_prompt(scene_design=True, reader_pull=True, writing_skills=True)
    without = pkg.to_writer_prompt(scene_design=True, reader_pull=True)

    assert "## 本章创作方法" in with_skills
    # Canon / author intent / chapter prohibitions outrank every skill.
    assert "与 Canon、作者意图、本章禁区冲突时，一律以后者为准" in with_skills
    # The Writer never sees the meta label "Writing Skills".
    assert "Writing Skills" not in with_skills
    assert "1. 老周不要解释自己为什么拒绝" in with_skills
    assert "2. 许知远必须主动改一次策略" in with_skills
    # Identity, reason and theory stay out of the Writer prompt.
    for token in ("dialogue-subtext", "character-agency", "两条台词在互相试探", "reason", "理论"):
        assert token not in with_skills
    assert "本章创作方法" not in without
    # The addition is guidance-sized, not a theory dump.
    assert 0 < len(with_skills) - len(without) < 1200


def test_skills_are_bound_into_the_package_fingerprint_and_status(tmp_path):
    root = _base_project(tmp_path)
    runtime = ChapterRuntime(root)
    baseline = runtime.get_writer_package(1, creative_brief="【任务书】")

    selection = [{"id": "voice-style", "chapter_guidance": "这一段不要写情绪结论，只写手上的动作。"}]
    sealed = runtime.attach_creative_brief(1, "【任务书】", writing_skills=selection)

    assert sealed.writing_skills_fingerprint
    assert sealed.package_fingerprint != baseline.package_fingerprint
    status = runtime.get_status(1)
    assert status.package_fingerprint == sealed.package_fingerprint
    assert status.is_writer_package_stale is False
    assert status.writing_skill_ids == ["voice-style"]
    assert sealed.meta["writing_skill_ids"] == ["voice-style"]


def test_render_writer_skills_ignores_empty_entries():
    assert render_writer_skills([]) == []
    assert render_writer_skills([{"id": "x", "chapter_guidance": "  "}]) == []


# --- Write-flow contract ----------------------------------------------------------

def test_both_write_skills_run_the_router_and_pass_the_selection():
    plugin_root = Path(__file__).resolve().parent.parent.parent / ".claude" / "plugins" / "zhanghui"
    for skill in ("webnovel-write", "webnovel-fast-write"):
        text = (plugin_root / "skills" / skill / "SKILL.md").read_text(encoding="utf-8")
        assert "zhanghui:writing-skill-router" in text, skill
        assert "--skills-file" in text, skill

    router = (plugin_root / "agents" / "writing-skill-router.md").read_text(encoding="utf-8")
    assert "name: writing-skill-router" in router
    assert "writing-skills input" in router
    assert "writing-skills validate" in router
