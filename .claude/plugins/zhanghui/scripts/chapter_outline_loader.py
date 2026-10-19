#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict

try:
    from chapter_paths import (
        find_outline_chapter_section,
        iter_outline_chapter_headings,
        parse_chapter_number,
        volume_num_for_chapter,
    )
except ImportError:  # pragma: no cover
    from scripts.chapter_paths import (
        find_outline_chapter_section,
        iter_outline_chapter_headings,
        parse_chapter_number,
        volume_num_for_chapter,
    )


_CHAPTER_RANGE_RE = re.compile(r"^\s*(\d+)\s*-\s*(\d+)\s*$")


def _parse_chapters_range(value: object) -> tuple[int, int] | None:
    if not isinstance(value, str):
        return None
    match = _CHAPTER_RANGE_RE.match(value)
    if not match:
        return None
    try:
        start = int(match.group(1))
        end = int(match.group(2))
    except ValueError:
        return None
    if start <= 0 or end <= 0 or start > end:
        return None
    return start, end


def volume_num_for_chapter_from_state(project_root: Path, chapter_num: int) -> int | None:
    state_path = project_root / ".webnovel" / "state.json"
    if not state_path.exists():
        return None

    try:
        state = json.loads(state_path.read_text(encoding="utf-8"))
    except Exception:
        return None

    if not isinstance(state, dict):
        return None

    progress = state.get("progress")
    if not isinstance(progress, dict):
        return None

    volumes_planned = progress.get("volumes_planned")
    if not isinstance(volumes_planned, list):
        return None

    best: tuple[int, int] | None = None
    for item in volumes_planned:
        if not isinstance(item, dict):
            continue
        volume = item.get("volume")
        if not isinstance(volume, int) or volume <= 0:
            continue
        parsed = _parse_chapters_range(item.get("chapters_range"))
        if not parsed:
            continue
        start, end = parsed
        if start <= chapter_num <= end:
            candidate = (start, volume)
            if best is None or candidate[0] > best[0] or (candidate[0] == best[0] and candidate[1] < best[1]):
                best = candidate

    return best[1] if best else None


def _find_split_outline_file(outline_dir: Path, chapter_num: int) -> Path | None:
    patterns = [
        f"第{chapter_num}章*.md",
        f"第{chapter_num:02d}章*.md",
        f"第{chapter_num:03d}章*.md",
        f"第{chapter_num:04d}章*.md",
    ]
    for pattern in patterns:
        matches = sorted(outline_dir.glob(pattern))
        if matches:
            return matches[0]
    return None


def _find_volume_outline_file(project_root: Path, chapter_num: int) -> Path | None:
    outline_dir = project_root / "大纲"
    volume_num = volume_num_for_chapter_from_state(project_root, chapter_num) or volume_num_for_chapter(chapter_num)
    candidates = [
        outline_dir / f"第{volume_num}卷-详细大纲.md",
        outline_dir / f"第{volume_num}卷 - 详细大纲.md",
        outline_dir / f"第{volume_num}卷 详细大纲.md",
    ]
    return next((path for path in candidates if path.exists()), None)


def _extract_outline_section(content: str, chapter_num: int) -> str | None:
    """截取某章章纲小节。

    标题层级/数字写法/冒号形态统一走 `chapter_paths.find_outline_chapter_section`
    的共享标题契约（官方模板写 `## 第N章：`，历史章纲可能写 `### 第N章：` 或
    `## 第N章`）。此函数不再自带第三套正则。
    """
    return find_outline_chapter_section(content, chapter_num)


def _extract_directive_section(content: str, chapter_num: int) -> str | None:
    """与 `_extract_outline_section` 完全同源，避免两套标题解析互相漂移。"""
    return _extract_outline_section(content, chapter_num)


def load_chapter_outline(project_root: Path, chapter_num: int, max_chars: int | None = 1500) -> str:
    outline_dir = project_root / "大纲"

    split_outline = _find_split_outline_file(outline_dir, chapter_num)
    if split_outline is not None:
        return split_outline.read_text(encoding="utf-8")

    volume_outline = _find_volume_outline_file(project_root, chapter_num)
    if volume_outline is None:
        return f"⚠️ 大纲文件不存在：第 {chapter_num} 章"

    outline = _extract_outline_section(volume_outline.read_text(encoding="utf-8"), chapter_num)
    if outline is None:
        return f"⚠️ 未找到第 {chapter_num} 章的大纲"

    if max_chars and len(outline) > max_chars:
        return outline[:max_chars] + "\n...(已截断)"
    return outline

_PLOT_SECTION_FIELD_MAP = {
    "cbn": "cbn",
    "cpns": "cpns",
    "cen": "cen",
    "必须覆盖节点": "mandatory_nodes",
    "本章禁区": "prohibitions",
}

def _is_chapter_heading_line(line: str) -> bool:
    """判断一行是否是章标题行（共享标题契约，含中文数字与可选冒号）。"""
    return bool(iter_outline_chapter_headings(line))


def _parse_chinese_chapter_num(value: str) -> int | None:
    """向后兼容别名：章号解析已统一到 `chapter_paths.parse_chapter_number`。"""
    return parse_chapter_number(value)


# 章纲字段契约。键为章纲里出现过的字段名（大小写不敏感），值为 governed context
# 中 `current_intent.directive` 使用的规范键。上半部为历史字段，下半部为官方模板
# `templates/output/大纲-卷详细大纲.md`「新增 craft 必填字段」段落的字段 —— 这些字段
# 此前从未被解析，导致 Writer / Reviewer 拿不到本章的 scene_goal / hook_type /
# foreshadow 义务与 本章禁区。
_DIRECTIVE_FIELD_MAP = {
    "目标": "goal",
    "本章目标": "goal",
    "章目标": "goal",
    "阻力": "obstacles",
    "障碍": "obstacles",
    "代价": "cost",
    "核心冲突": "conflict",
    "本章变化": "chapter_change",
    "时间锚点": "time_anchor",
    "时间": "time_anchor",
    "章内跨度": "chapter_span",
    "章节跨度": "chapter_span",
    "倒计时状态": "countdown",
    "倒计时": "countdown",
    "cbn": "cbn",
    "cpns": "cpns",
    "cen": "cen",
    "必须覆盖节点": "must_cover_nodes",
    "本章禁区": "forbidden_zones",
    "章末未闭合问题": "chapter_end_open_question",
    "章末问题": "chapter_end_open_question",
    "未闭合问题": "chapter_end_open_question",
    "钩子": "hook",
    "钩子类型": "hook_type",
    "钩子强度": "hook_strength",
    "关键实体": "key_entities",
    "涉及实体": "key_entities",
    "strand": "strand",
    "反派层级": "antagonist_tier",
    # 官方模板「新增 craft 必填字段」
    "beat_position": "beat_position",
    "hook_type": "hook_type",
    "scene_goal": "scene_goal",
    "scene_conflict": "scene_conflict",
    "scene_setback": "scene_setback",
    "scene_resolution": "scene_resolution",
    "sequel_reaction": "sequel_reaction",
    "sequel_dilemma": "sequel_dilemma",
    "sequel_decision": "sequel_decision",
    "foreshadow_buried": "foreshadow_buried",
    "foreshadow_paid_off": "foreshadow_paid_off",
    # 章节定位与类型
    "章节类型": "chapter_type",
    "本章类型": "chapter_type",
    "章类型": "chapter_type",
    "类型": "chapter_type",
    "chapter_type": "chapter_type",
    "章节定位": "chapter_role",
    "本章定位": "chapter_role",
    "章节角色": "chapter_role",
    "chapter_role": "chapter_role",
}

_DIRECTIVE_LIST_FIELDS = {
    "cpns", "must_cover_nodes", "forbidden_zones", "key_entities",
    "foreshadow_buried", "foreshadow_paid_off",
}

# 列表字段的分隔符。cpns 的规范写法是「角色 | 动作 | 结果」，`|` 是字段内分隔符
# 而非条目分隔符，因此只按中文分号切分，不能把一条 CPN 切成三段。
_DIRECTIVE_SPLIT_RE = {
    "cpns": re.compile(r"[；;]+"),
    "must_cover_nodes": re.compile(r"[、,，；;|]+"),
    "forbidden_zones": re.compile(r"[、,，；;|]+"),
    "key_entities": re.compile(r"[、,，；;|]+"),
    "foreshadow_buried": re.compile(r"[、,，；;|]+"),
    "foreshadow_paid_off": re.compile(r"[、,，；;|]+"),
}

# 「无 / 无。 / none / n/a / -」等占位值在列表字段里不入账。
_EMPTY_FIELD_VALUES = {"", "无", "无。", "none", "n/a", "na", "-", "—", "null", "[]"}

# 未知标签且同行为空值 → 视为结构性小标题（如官方模板的「**新增 craft 必填字段**：」
# 「**结构化节点**：」），重置当前字段，避免把标题文本拼进上一字段的值里。
_LABEL_ONLY_RE = re.compile(r"^[^：:\n]{1,32}[：:]\s*$")
_BOLD_LABEL_RE = re.compile(r"^\*\*[^*]+\*\*\s*[：:]?\s*$")
_SENTENCE_PUNCT_RE = re.compile(r"[。！？，、；;,.!?…]")


def _clean_plot_line(line: str) -> str:
    """归一化一行章纲：去掉列表符号与 markdown 强调标记。

    官方模板的字段写作 `**目标**：…`、`- **beat_position**：…`；若不清掉 `**`，
    标签正则匹配不到任何字段，整章 directive / plot_structure 会退化成空字典。
    """
    text = str(line or "").strip()
    text = re.sub(r"^[-*•]\s+", "", text)
    text = re.sub(r"^\d+[\.、]\s*", "", text)
    text = text.replace("**", "").replace("__", "")
    text = re.sub(r"^`+|`+$", "", text)
    return text.strip()


def _is_structural_label_line(raw_line: str, cleaned: str) -> bool:
    """判断一行是否是「结构性小标题」而不是某个字段的延续行。

    官方模板用 `**新增 craft 必填字段**：` / `**结构化节点**：` 分节。这些行若不识别，
    会把标题文字拼进上一个字段的值里（例如把「新增 craft 必填字段」拼进 scene_resolution）。
    只在「带加粗的独立标签行」或「短标签行且无句读」时判定为小标题，避免误吃正文。
    """
    if _BOLD_LABEL_RE.match(str(raw_line or "").strip()):
        return True
    if not _LABEL_ONLY_RE.match(cleaned):
        return False
    label = re.split(r"[：:]", cleaned, maxsplit=1)[0]
    return not _SENTENCE_PUNCT_RE.search(label)


def _append_plot_value(target: Dict[str, Any], field: str, value: str) -> None:
    value = _clean_plot_line(value)
    if not value:
        return
    if field in {"cpns", "mandatory_nodes", "prohibitions"} and value.lower() in _EMPTY_FIELD_VALUES:
        return

    if field in {"cpns", "mandatory_nodes", "prohibitions"}:
        target.setdefault(field, [])
        candidates = [value]
        if field in {"mandatory_nodes", "prohibitions"}:
            split_values = [part.strip() for part in re.split(r"[、,，；;|]+", value) if part.strip()]
            if split_values:
                candidates = split_values
        for item in candidates:
            if item not in target[field]:
                target[field].append(item)
        return

    if field not in target:
        target[field] = value


def _split_directive_values(value: str, field: str = "") -> list[str]:
    text = _clean_plot_line(value)
    if not text:
        return []
    pattern = _DIRECTIVE_SPLIT_RE.get(field, re.compile(r"[、,，；;|]+"))
    return [part.strip() for part in pattern.split(text) if part.strip()]


def _append_directive_value(target: Dict[str, Any], field: str, value: str) -> None:
    value = _clean_plot_line(value)
    if not value:
        return
    if value.lower() in _EMPTY_FIELD_VALUES:
        # 「无」「n/a」这类占位值不入账；否则 `foreshadow_paid_off：无` 会被当义务。
        return
    if field in _DIRECTIVE_LIST_FIELDS:
        target.setdefault(field, [])
        for item in _split_directive_values(value, field) or [value]:
            if item not in target[field]:
                target[field].append(item)
        return
    if field not in target:
        target[field] = value


def parse_chapter_plot_structure(outline_text: str) -> Dict[str, Any]:
    text = str(outline_text or "")
    if not text or text.startswith("⚠️"):
        return {}

    structure: Dict[str, Any] = {}
    current_field = ""

    for raw_line in text.splitlines():
        stripped = raw_line.strip()
        if not stripped:
            current_field = ""
            continue
        if _is_chapter_heading_line(stripped):
            current_field = ""
            continue

        cleaned = _clean_plot_line(stripped)
        matched_field = ""
        matched_value = ""
        for label, field in _PLOT_SECTION_FIELD_MAP.items():
            match = re.match(rf"^{re.escape(label)}\s*[：:]\s*(.*)$", cleaned, re.IGNORECASE)
            if match:
                matched_field = field
                matched_value = match.group(1).strip()
                break

        if matched_field:
            current_field = matched_field
            _append_plot_value(structure, matched_field, matched_value)
            continue

        if _is_structural_label_line(stripped, cleaned):
            current_field = ""
            continue

        if current_field:
            _append_plot_value(structure, current_field, cleaned)

    cpns = structure.get("cpns") or []
    mandatory_nodes = structure.get("mandatory_nodes") or []
    prohibitions = structure.get("prohibitions") or []
    if not any([structure.get("cbn"), cpns, structure.get("cen"), mandatory_nodes, prohibitions]):
        return {}

    return {
        "cbn": str(structure.get("cbn") or "").strip(),
        "cpns": cpns,
        "cen": str(structure.get("cen") or "").strip(),
        "mandatory_nodes": mandatory_nodes,
        "prohibitions": prohibitions,
        "source": "chapter_outline",
    }


def load_chapter_plot_structure(project_root: Path, chapter_num: int) -> Dict[str, Any]:
    outline = load_chapter_outline(project_root, chapter_num, max_chars=None)
    return parse_chapter_plot_structure(outline)


def parse_chapter_execution_directive(outline_text: str) -> Dict[str, Any]:
    text = str(outline_text or "")
    if not text or text.startswith("⚠️"):
        return {}

    directive: Dict[str, Any] = {}
    current_field = ""
    for raw_line in text.splitlines():
        stripped = raw_line.strip()
        if not stripped:
            current_field = ""
            continue
        if _is_chapter_heading_line(stripped):
            current_field = ""
            continue

        cleaned = _clean_plot_line(stripped)
        matched_field = ""
        matched_value = ""
        for label, field in _DIRECTIVE_FIELD_MAP.items():
            match = re.match(rf"^{re.escape(label)}\s*[：:]\s*(.*)$", cleaned, re.IGNORECASE)
            if match:
                matched_field = field
                matched_value = match.group(1).strip()
                break

        if matched_field:
            current_field = matched_field
            _append_directive_value(directive, matched_field, matched_value)
            continue
        if _is_structural_label_line(stripped, cleaned):
            current_field = ""
            continue
        if current_field:
            _append_directive_value(directive, current_field, cleaned)

    plot_structure = parse_chapter_plot_structure(text)
    for source_key, target_key in (
        ("cbn", "cbn"),
        ("cpns", "cpns"),
        ("cen", "cen"),
        ("mandatory_nodes", "must_cover_nodes"),
        ("prohibitions", "forbidden_zones"),
    ):
        if plot_structure.get(source_key) and not directive.get(target_key):
            directive[target_key] = plot_structure[source_key]

    if directive:
        directive["source"] = "chapter_outline"
    return directive


def load_chapter_execution_directive(project_root: Path, chapter_num: int) -> Dict[str, Any]:
    outline_dir = project_root / "大纲"
    split_outline = _find_split_outline_file(outline_dir, chapter_num)
    if split_outline is not None:
        return parse_chapter_execution_directive(split_outline.read_text(encoding="utf-8"))

    volume_outline = _find_volume_outline_file(project_root, chapter_num)
    if volume_outline is None:
        return {}
    section = _extract_directive_section(volume_outline.read_text(encoding="utf-8"), chapter_num)
    if section is None:
        return {}
    return parse_chapter_execution_directive(section)
