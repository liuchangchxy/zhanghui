#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Prose Diagnostics (Issue #26).

Implements "Diagnose First":
Inspects the actual chapter text for real, concrete prose defects instead of
blindly applying 200 global rewrite transformations to the whole chapter.

Issues diagnosed:
- stock_phrase: cliché formulas (眸中闪过, 嘴角勾起一抹, 倒吸一口凉气, etc.)
- narrator_over_explanation: showing followed immediately by redundant explanation or meta-narration
- repetitive_sentence_shape: mechanical repetition of syntactic frames (e.g. 不是...而是...)
- dialogue_exposition: characters unnaturally lecturing worldbuilding in dialogue
- character_voice_flattening: dialogue homogenized into bookish essay voice
- rhythm_monotony: monotonous sentence lengths or endless choppy 1-sentence paragraphs
- book_specific_repeated_phrase: fatigue from repeating the same uncommon word repeatedly
- micro_action_template: mechanical formulaic micro-actions (指节发白 + 深吸一口气 + 冷冷道)
- excessive_compression_risk: chapter already too brief or at risk of telegraphic staccato
"""
from __future__ import annotations

import json
import re
from collections import Counter
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional

from .prose_voice_target import VoiceTarget


@dataclass
class ProseIssue:
    issue_type: str
    location: str
    excerpt: str
    evidence: str
    suggested_intervention: str
    severity: str = "suggested"  # "high" | "suggested" | "advisory"

    @property
    def category(self) -> str:
        return self.issue_type

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class DiagnosisReport:
    total_chars: int
    paragraph_count: int
    issues: List[ProseIssue] = field(default_factory=list)
    issue_counts_by_type: Dict[str, int] = field(default_factory=dict)
    summary: str = ""

    @property
    def is_clean(self) -> bool:
        return len(self.issues) == 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "total_chars": self.total_chars,
            "paragraph_count": self.paragraph_count,
            "issues": [i.to_dict() for i in self.issues],
            "issue_counts_by_type": self.issue_counts_by_type,
            "summary": self.summary,
        }

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=indent)

    def format_markdown_report(self) -> str:
        lines = [
            "### 章节正文质量诊断报告 (Prose Diagnosis)",
            f"- 总字数: {self.total_chars} | 段落数: {self.paragraph_count} | 发现问题数: {len(self.issues)}",
        ]
        if not self.issues:
            lines.append("- ✅ 未发现高频模板腔或明显 AI 套话，正文表达健康。")
            return "\n".join(lines)

        lines.append("\n| 问题类型 | 位置 | 摘录 | 诊断依据 | 建议干预 |")
        lines.append("|---|---|---|---|---|")
        for iss in self.issues:
            excerpt_clean = iss.excerpt.replace("\n", " ").strip()
            if len(excerpt_clean) > 25:
                excerpt_clean = excerpt_clean[:22] + "..."
            lines.append(
                f"| `{iss.issue_type}` | {iss.location} | {excerpt_clean} | {iss.evidence} | {iss.suggested_intervention} |"
            )
        return "\n".join(lines)


# Stock phrases catalogue
STOCK_PATTERNS = [
    (r"眸中闪过(?:一抹|一丝|一道)?", "stock_phrase", "陈词滥调神态描写", "替换为个性化真实神态或直接推进动作"),
    (r"嘴角勾起(?:一抹|一丝)?(?:冷笑|微笑|弧度)?", "stock_phrase", "陈词滥调神态描写", "改为具体言行反应"),
    (r"倒吸(?:了)?一口(?:冷|凉)气", "stock_phrase", "泛滥的震惊套话", "改为动作凝滞或真实战术反应"),
    (r"如遭雷击", "stock_phrase", "夸张空泛的震惊模板", "描写具体的生理失控或认知断裂"),
    (r"一时间，?(?:空气仿佛凝固|气氛陷入沉寂)", "stock_phrase", "环境静止套话", "保留自然停顿即可，无需元叙述感叹"),
    (r"仿佛(?:整个世界|万物)?(?:都在这一刻|在这一瞬间)?(?:静止|凝固)", "stock_phrase", "宏大化静止套话", "让场景自然推进，避免元叙述抒情"),
    (r"(?:不由得|禁不住|情不自禁地)", "stock_phrase", "弱化角色自主性的机械副词", "删去副词，直接写行动或决断"),
    (r"在这一刻，?", "stock_phrase", "时间膨胀套话", "直接陈述事件，避免元叙述强调"),
    (r"(?:总而言之|不得不说|值得注意的是|可以说，?)", "narrator_over_explanation", "分析报告型旁白元叙述", "删去旁白总结，让场景自己呈现"),
    (r"(?:心中|心底)(?:暗自|暗暗)?(?:想到|思忖|思索)", "narrator_over_explanation", "心理标签冗余元叙述", "直接写所思内容或通过行为呈现"),
    (r"(?:正如你所知|你知道的，早在|正如前文所说|你难道忘(?:记)?了)", "dialogue_exposition", "对白背景说明书化", "融入角色真实意图冲突中呈现"),
]


def diagnose_prose(text: str, voice_target: Optional[VoiceTarget] = None) -> DiagnosisReport:
    """Diagnose chapter prose and output structured targeted issues."""
    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    if not paragraphs:
        paragraphs = [p.strip() for p in text.splitlines() if p.strip()]

    total_chars = len(text)
    issues: List[ProseIssue] = []

    # 1. Check stock phrases and explanation markers
    for idx, para in enumerate(paragraphs, 1):
        for pattern, itype, evidence, intervention in STOCK_PATTERNS:
            matches = list(re.finditer(pattern, para))
            for m in matches:
                start = max(0, m.start() - 10)
                end = min(len(para), m.end() + 15)
                excerpt = para[start:end]
                issues.append(
                    ProseIssue(
                        issue_type=itype,
                        location=f"第{idx}段",
                        excerpt=excerpt,
                        evidence=evidence,
                        suggested_intervention=intervention,
                        severity="high" if itype == "stock_phrase" else "suggested",
                    )
                )

    # 2. Check repetitive sentence frames ("不是...而是...")
    bushi_pattern = re.compile(r"不是[^，。！？]+，?而是[^。！？]+")
    for idx, para in enumerate(paragraphs, 1):
        bushi_matches = bushi_pattern.findall(para)
        if len(bushi_matches) >= 1:
            issues.append(
                ProseIssue(
                    issue_type="repetitive_sentence_shape",
                    location=f"第{idx}段",
                    excerpt=bushi_matches[0],
                    evidence=f"段落出现'不是...而是...'议论文对仗句式",
                    suggested_intervention="打破对仗句式，改用直接叙述或动作呈现",
                    severity="suggested",
                )
            )

    # 3. Check micro-action formula ("指节发白", "瞳孔微缩", "缓缓吐出一口浊气")
    micro_action_pattern = re.compile(r"(?:指节(?:微微)?捏得发白|牙关紧咬|额角青筋暴起|瞳孔(?:微|微微)?(?:缩|一缩)|缓缓吐出一口(?:浊|清)气)")
    for idx, para in enumerate(paragraphs, 1):
        matches = micro_action_pattern.findall(para)
        if len(matches) >= 1:
            issues.append(
                ProseIssue(
                    issue_type="micro_action_template",
                    location=f"第{idx}段",
                    excerpt=matches[0],
                    evidence="出现高频生理微动作模板",
                    suggested_intervention="保留主要动作，删去多余的生理模板套话",
                    severity="suggested",
                )
            )

    # 4. Check rhythm monotony: excessive 1-sentence paragraphs
    short_para_count = sum(1 for p in paragraphs if len(p) < 30 and not p.startswith("“") and not p.startswith('"'))
    if len(paragraphs) >= 15 and short_para_count / len(paragraphs) > 0.6:
        issues.append(
            ProseIssue(
                issue_type="rhythm_monotony",
                location="全篇段落结构",
                excerpt=f"单句短段比例高达 {short_para_count}/{len(paragraphs)}",
                evidence="通篇极度碎片化、单句成段，产生严重的电报体/口吃感，破坏呼吸感",
                suggested_intervention="适度合并具有连续语意、动作或描写的短段，恢复段落呼吸",
                severity="high",
            )
        )

    # 5. Check excessive compression risk
    if total_chars < 1200 and total_chars > 0:
        issues.append(
            ProseIssue(
                issue_type="excessive_compression_risk",
                location="全文篇幅",
                excerpt=f"当前字数仅 {total_chars} 字",
                evidence="篇幅显著过短，存在过度压缩、缺乏场景沉浸与过渡呼吸的风险",
                suggested_intervention="扩充场景具体感官反馈与角色内心，避免只保留功能性骨架",
                severity="advisory",
            )
        )

    # 6. Check book-specific repeated phrase fatigue (non-stop repetition of certain content words)
    words = re.findall(r"[\u4e00-\u9fa5]{2,4}", text)
    word_counts = Counter(words)
    # Ignore common grammatical stop-words
    ignored = {"什么", "这样", "只见", "随后", "不过", "如果", "虽然", "自己", "这个", "那个", "此时", "如何", "一般", "现在", "已经", "知道", "没有"}
    for word, count in word_counts.most_common(10):
        if word not in ignored and count >= 8 and len(word) >= 2:
            issues.append(
                ProseIssue(
                    issue_type="book_specific_repeated_phrase",
                    location="全篇词频",
                    excerpt=f"词语「{word}」出现 {count} 次",
                    evidence="特定实词短时间内高频复现，易引起读者审美疲劳",
                    suggested_intervention=f"适度替换或省略词语「{word}」的重复提及",
                    severity="advisory",
                )
            )
            break

    counts_by_type: Dict[str, int] = {}
    for iss in issues:
        counts_by_type[iss.issue_type] = counts_by_type.get(iss.issue_type, 0) + 1

    summary = f"检测到 {len(issues)} 处需定向干预项。" if issues else "未检测到显著表达瑕疵。"

    return DiagnosisReport(
        total_chars=total_chars,
        paragraph_count=len(paragraphs),
        issues=issues,
        issue_counts_by_type=counts_by_type,
        summary=summary,
    )
