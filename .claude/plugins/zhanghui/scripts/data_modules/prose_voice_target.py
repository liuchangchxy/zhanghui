#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Prose Voice Target (Issue #26).

Constructs a structured, positive voice target (prose profile) for Writer and Editor by combining:
1. User profile: .webnovel/writer-profile/个人语料.md
2. Book constitution: .webnovel/writer-profile/写作宪法.md
3. Confirmed chapter samples / baseline fingerprint
4. Reference research observations
5. Genre defaults

Eliminates purely negative rulebook piling, giving the pipeline a clear standard of
how the chapter *should* sound and read while preserving natural literary breathing room.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Dict, List, Optional


@dataclass
class VoiceTarget:
    """Positive voice and prose styling contract."""
    genre: str = "通用"
    narrative_pov: str = "第三人称限制视角"
    author_identity: str = ""
    core_rules: List[str] = field(default_factory=list)
    sentence_rhythm: Dict[str, Any] = field(default_factory=lambda: {
        "preferred_lengths": "句长随场景自然起伏：动作段紧凑明快，沉浸与过渡段允许中长句抒发",
        "breathing_room": "保持叙事呼吸感与场景氛围沉浸，避免通篇同一机械节奏",
        "staccato_warning": "严禁通篇单句成段或极短句碎切（电报体倾向）",
    })
    dialogue_policy: Dict[str, Any] = field(default_factory=lambda: {
        "voice_differentiation": "角色语言各具性格与口吻，避免所有人千篇一律书面化",
        "subtext_allowed": "允许潜台词、合理沉默与意图冲突，不强制每句对白都成为设定说明书",
        "tag_naturalness": "对话引导动作自然，避免机械重复 'XX淡淡道' 或强迫全换成生理动作",
    })
    positive_guidance: List[str] = field(default_factory=lambda: [
        "保持中文网文叙事张力与自然语感",
        "允许直接、真实的情绪流露，不强行把所有情感机械化改写为'指节发白+牙齿打颤'",
        "保持节奏疏密对比，精彩处紧凑，过渡处舒缓",
    ])
    preservation_notes: List[str] = field(default_factory=lambda: [
        "保留原文中的普通中长句与合理副词",
        "保留自然安静的场景氛围描写",
        "不追求句句极高信息密度的压缩文本",
    ])
    forbidden_inventions: List[str] = field(default_factory=lambda: [
        "严禁 Editor 擅自编造新人物履历（如'当过三年机修学徒'）",
        "严禁 Editor 擅自把'偶然事件'篡改为'角色主动试探/心机设局'",
        "严禁 Editor 擅自发明新技能、新关系、新物品归属、新世界规则",
        "若发现剧情合理性漏洞，必须标记 SEMANTIC_CHANGE_PROPOSED，不得自行补丁事实",
    ])
    raw_sources: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=indent)

    def format_prompt_block(self) -> str:
        """Format a concise positive voice guide for insertion into prompts."""
        lines = [
            f"=== 正向文风锚 (Voice Target: {self.genre}) ===",
        ]
        if self.author_identity:
            clean_identity = [
                line.strip().lstrip("#-*\t ")
                for line in self.author_identity.splitlines()
                if line.strip() and not line.strip().startswith("#") and _clean_template_val(line)
            ]
            if clean_identity:
                lines.append(f"- 作者核心语调与风格: {'；'.join(clean_identity[:3])}")
        lines.extend([
            f"- 视角与调性: {self.narrative_pov}",
            f"- 句式与呼吸感: {self.sentence_rhythm.get('preferred_lengths', '')}；{self.sentence_rhythm.get('breathing_room', '')}",
        ])
        if self.core_rules:
            lines.append("- 最高优先级写作原则 (宪法):")
            for r in self.core_rules[:4]:
                lines.append(f"  * {r.lstrip('#-*\t ').strip()}")
        elif self.positive_guidance:
            lines.append("- 正向写作准则:")
            for item in self.positive_guidance[:4]:
                lines.append(f"  * {item}")
        lines.append("- 文本保留要求:")
        for item in self.preservation_notes[:3]:
            lines.append(f"  * {item}")
        lines.append("- 严守事实边界 (Editor 禁区):")
        for item in self.forbidden_inventions[:4]:
            lines.append(f"  * {item}")
        return "\n".join(lines)


def _clean_template_val(val: str) -> Optional[str]:
    cleaned = val.strip()
    if not cleaned or "{{" in cleaned or "待填" in cleaned:
        return None
    return cleaned


def build_voice_target(
    project_root: str | Path,
    chapter: int = 1,
    genre: Optional[str] = None,
) -> VoiceTarget:
    """Build positive voice target by combining available project assets."""
    root = Path(project_root)
    state_file = root / ".webnovel" / "state.json"
    detected_genre = genre or "通用"

    if state_file.is_file():
        try:
            state = json.loads(state_file.read_text(encoding="utf-8"))
            detected_genre = (
                genre
                or state.get("project_info", {}).get("genre")
                or state.get("genre")
                or "通用"
            )
        except Exception:
            pass

    target = VoiceTarget(genre=detected_genre)
    raw_sources: Dict[str, Any] = {}

    # 1. 个人语料
    profile_file = root / ".webnovel" / "writer-profile" / "个人语料.md"
    if profile_file.is_file():
        try:
            text = profile_file.read_text(encoding="utf-8")
            raw_sources["writer_profile"] = text
            target.author_identity = text
            for line in text.splitlines():
                if "句长偏好" in line:
                    parts = line.split("：", 1) if "：" in line else line.split(":", 1)
                    if len(parts) > 1 and _clean_template_val(parts[1]):
                        target.sentence_rhythm["preferred_lengths"] = parts[1].strip()
                elif "视角" in line:
                    parts = line.split("：", 1) if "：" in line else line.split(":", 1)
                    if len(parts) > 1 and _clean_template_val(parts[1]):
                        target.narrative_pov = parts[1].strip()
        except Exception:
            pass

    # 2. 写作宪法
    constitution_file = root / ".webnovel" / "writer-profile" / "写作宪法.md"
    if constitution_file.is_file():
        try:
            const_text = constitution_file.read_text(encoding="utf-8")
            raw_sources["constitution"] = const_text
            rules = [
                line.strip()
                for line in const_text.splitlines()
                if line.strip() and not line.strip().startswith("#") and _clean_template_val(line)
            ]
            target.core_rules = rules
            clean_bullets = [
                r.lstrip("-* ").strip()
                for r in rules
                if r.startswith(("-", "*"))
            ]
            if clean_bullets:
                target.positive_guidance.extend(clean_bullets[:3])
            elif rules:
                target.positive_guidance.extend([r for r in rules if len(r) < 50][:3])
        except Exception:
            pass

    # 3. 基线文风指纹
    baseline_fingerprint = root / ".webnovel" / "style-profile" / "baseline.json"
    if baseline_fingerprint.is_file():
        try:
            fp_data = json.loads(baseline_fingerprint.read_text(encoding="utf-8"))
            raw_sources["baseline_fingerprint"] = fp_data
            avg_len = fp_data.get("avg_sentence_len")
            if avg_len:
                target.sentence_rhythm["baseline_avg_length"] = avg_len
        except Exception:
            pass

    target.raw_sources = raw_sources
    return target
