"""AI Volume Drafter — pure function that produces CandidateVolume.

Takes an LLM-callable so tests can mock it. Never persists output.
See docs/superpowers/specs/2026-08-18-multi-volume-init-design.md §5.2.
"""
from __future__ import annotations

from typing import Callable

from data_modules.volume_state import (
    CandidateVolume, VolumeSource, VolumeRecord, VolumeStatus,
)


def draft_next_volume(
    *,
    one_line_concept: str,
    confirmed_volumes: list[VolumeRecord],
    genre: str,
    target_index: int,
    llm_call: Callable[[str], str],
) -> CandidateVolume:
    """Call llm_call with a prompt, parse the response into CandidateVolume.

    Raises ValueError on parse failure. Returns status=draft, source=ai.
    """
    prompt = _build_prompt(one_line_concept, confirmed_volumes, genre, target_index)
    raw = llm_call(prompt)
    return _parse(raw, target_index)


def _build_prompt(
    concept: str, prior: list[VolumeRecord], genre: str, target_index: int,
) -> str:
    prior_text = "\n".join(
        f"- V{v.index} {v.title}: 冲突={v.core_conflict}, 高潮={v.climax}"
        for v in prior
    ) or "(无)"
    return (
        f"题材：{genre}\n"
        f"全书一句话：{concept}\n"
        f"已确认前卷（必须承接且不重复伏笔）：\n{prior_text}\n\n"
        f"请起草第 {target_index} 卷的骨架：\n"
        f"卷名：\n"
        f"核心冲突：\n"
        f"卷末高潮：\n"
        f"严格遵循格式：\n"
        f"卷名：<20字以内>\n"
        f"核心冲突：<一句话>\n"
        f"卷末高潮：<一句话>\n"
    )


def _parse(raw: str, target_index: int) -> CandidateVolume:
    title = _extract(raw, "卷名")
    conflict = _extract(raw, "核心冲突")
    climax = _extract(raw, "卷末高潮")
    if not (title and conflict and climax):
        raise ValueError(f"LLM output missing required fields: {raw[:200]}")
    return CandidateVolume(
        index=target_index,
        title=title,
        core_conflict=conflict,
        climax=climax,
        status=VolumeStatus.DRAFT,
        source=VolumeSource.AI,
    )


def _extract(text: str, key: str) -> str:
    # Normalize half-width colon to full-width before parsing
    # (LLMs sometimes return either form)
    for line in text.splitlines():
        normalized = line.replace(":", "：")
        if normalized.strip().startswith(key + "："):
            return normalized.split("：", 1)[1].strip()
    return ""