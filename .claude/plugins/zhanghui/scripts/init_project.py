#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
网文项目初始化脚本

目标：
- 生成可运行的项目结构（webnovel-project）
- 创建/更新 .webnovel/state.json（初始化配置与兼容读模型）
- 生成基础设定集与大纲模板文件（供 /webnovel-plan 与 /webnovel-write 使用）

说明：
- 该脚本是命令 /webnovel-init 的“唯一允许的文件生成入口”（与命令文档保持一致）。
- 生成的内容以“模板骨架”为主，便于 AI/作者后续补全；但保证所有关键文件存在。
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

from runtime_compat import enable_windows_utf8_stdio
from typing import Any, Dict, List
import re

# 安全修复：导入安全工具函数
from security_utils import sanitize_commit_message, atomic_write_json, is_git_available
from project_locator import write_current_project_pointer
from genre_taxonomy import resolve_genre_input, resolve_template_stems


# Windows 编码兼容性修复
if sys.platform == "win32":
    enable_windows_utf8_stdio()


_ASCII_LETTER_RE = re.compile(r"[A-Za-z]")


def _validate_initial_genre_source(genre: str) -> str:
    normalized = str(genre or "").strip()
    if _ASCII_LETTER_RE.search(normalized):
        raise SystemExit(
            "题材必须使用中文名称，不能使用英文 profile key "
            f"'{normalized}'。例如：规则怪谈、悬疑、玄幻。"
        )
    return normalized


def _read_text_if_exists(path: Path) -> str:
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8")


def _write_text_if_missing(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        return
    path.write_text(content, encoding="utf-8")


def _split_genre_keys(genre: str) -> list[str]:
    raw = (genre or "").strip()
    if not raw:
        return []
    # 支持复合题材：A+B / A+B / A、B / A与B
    raw = re.sub(r"[＋/、]", "+", raw)
    raw = raw.replace("与", "+")
    parts = [p.strip() for p in raw.split("+") if p.strip()]
    return parts or [raw]


def _normalize_genre_key(key: str) -> str:
    stems = resolve_template_stems(key)
    return stems[0] if stems else key


def _apply_label_replacements(text: str, replacements: Dict[str, str]) -> str:
    if not text or not replacements:
        return text
    lines = text.splitlines()
    for i, line in enumerate(lines):
        stripped = line.lstrip()
        for label, value in replacements.items():
            if not value:
                continue
            prefix = f"- {label}："
            if stripped.startswith(prefix):
                leading = line[: len(line) - len(stripped)]
                lines[i] = f"{leading}{prefix}{value}"
    return "\n".join(lines)


def _parse_tier_map(raw: str) -> Dict[str, str]:
    result: Dict[str, str] = {}
    if not raw:
        return result
    for part in raw.split(";"):
        part = part.strip()
        if not part:
            continue
        if ":" in part:
            key, val = part.split(":", 1)
            result[key.strip()] = val.strip()
    return result


def _needs_protagonist_group(protagonist_structure: str) -> bool:
    text = (protagonist_structure or "").strip()
    return any(marker in text for marker in ("主角组", "双主角", "多主角", "群像主角"))


def _needs_heroine_card(heroine_config: str, heroine_names: str) -> bool:
    text = (heroine_config or "").strip().lower()
    if text in {"无", "无女主", "none", "no heroine"}:
        return False
    return bool((heroine_names or "").strip() or text)


def _render_team_rows(names: List[str], roles: List[str]) -> List[str]:
    rows = []
    for idx, name in enumerate(names):
        role = roles[idx] if idx < len(roles) else ""
        rows.append(f"| {name} | {role or '主线/副线'} | | | |")
    return rows


def _ensure_state_schema(state: Dict[str, Any]) -> Dict[str, Any]:
    """确保 state.json 具备 v5.1 架构所需的字段集合（v5.4 沿用）。

    v5.1 变更:
    - entities_v3 和 alias_index 已迁移到 index.db，不再存储在 state.json
    - structured_relationships 已迁移到 index.db relationships 表
    - state.json 保持精简 (< 5KB)
    """
    state.setdefault("project_info", {})
    state.setdefault("progress", {})
    state.setdefault("protagonist_state", {})
    state.setdefault("relationships", {})  # update_state.py 需要此字段
    state.setdefault("disambiguation_warnings", [])
    state.setdefault("disambiguation_pending", [])
    state.setdefault("world_settings", {"power_system": [], "factions": [], "locations": []})
    state.setdefault("plot_threads", {"active_threads": [], "foreshadowing": []})
    state.setdefault("review_checkpoints", [])
    state.setdefault("chapter_meta", {})
    state.setdefault(
        "strand_tracker",
        {
            "last_quest_chapter": 0,
            "last_fire_chapter": 0,
            "last_constellation_chapter": 0,
            "current_dominant": "quest",
            "chapters_since_switch": 0,
            "history": [],
        },
    )
    # v5.1: entities_v3, alias_index, structured_relationships 已迁移到 index.db
    # 不再在 state.json 中初始化这些字段

    # progress schema evolution
    state["progress"].setdefault("current_chapter", 0)
    state["progress"].setdefault("total_words", 0)
    state["progress"].setdefault("last_updated", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    state["progress"].setdefault("volumes_completed", [])
    state["progress"].setdefault("current_volume", 1)
    state["progress"].setdefault("volumes_planned", [])

    # protagonist schema evolution
    ps = state["protagonist_state"]
    ps.setdefault("name", "")
    ps.setdefault("power", {"realm": "", "layer": 1, "bottleneck": ""})
    ps.setdefault("location", {"current": "", "last_chapter": 0})
    ps.setdefault("golden_finger", {"name": "", "level": 1, "cooldown": 0, "skills": []})
    ps.setdefault("attributes", {})

    return state


def _build_master_outline(target_chapters: int, *, chapters_per_volume: int = 50) -> str:
    volumes = (target_chapters - 1) // chapters_per_volume + 1 if target_chapters > 0 else 1
    lines: list[str] = [
        "# 总纲",
        "",
        "> 本文件为“总纲骨架”，用于 /webnovel-plan 细化为卷大纲与章纲。",
        "",
        "## 卷结构",
        "",
    ]

    for v in range(1, volumes + 1):
        start = (v - 1) * chapters_per_volume + 1
        end = min(v * chapters_per_volume, target_chapters)
        lines.extend(
            [
                f"### 第{v}卷（第{start}-{end}章）",
                "- 核心冲突：",
                "- 关键爽点：",
                "- 卷末高潮：",
                "- 主要登场角色：",
                "- 关键伏笔（埋/收）：",
                "",
            ]
        )

    return "\n".join(lines).rstrip() + "\n"


def _now_iso() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _md_escape(s: str) -> str:
    """Escape characters that break markdown tables / headings."""
    if not isinstance(s, str):
        s = str(s)
    return (
        s.replace("\\", "\\\\")
         .replace("|", "\\|")
         .replace("\n", " ")
         .replace("\r", " ")
    )


def _render_volume_skeleton_outline(
    skeleton: list[dict], target_chapters: int,
) -> str:
    """Render a multi-volume 总纲 from a user-supplied skeleton list.

    Uses the same `### 第N卷` heading style as `_build_master_outline` so
    /webnovel-plan can read it uniformly. Falls back to existing chapter
    range / 核心冲突 / 卷末高潮 fields populated from the skeleton entry.
    """
    lines: list[str] = [
        "# 总纲",
        "",
        "> 本文件由 init_project.py 通过 volume_skeleton 自动生成。",
        "",
        "## 卷结构",
        "",
    ]
    for v in skeleton:
        idx = v.get("index", "?")
        title = v.get("title", "")
        title = _md_escape(title)
        rng = v.get("chapter_range", [])
        if len(rng) == 2:
            range_str = f"（第{rng[0]}-{rng[1]}章）"
        else:
            range_str = ""
        if title:
            heading = f"### 第{idx}卷 {title}{range_str}"
        else:
            heading = f"### 第{idx}卷{range_str}"
        lines.append(heading)
        conflict = v.get("core_conflict", "") or "（待填写）"
        climax = v.get("climax", "") or "（待填写）"
        lines.append(f"- 核心冲突：{_md_escape(conflict)}")
        lines.append("- 关键爽点：")
        lines.append(f"- 卷末高潮：{_md_escape(climax)}")
        lines.append("- 主要登场角色：")
        lines.append("- 关键伏笔（埋/收）：")
        status = v.get("status", "confirmed")
        lines.append(f"- 状态：{_md_escape(status)}")
        lines.append("")
    lines.append(f"> 预计总章节数：{target_chapters}")
    lines.append("")
    return "\n".join(lines)


def _inject_volume_rows(template_text: str, target_chapters: int, *, chapters_per_volume: int = 50) -> str:
    """在总纲模板的卷表中只注入首卷行（后续卷由规划完成后写回）。"""
    lines = template_text.splitlines()
    header_idx = None
    for i, line in enumerate(lines):
        if line.strip().startswith("| 卷号"):
            header_idx = i
            break
    if header_idx is None:
        return template_text

    insert_idx = header_idx + 2 if header_idx + 1 < len(lines) else len(lines)
    end = min(chapters_per_volume, target_chapters) if target_chapters > 0 else chapters_per_volume
    rows = [f"| 1 | | 第1-{end}章 | | |"]

    # 避免重复插入（若模板已有数据行）
    existing = {line.strip() for line in lines}
    rows = [r for r in rows if r.strip() not in existing]
    return "\n".join(lines[:insert_idx] + rows + lines[insert_idx:])


def _validate_idea_bank_payload(raw: str) -> dict:
    """Parse and validate an idea_bank.json payload string.

    Required schema (matches 2026-08-16-webnovel-init-deconstruction-wiring-design §D2):
      - version == 1
      - top-level keys: source, selected_idea, constraints_inherited,
        borrowed_patterns, do_not_copy, canon_contamination_warnings
      - source.reference_source in {"none", "book_name", "local_text", "excerpt"}
      - source.analysis_mode in {"quick", "deep"}

    Optional (P0-Full): reference_research_path (str, relative path).
    """
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        raise ValueError(f"idea_bank.json is not valid JSON: {e}") from e

    if not isinstance(data, dict):
        raise ValueError("idea_bank.json must be a JSON object")

    # I2 fix: identity check rejects True (which == 1) and 1.0 (which == 1 in Python)
    version = data.get("version")
    if version is None or not isinstance(version, int) or isinstance(version, bool) or version != 1:
        raise ValueError(
            f"idea_bank.json version must be exactly the int 1, got {version!r}"
        )

    required_top = {
        "source", "selected_idea", "constraints_inherited",
        "borrowed_patterns", "do_not_copy", "canon_contamination_warnings",
    }
    missing = required_top - set(data.keys())
    if missing:
        raise ValueError(f"idea_bank.json missing required top-level keys: {sorted(missing)}")

    # Optional fields (P0-Full): silently accept if absent (backward compat)
    # Currently just reference_research_path; future fields can be added here.

    source = data.get("source")
    if not isinstance(source, dict):
        raise ValueError("idea_bank.json source must be an object")

    ref_src = source.get("reference_source")
    if ref_src not in {"none", "book_name", "local_text", "excerpt"}:
        raise ValueError(
            f"idea_bank.json source.reference_source must be one of "
            f"{{none, book_name, local_text, excerpt}}, got {ref_src!r}"
        )

    mode = source.get("analysis_mode")
    if mode not in {"quick", "deep"}:
        raise ValueError(
            f"idea_bank.json source.analysis_mode must be quick or deep, got {mode!r}"
        )

    # I3 fix: optional reference_research_path validation
    # (P0-Full spec §D4 + adversarial finding I3)
    if "reference_research_path" in data:
        rrp = data["reference_research_path"]
        if not isinstance(rrp, str):
            raise ValueError(
                f"idea_bank.reference_research_path must be a string, got {type(rrp).__name__}"
            )
        from pathlib import Path as _Path
        if _Path(rrp).is_absolute():
            raise ValueError(
                f"idea_bank.reference_research_path must be relative, got {rrp!r}"
            )
        if ".." in _Path(rrp).parts:
            raise ValueError(
                f"idea_bank.reference_research_path must not contain '..', got {rrp!r}"
            )

    return data


def init_project(
    project_dir: str,
    title: str,
    genre: str,
    *,
    protagonist_name: str = "",
    target_words: int = 2_000_000,
    target_chapters: int = 600,
    golden_finger_name: str = "",
    golden_finger_type: str = "",
    golden_finger_style: str = "",
    core_selling_points: str = "",
    protagonist_structure: str = "",
    heroine_config: str = "",
    heroine_names: str = "",
    heroine_role: str = "",
    co_protagonists: str = "",
    co_protagonist_roles: str = "",
    antagonist_tiers: str = "",
    world_scale: str = "",
    factions: str = "",
    power_system_type: str = "",
    social_class: str = "",
    resource_distribution: str = "",
    gf_visibility: str = "",
    gf_irreversible_cost: str = "",
    protagonist_desire: str = "",
    protagonist_flaw: str = "",
    protagonist_archetype: str = "",
    antagonist_level: str = "",
    target_reader: str = "",
    platform: str = "",
    currency_system: str = "",
    currency_exchange: str = "",
    sect_hierarchy: str = "",
    cultivation_chain: str = "",
    cultivation_subtiers: str = "",
    reference_research_dir: str = "",
    reference_overwrite: bool = False,
    volume_skeleton: list[dict] | None = None,
    force: bool = False,
) -> None:
    project_path = Path(project_dir).expanduser().resolve()
    if ".claude" in project_path.parts:
        raise SystemExit("Refusing to initialize a project inside .claude. Choose a different directory.")
    from data_modules.projection_generation import ProjectionGeneration
    if ProjectionGeneration(project_path).enrollment_path.exists():
        raise ValueError("Cannot reinitialize an activation-managed project through the base-only initializer")
    genre = _validate_initial_genre_source(genre)
    genre_resolution = resolve_genre_input(genre)
    canonical_genre = genre_resolution.canonical_genre or genre
    project_path.mkdir(parents=True, exist_ok=True)

    # Guard against silent re-init overwrite (spec §4.2 invariant protection).
    # If volumes[] already has confirmed entries, refuse to overwrite unless caller
    # opts in via the `force` parameter.
    if not force:
        existing_state_path = project_path / ".webnovel" / "state.json"
        if existing_state_path.exists():
            try:
                _existing_state: Dict[str, Any] = json.loads(
                    existing_state_path.read_text(encoding="utf-8")
                )
            except json.JSONDecodeError:
                _existing_state = {}
            confirmed_existing = [
                v for v in _existing_state.get("volumes", [])
                if v.get("status") == "confirmed"
            ]
            if confirmed_existing:
                raise ValueError(
                    f"Refusing to re-init: project already has "
                    f"{len(confirmed_existing)} confirmed volume(s). "
                    f"Pass force=True to override (not yet supported)."
                )

    # 目录结构（同时兼容“卷目录”与后续扩展）
    directories = [
        ".webnovel/backups",
        ".webnovel/archive",
        ".webnovel/summaries",
        "设定集",
        "大纲",
        "正文",
        "审查报告",
    ]
    for dir_path in directories:
        (project_path / dir_path).mkdir(parents=True, exist_ok=True)

    # state.json（创建或增量补齐）
    state_path = project_path / ".webnovel" / "state.json"
    if state_path.exists():
        try:
            state: Dict[str, Any] = json.loads(state_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
            corrupt_path = state_path.with_name(f"state.corrupt_{timestamp}.json")
            shutil.copy2(state_path, corrupt_path)
            print(f"⚠️ 原 state.json 已损坏，已另存为 {corrupt_path} 供手工抢救")
            state = {}
    else:
        state = {}

    state = _ensure_state_schema(state)
    created_at = state.get("project_info", {}).get("created_at") or datetime.now().strftime("%Y-%m-%d")

    state["project_info"].update(
        {
            "title": title,
            "genre": canonical_genre,
            "genre_label": genre,
            "genre_tags": {
                "route": genre_resolution.route_tags,
                "trope": genre_resolution.trope_tags,
                "format": genre_resolution.format_tags,
                "templates": [Path(name).stem for name in genre_resolution.template_files],
            },
            "created_at": created_at,
            "target_words": int(target_words),
            "target_chapters": int(target_chapters),
            # 下面字段属于“初始化元信息”，不影响运行时脚本
            "golden_finger_name": golden_finger_name,
            "golden_finger_type": golden_finger_type,
            "golden_finger_style": golden_finger_style,
            "core_selling_points": core_selling_points,
            "protagonist_structure": protagonist_structure,
            "heroine_config": heroine_config,
            "heroine_names": heroine_names,
            "heroine_role": heroine_role,
            "co_protagonists": co_protagonists,
            "co_protagonist_roles": co_protagonist_roles,
            "antagonist_tiers": antagonist_tiers,
            "world_scale": world_scale,
            "factions": factions,
            "power_system_type": power_system_type,
            "social_class": social_class,
            "resource_distribution": resource_distribution,
            "gf_visibility": gf_visibility,
            "gf_irreversible_cost": gf_irreversible_cost,
            "target_reader": target_reader,
            "platform": platform,
            "currency_system": currency_system,
            "currency_exchange": currency_exchange,
            "sect_hierarchy": sect_hierarchy,
            "cultivation_chain": cultivation_chain,
            "cultivation_subtiers": cultivation_subtiers,
        }
    )

    if protagonist_name:
        state["protagonist_state"]["name"] = protagonist_name

    # Volume skeleton: write volumes[] to state.json per spec §4.
    # Use VolumeStateManager to enforce invariants (index continuity, etc.).
    # Fail-fast on malformed entries (missing `index` or invalid
    # status/source enum values raise ValueError) — these are
    # structural errors the caller should fix, not silently coerced.
    if volume_skeleton:
        from data_modules.volume_state import (
            VolumeRecord, VolumeSource, VolumeStatus, VolumeStateManager,
        )

        # Validate the FULL skeleton for index continuity BEFORE writing.
        # VolumeStateManager.append_or_update enforces one-at-a-time,
        # so we pre-check by walking through and calling it.
        mgr = VolumeStateManager(state)
        for v in volume_skeleton:
            rec = VolumeRecord(
                index=int(v["index"]),
                title=v.get("title", ""),
                chapter_range=v.get("chapter_range", [0, 0]),
                core_conflict=v.get("core_conflict", ""),
                climax=v.get("climax", ""),
                status=VolumeStatus(v.get("status", "confirmed")),  # raises ValueError on invalid
                source=VolumeSource(v.get("source", "human")),       # raises ValueError on invalid
            )
            mgr.append_or_update(rec)
        # mgr has already written to state["volumes"] via append_or_update
        # update planning_horizon (VolumeStateManager._update_horizon was called per append)
        # setdefault for later_volumes_status to preserve re-init state
        state["project_info"].setdefault("later_volumes_status", "deferred")
    else:
        # No skeleton: still initialize empty volumes[] and defaults so plan skill can read
        state.setdefault("volumes", [])
        state["project_info"].setdefault("confirmed_through_volume", 0)
        state["project_info"].setdefault("later_volumes_status", "deferred")

    gf_type_norm = (golden_finger_type or "").strip()
    if gf_type_norm in {"无", "无金手指", "none"}:
        state["protagonist_state"]["golden_finger"]["name"] = "无金手指"
        state["protagonist_state"]["golden_finger"]["level"] = 0
        state["protagonist_state"]["golden_finger"]["cooldown"] = 0
    elif golden_finger_name:
        state["protagonist_state"]["golden_finger"]["name"] = golden_finger_name

    # 确保 golden_finger 字段存在且可编辑
    if not state["protagonist_state"]["golden_finger"].get("name"):
        state["protagonist_state"]["golden_finger"]["name"] = "未命名金手指"

    state["progress"]["last_updated"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    state_path.parent.mkdir(parents=True, exist_ok=True)
    # 使用原子化写入（初始化不需要备份旧文件）
    atomic_write_json(state_path, state, use_lock=True, backup=False)

    # 读取内置模板（可选）
    script_dir = Path(__file__).resolve().parent
    templates_dir = script_dir.parent / "templates"
    output_templates_dir = templates_dir / "output"
    genre_key = (genre or "").strip()
    template_files = list(genre_resolution.template_files)
    if not template_files:
        template_files = [f"{_normalize_genre_key(k)}.md" for k in _split_genre_keys(genre_key)]
    genre_templates = []
    seen = set()
    for template_file in template_files:
        if not template_file or template_file in seen:
            continue
        seen.add(template_file)
        template_text = _read_text_if_exists(templates_dir / "genres" / template_file)
        if template_text:
            genre_templates.append(template_text.strip())
    genre_template = "\n\n---\n\n".join(genre_templates)
    output_worldview = _read_text_if_exists(output_templates_dir / "设定集-世界观.md")
    output_power = _read_text_if_exists(output_templates_dir / "设定集-力量体系.md")
    output_protagonist = _read_text_if_exists(output_templates_dir / "设定集-主角卡.md")
    output_heroine = _read_text_if_exists(output_templates_dir / "设定集-女主卡.md")
    output_team = _read_text_if_exists(output_templates_dir / "设定集-主角组.md")
    output_outline = _read_text_if_exists(output_templates_dir / "大纲-总纲.md")
    output_antagonist = _read_text_if_exists(output_templates_dir / "设定集-反派设计.md")

    # 基础文件（只在缺失时生成，避免覆盖已有内容）
    now = datetime.now().strftime("%Y-%m-%d")

    worldview_content = output_worldview.strip() if output_worldview else ""
    if not worldview_content:
        worldview_content = "\n".join(
            [
                "# 世界观",
                "",
                f"> 项目：{title}｜题材：{genre}｜创建：{now}",
                "",
                "## 一句话世界观",
                "- （用一句话说明世界的核心规则与卖点）",
                "",
                "## 核心规则（设定即物理）",
                "- 规则1：",
                "- 规则2：",
                "- 规则3：",
                "",
                "## 势力与地理（简版）",
                "- 主要势力：",
                "- 关键地点：",
                "",
                "## 参考题材模板（可删/可改）",
                "",
                (genre_template.strip() + "\n") if genre_template else "（未找到对应题材模板，可自行补充）\n",
            ]
        ).rstrip() + "\n"
    else:
        worldview_content = _apply_label_replacements(
            worldview_content,
            {
                "大陆/位面数量": world_scale,
                "核心势力": factions,
                "社会阶层": social_class,
                "资源分配规则": resource_distribution,
                "宗门/组织层级": sect_hierarchy,
                "货币体系": currency_system,
                "兑换规则": currency_exchange,
            },
        )
        if genre_template:
            worldview_content = (
                worldview_content.rstrip()
                + "\n\n## 参考题材模板（可删/可改）\n\n"
                + genre_template.strip()
                + "\n"
            )
    _write_text_if_missing(
        project_path / "设定集" / "世界观.md",
        worldview_content,
    )

    power_content = output_power.strip() if output_power else ""
    if not power_content:
        power_content = "\n".join(
            [
                "# 力量体系",
                "",
                f"> 项目：{title}｜题材：{genre}｜创建：{now}",
                "",
                "## 等级/境界划分",
                "- （列出从弱到强的等级，含突破条件与代价）",
                "",
                "## 技能/招式规则",
                "- 获得方式：",
                "- 成本与副作用：",
                "- 进阶与组合：",
                "",
                "## 禁止事项（防崩坏）",
                "- 未达等级不得使用高阶能力（设定即物理）",
                "- 新增能力必须申报并入库（发明需申报）",
                "",
            ]
        ).rstrip() + "\n"
    else:
        power_content = _apply_label_replacements(
            power_content,
            {
                "体系类型": power_system_type,
                "典型境界链（可选）": cultivation_chain,
                "小境界划分": cultivation_subtiers,
            },
        )
    _write_text_if_missing(
        project_path / "设定集" / "力量体系.md",
        power_content,
    )

    protagonist_content = output_protagonist.strip() if output_protagonist else ""
    if not protagonist_content:
        protagonist_content = "\n".join(
            [
                "# 主角卡",
                "",
                f"> 主角：{protagonist_name or '（待填写）'}｜项目：{title}｜创建：{now}",
                "",
                "## 三要素",
                f"- 欲望：{protagonist_desire or '（待填写）'}",
                f"- 弱点：{protagonist_flaw or '（待填写）'}",
                f"- 人设类型：{protagonist_archetype or '（待填写）'}",
                "",
                "## 初始状态（开局）",
                "- 身份：",
                "- 资源：",
                "- 约束：",
                "",
                "## 金手指概览",
                f"- 称呼：{golden_finger_name or '（待填写）'}",
                f"- 类型：{golden_finger_type or '（待填写）'}",
                f"- 风格：{golden_finger_style or '（待填写）'}",
                "- 成长曲线：",
                "",
            ]
        ).rstrip() + "\n"
    else:
        protagonist_content = _apply_label_replacements(
            protagonist_content,
            {
                "姓名": protagonist_name,
                "真正渴望（可能不自知）": protagonist_desire,
                "性格缺陷": protagonist_flaw,
            },
        )
    _write_text_if_missing(
        project_path / "设定集" / "主角卡.md",
        protagonist_content,
    )

    heroine_content = output_heroine.strip() if output_heroine else ""
    if heroine_content and _needs_heroine_card(heroine_config, heroine_names):
        heroine_content = _apply_label_replacements(
            heroine_content,
            {
                "姓名": heroine_names,
                "与主角关系定位（对手/盟友/共谋/牵制）": heroine_role,
            },
        )
        _write_text_if_missing(project_path / "设定集" / "女主卡.md", heroine_content)

    team_content = output_team.strip() if output_team else ""
    if team_content and _needs_protagonist_group(protagonist_structure):
        names = [n.strip() for n in co_protagonists.split(",") if n.strip()] if co_protagonists else []
        roles = [r.strip() for r in co_protagonist_roles.split(",") if r.strip()] if co_protagonist_roles else []
        if names:
            lines = team_content.splitlines()
            new_rows = _render_team_rows(names, roles)
            replaced = False
            out_lines: List[str] = []
            for line in lines:
                if line.strip().startswith("| 主角A"):
                    out_lines.extend(new_rows)
                    replaced = True
                    continue
                if replaced and line.strip().startswith("| 主角"):
                    continue
                out_lines.append(line)
            team_content = "\n".join(out_lines)
        _write_text_if_missing(
            project_path / "设定集" / "主角组.md",
            team_content,
        )

    antagonist_content = output_antagonist.strip() if output_antagonist else ""
    if not antagonist_content:
        antagonist_content = "\n".join(
            [
                "# 反派设计",
                "",
                f"> 项目：{title}｜创建：{now}",
                "",
                f"- 反派等级：{antagonist_level or '（待填写）'}",
                "- 动机：",
                "- 资源/势力：",
                "- 与主角的镜像关系：",
                "- 终局：",
                "",
            ]
        ).rstrip() + "\n"
    else:
        tier_map = _parse_tier_map(antagonist_tiers)
        if tier_map:
            lines = antagonist_content.splitlines()
            out_lines = []
            for line in lines:
                if line.strip().startswith("| 小反派"):
                    name = tier_map.get("小反派", "")
                    out_lines.append(f"| 小反派 | {name} | 前期 | | |")
                    continue
                if line.strip().startswith("| 中反派"):
                    name = tier_map.get("中反派", "")
                    out_lines.append(f"| 中反派 | {name} | 中期 | | |")
                    continue
                if line.strip().startswith("| 大反派"):
                    name = tier_map.get("大反派", "")
                    out_lines.append(f"| 大反派 | {name} | 后期 | | |")
                    continue
                out_lines.append(line)
            antagonist_content = "\n".join(out_lines)
    _write_text_if_missing(project_path / "设定集" / "反派设计.md", antagonist_content)

    outline_content = output_outline.strip() if output_outline else ""

    # Multi-volume skeleton path takes priority when provided
    if volume_skeleton:
        outline_content = _render_volume_skeleton_outline(
            volume_skeleton, int(target_chapters)
        )
    elif outline_content:
        outline_content = _inject_volume_rows(outline_content, int(target_chapters)).rstrip() + "\n"
    else:
        outline_content = _build_master_outline(int(target_chapters))
    _write_text_if_missing(project_path / "大纲" / "总纲.md", outline_content)

    # 生成环境变量模板（不写入真实密钥）
    _write_text_if_missing(
        project_path / ".env.example",
        "\n".join(
            [
                "# Webnovel Writer 配置示例（复制为 .env 后填写）",
                "# 注意：请勿将包含真实 API_KEY 的 .env 提交到版本库。",
                "",
                "# Embedding",
                "EMBED_BASE_URL=https://api-inference.modelscope.cn/v1",
                "EMBED_MODEL=Qwen/Qwen3-Embedding-8B",
                "EMBED_API_KEY=",
                "",
                "# Rerank",
                "RERANK_BASE_URL=https://api.jina.ai/v1",
                "RERANK_MODEL=jina-reranker-v3",
                "RERANK_API_KEY=",
                "",
            ]
        )
        + "\n",
    )

    # Git 初始化（仅当项目目录内尚无 .git 且 Git 可用）
    git_dir = project_path / ".git"
    if not git_dir.exists():
        if not is_git_available():
            print("\n⚠️  Git 不可用，跳过版本控制初始化")
            print("💡 如需启用 Git 版本控制，请安装 Git: https://git-scm.com/")
        else:
            print("\nInitializing Git repository...")
            try:
                subprocess.run(["git", "init"], cwd=project_path, check=True, capture_output=True, text=True)

                gitignore_file = project_path / ".gitignore"
                if not gitignore_file.exists():
                    gitignore_file.write_text(
                        """# Python
__pycache__/
*.py[cod]
*.so

# Env (keep .env.example)
.env
.env.*
!.env.example

# Temporary files
*.tmp
*.bak
.DS_Store

# IDE
.vscode/
.idea/

# Don't ignore .webnovel (we need to track state.json)
# But ignore cache files
.webnovel/context_cache.json
.webnovel/*.lock
.webnovel/*.bak
# 原子写入的滚动备份（本地恢复用，不入库）
.webnovel/backups/
.webnovel/**/backups/
""",
                        encoding="utf-8",
                    )

                subprocess.run(["git", "add", "."], cwd=project_path, check=True, capture_output=True)
                # 安全修复：清理 title 防止命令注入
                safe_title = sanitize_commit_message(title)
                subprocess.run(
                    ["git", "commit", "-m", f"初始化网文项目：{safe_title}"],
                    cwd=project_path,
                    check=True,
                    capture_output=True,
                )
                print("Git initialized.")
            except subprocess.CalledProcessError as e:
                print(f"Git init failed (non-fatal): {e}")

    # 记录工作区默认项目指针（非阻断）
    try:
        pointer_file = write_current_project_pointer(project_path)
        if pointer_file is not None:
            print(f"Default project pointer updated: {pointer_file}")
    except Exception as e:
        print(f"Default project pointer update failed (non-fatal): {e}")

    # === reference_research/ 验证（spec 2026-08-16 §D3/D7）===
    if reference_research_dir:
        raw_src_tree = Path(reference_research_dir).expanduser()
        # C3 fix: refuse symlinks BEFORE resolving (resolve() would follow and lose the symlink info)
        if raw_src_tree.is_symlink():
            raise SystemExit(
                f"--reference-research-dir is a symlink (refusing to follow): {raw_src_tree}"
            )
        src_tree = raw_src_tree.resolve()
        if not src_tree.is_dir():
            raise SystemExit(
                f"--reference-research-dir not found or not a directory: {src_tree}"
            )
        from init_reference_tree import validate_reference_tree
        if not validate_reference_tree(src_tree):
            raise SystemExit(
                f"--reference-research-dir is not a valid reference_research tree (missing required files): {src_tree}"
            )
        # Copy tree into project
        book_safe = src_tree.name
        target_tree = project_path / ".webnovel" / "reference_research" / book_safe
        if target_tree.exists() and not reference_overwrite:
            raise SystemExit(
                f"reference_research tree already exists at {target_tree}. "
                f"Pass reference_overwrite=True (or --reference-overwrite CLI flag) to overwrite."
            )
        # Backup existing schema to OUTSIDE target_tree (preserves even on overwrite)
        existing_schema = target_tree / "_schema.json"
        if existing_schema.exists():
            from datetime import timezone as _tz
            backups_dir = project_path / ".webnovel" / "backups"
            backups_dir.mkdir(parents=True, exist_ok=True)
            backup = backups_dir / f"{book_safe}__schema__{datetime.now(_tz.utc).strftime('%Y%m%dT%H%M%S_%fZ')}.bak"
            shutil.copy2(existing_schema, backup)
        target_tree.parent.mkdir(parents=True, exist_ok=True)
        # In-place overwrite (no rmtree — shutil.copytree with dirs_exist_ok overwrites files)
        shutil.copytree(src_tree, target_tree, dirs_exist_ok=True)
        print(f"已写入 {target_tree}")

    # === 个人语料 + 写作宪法模板写入（Phase E）===
    # 从 plugin templates/ 复制默认模板到 <book>/.webnovel/writer-profile/，
    # 仅在书项目副本不存在时 copy（避免覆盖用户已编辑的内容）。
    writer_profile = project_path / ".webnovel" / "writer-profile"
    writer_profile.mkdir(parents=True, exist_ok=True)
    for template_name in ("个人语料.md", "写作宪法.md"):
        src = templates_dir / template_name
        dst = writer_profile / template_name
        if not dst.exists() and src.exists():
            shutil.copy(src, dst)
            print(f"✅ 已写入 {dst}")

    print(f"\nProject initialized at: {project_path}")
    print("Key files:")
    print(" - .webnovel/state.json")
    print(" - .webnovel/writer-profile/个人语料.md")
    print(" - .webnovel/writer-profile/写作宪法.md")
    print(" - 设定集/世界观.md")
    print(" - 设定集/力量体系.md")
    print(" - 设定集/主角卡.md")
    print(" - 大纲/总纲.md")


def _render_volume_blueprint(volume: dict, total_project_chapters: int) -> tuple[str, str, str]:
    """Render 详细大纲 / 15节拍 / 时间线 三件套 for one volume.

    I5: raises ValueError if ch_range is reversed (start > end) to prevent
    silent garbage volume blueprints.
    """
    idx = volume["index"]
    title = volume.get("title", f"V{idx}")
    ch_range = volume.get("chapter_range") or [0, 0]
    # I5: validate chapter range before rendering
    if len(ch_range) == 2 and ch_range[0] > ch_range[1]:
        raise ValueError(
            f"chapter_range is reversed for volume {idx!r}: "
            f"start ({ch_range[0]}) > end ({ch_range[1]})"
        )
    core_conflict = volume.get("core_conflict", "")
    climax = volume.get("climax", "")
    vol_chapters = max(1, ch_range[1] - ch_range[0] + 1)

    # 第N卷-详细大纲.md
    detailed = (
        f"# 第{idx}卷 详细大纲 — {title}\n\n"
        f"**章节范围**: {ch_range[0]}-{ch_range[1]} ({vol_chapters} 章)\n"
        f"**核心冲突**: {core_conflict}\n"
        f"**卷末高潮**: {climax}\n\n"
        f"## 章节蓝图\n\n"
        f"（plan 流程 Step 7 填充 chapter list；本骨架由 --all-volumes 自动生成）\n"
    )

    # 第N卷-15节拍.md (Save the Cat)
    beats = [
        "Opening Image", "Theme Stated", "Setup", "Catalyst",
        "Debate", "Break Into Two", "B Story", "Fun and Games",
        "Midpoint", "Bad Guys Close In", "All Is Lost",
        "Dark Night of the Soul", "Break Into Three", "Finale", "Final Image",
    ]
    percentages = [0.01, 0.05, 0.10, 0.10, 0.20, 0.20, 0.22, 0.50, 0.50, 0.75, 0.75, 0.80, 0.80, 0.99, 1.00]
    beat_lines = []
    for name, pct in zip(beats, percentages):
        ch = max(1, round(pct * vol_chapters))
        beat_lines.append(f"- **{name}** — ch {ch}")
    beat_sheet = (
        f"# 第{idx}卷 15-节拍表 — {title}\n\n"
        f"**节拍分布算法**: 比例法 (vol_chapters={vol_chapters})\n\n"
        + "\n".join(beat_lines) + "\n"
    )

    # 第N卷-时间线.md
    timeline = (
        f"# 第{idx}卷 时间线 — {title}\n\n"
        f"**章节范围**: ch {ch_range[0]} - ch {ch_range[1]}\n"
        f"**项目总章节**: {total_project_chapters}\n\n"
        f"（事件时间线由 plan 流程 Step 6.5 填充；本骨架由 --all-volumes 自动生成）\n"
    )
    return detailed, beat_sheet, timeline


def _atomic_write(path: Path, content: str) -> None:
    """C1: atomic write via tmp + os.replace, prevents partial writes.

    Writes to path + ".tmp" first; on success os.replace swaps it in atomically.
    On failure the tmp file is cleaned up and the exception re-raised.
    Caller is responsible for the idempotent skip check; this helper only writes.
    """
    import os
    tmp = path.with_suffix(path.suffix + ".tmp")
    try:
        tmp.write_text(content, encoding="utf-8")
        os.replace(tmp, path)
    except Exception:
        if tmp.exists():
            try:
                tmp.unlink()
            except OSError:
                pass
        raise


def _has_cycle(edges: list[dict]) -> bool:
    """C2: Tarjan-style DFS cycle detection on a simple integer-node digraph.

    Edges: list of {"from": int, "to": int, ...}.
    Returns True if any back-edge found (cycle present).
    A linear chain has no cycle.
    """
    nodes: set[int] = set()
    for e in edges:
        nodes.add(int(e["from"]))
        nodes.add(int(e["to"]))
    if not nodes:
        return False
    adj: dict[int, list[int]] = {n: [] for n in nodes}
    for e in edges:
        adj[int(e["from"])].append(int(e["to"]))
    WHITE, GRAY, BLACK = 0, 1, 2
    color = {n: WHITE for n in nodes}

    def dfs(n: int) -> bool:
        color[n] = GRAY
        for m in adj[n]:
            if color[m] == GRAY:
                return True
            if color[m] == WHITE and dfs(m):
                return True
        color[n] = BLACK
        return False

    for n in nodes:
        if color[n] == WHITE and dfs(n):
            return True
    return False


def generate_volume_blueprints(
    project_root,
    all_volumes: bool = False,
    force: bool = False,
) -> int:
    """按 confirmed volumes[] 生成 N 卷蓝图三件套.

    C1: idempotent — files that already exist with non-empty content are skipped
    (unless force=True). Atomic writes via tmp + os.replace prevent half-written
    files on interruption.

    C2: also writes project_info.cross_volume_beat_map = linear adjacency list
    of confirmed volumes (from → to edge per consecutive pair) and validates
    no cycle via DFS.

    Args:
        project_root: 项目根目录.
        all_volumes: True 一次性铺全部 confirmed 卷; False 不铺.
        force: True 覆盖已有非空文件.

    Returns:
        实际写入的文件数 (新增 + 覆盖).
    """
    if not all_volumes:
        return 0
    state_path = Path(project_root) / ".webnovel" / "state.json"
    if not state_path.is_file():
        return 0
    import json
    state = json.loads(state_path.read_text(encoding="utf-8"))
    confirmed = [v for v in state.get("volumes", []) if v.get("status") == "confirmed"]
    if not confirmed:
        return 0
    total_project_chapters = state.get("project_info", {}).get("target_chapters", 600)
    outline_dir = Path(project_root) / "大纲"
    outline_dir.mkdir(parents=True, exist_ok=True)
    written = 0
    for vol in confirmed:
        idx = vol["index"]
        detailed, beat_sheet, timeline = _render_volume_blueprint(vol, total_project_chapters)
        for content, suffix in (
            (detailed, "详细大纲.md"),
            (beat_sheet, "15节拍.md"),
            (timeline, "时间线.md"),
        ):
            path = outline_dir / f"第{idx}卷-{suffix}"
            # Idempotent: skip existing non-empty unless force
            if not force and path.is_file() and path.read_text(encoding="utf-8").strip():
                continue
            _atomic_write(path, content)
            written += 1

    # C2: cross_volume_beat_map — linear adjacency of confirmed volumes
    sorted_confirmed = sorted(confirmed, key=lambda v: v["index"])
    beat_map_entries: list[dict] = []
    for i in range(len(sorted_confirmed) - 1):
        from_v = sorted_confirmed[i]
        to_v = sorted_confirmed[i + 1]
        beat_map_entries.append({
            "from": int(from_v["index"]),
            "to": int(to_v["index"]),
            "edge_id": f"v{int(from_v['index'])}_to_v{int(to_v['index'])}",
        })
    # Cycle check (linear chain can't cycle, but verify anyway as a safety net)
    if _has_cycle(beat_map_entries):
        raise ValueError(f"cross_volume_beat_map has cycle: {beat_map_entries}")

    state.setdefault("project_info", {})["cross_volume_beat_map"] = beat_map_entries
    state_path.write_text(
        json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return written


def main() -> None:
    parser = argparse.ArgumentParser(description="网文项目初始化脚本（生成项目结构 + state.json + 基础模板）")
    parser.add_argument("project_dir", help="项目目录（建议 ./webnovel-project）")
    parser.add_argument("title", help="小说标题")
    parser.add_argument(
        "genre",
        help="题材类型（可用“+”组合，如：都市脑洞+规则怪谈；示例：修仙/系统流/都市异能/古言/现实题材）",
    )

    parser.add_argument("--protagonist-name", default="", help="主角姓名")
    parser.add_argument("--target-words", type=int, default=2_000_000, help="目标总字数（默认 2000000）")
    parser.add_argument("--target-chapters", type=int, default=600, help="目标总章节数（默认 600）")

    parser.add_argument("--golden-finger-name", default="", help="金手指称呼/系统名（建议读者可见的代号）")
    parser.add_argument("--golden-finger-type", default="", help="金手指类型（如 系统流/鉴定流/签到流）")
    parser.add_argument("--golden-finger-style", default="", help="金手指风格（如 冷漠工具型/毒舌吐槽型）")
    parser.add_argument("--core-selling-points", default="", help="核心卖点（逗号分隔）")
    parser.add_argument("--protagonist-structure", default="", help="主角结构（单主角/多主角）")
    parser.add_argument("--heroine-config", default="", help="女主配置（无女主/单女主/多女主）")
    parser.add_argument("--heroine-names", default="", help="女主姓名（多个用逗号分隔）")
    parser.add_argument("--heroine-role", default="", help="女主定位（事业线/情感线/对抗线）")
    parser.add_argument("--co-protagonists", default="", help="多主角姓名（逗号分隔）")
    parser.add_argument("--co-protagonist-roles", default="", help="多主角定位（逗号分隔）")
    parser.add_argument("--antagonist-tiers", default="", help="反派分层（如 小反派:张三;中反派:李四;大反派:王五）")
    parser.add_argument("--world-scale", default="", help="世界规模")
    parser.add_argument("--factions", default="", help="势力格局/核心势力")
    parser.add_argument("--power-system-type", default="", help="力量体系类型")
    parser.add_argument("--social-class", default="", help="社会阶层")
    parser.add_argument("--resource-distribution", default="", help="资源分配")
    parser.add_argument("--gf-visibility", default="", help="金手指可见度（明牌/半明牌/暗牌）")
    parser.add_argument("--gf-irreversible-cost", default="", help="金手指不可逆代价")
    parser.add_argument("--currency-system", default="", help="货币体系")
    parser.add_argument("--currency-exchange", default="", help="货币兑换/面值规则")
    parser.add_argument("--sect-hierarchy", default="", help="宗门/组织层级")
    parser.add_argument("--cultivation-chain", default="", help="典型境界链")
    parser.add_argument("--cultivation-subtiers", default="", help="小境界划分（初/中/后/巅 等）")

    parser.add_argument("--reference-research-dir", default="",
                        help="预构建的 reference_research 树路径；init 主流程在 Step 1.5 落盘后传进来验证")
    parser.add_argument("--reference-overwrite", action="store_true",
                        help="强制覆盖已存在的 reference_research 树（默认拒绝覆盖）")

    # 深度模式可选参数（用于预填模板）
    parser.add_argument("--protagonist-desire", default="", help="主角核心欲望（深度模式）")
    parser.add_argument("--protagonist-flaw", default="", help="主角性格弱点（深度模式）")
    parser.add_argument("--protagonist-archetype", default="", help="主角人设类型（深度模式）")
    parser.add_argument("--antagonist-level", default="", help="反派等级（深度模式）")
    parser.add_argument("--target-reader", default="", help="目标读者（深度模式）")
    parser.add_argument("--platform", default="", help="发布平台（深度模式）")
    parser.add_argument(
        "--all-volumes", action="store_true",
        help="一次性铺 N 卷蓝图 (覆盖所有 confirmed volumes). 默认关闭保持现状兼容."
    )
    parser.add_argument(
        "--force", action="store_true",
        help="C1: 与 --all-volumes 共用; 强制覆盖已存在的卷蓝图文件 (默认跳过).",
    )

    args = parser.parse_args()

    init_project(
        args.project_dir,
        args.title,
        args.genre,
        protagonist_name=args.protagonist_name,
        target_words=args.target_words,
        target_chapters=args.target_chapters,
        golden_finger_name=args.golden_finger_name,
        golden_finger_type=args.golden_finger_type,
        golden_finger_style=args.golden_finger_style,
        core_selling_points=args.core_selling_points,
        protagonist_structure=args.protagonist_structure,
        heroine_config=args.heroine_config,
        heroine_names=args.heroine_names,
        heroine_role=args.heroine_role,
        co_protagonists=args.co_protagonists,
        co_protagonist_roles=args.co_protagonist_roles,
        antagonist_tiers=args.antagonist_tiers,
        world_scale=args.world_scale,
        factions=args.factions,
        power_system_type=args.power_system_type,
        social_class=args.social_class,
        resource_distribution=args.resource_distribution,
        gf_visibility=args.gf_visibility,
        gf_irreversible_cost=args.gf_irreversible_cost,
        protagonist_desire=args.protagonist_desire,
        protagonist_flaw=args.protagonist_flaw,
        protagonist_archetype=args.protagonist_archetype,
        antagonist_level=args.antagonist_level,
        target_reader=args.target_reader,
        platform=args.platform,
        currency_system=args.currency_system,
        currency_exchange=args.currency_exchange,
        sect_hierarchy=args.sect_hierarchy,
        cultivation_chain=args.cultivation_chain,
        cultivation_subtiers=args.cultivation_subtiers,
        reference_research_dir=args.reference_research_dir,
        reference_overwrite=args.reference_overwrite,
    )

    if getattr(args, 'all_volumes', False):
        written = generate_volume_blueprints(
            args.project_dir, all_volumes=True, force=args.force,
        )
        print(f"--all-volumes: wrote {written} volume blueprint file(s)")


if __name__ == "__main__":
    main()
