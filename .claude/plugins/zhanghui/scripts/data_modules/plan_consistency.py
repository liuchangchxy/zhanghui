#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Planning-stage consistency checks (task I).

Two kinds of check, kept deliberately separate (I2):

**Deterministic** — machine-decidable, reported as blockers so the planner fixes them before
drafting:
  * chapter sequence: numbering, duplicates, order in the volume outline;
  * required chapter fields (CBN / CEN / goal / prohibitions / scene-seal fields);
  * time-anchor monotonicity taken from the volume timeline table.

**Semantic-ish, but anchored on explicit declarations** — reported as advisories with concrete
evidence and adjudication options, never as a hidden hard gate (I7):
  * **information leakage**: a chapter must not state a later chapter's protected reveal.
    A reveal is only *protectable* when the plan declares it, so this check reads explicit
    declarations — the outline pointing at 「第N章…反转/真相/揭示」, the volume foreshadow table's
    中层/深层 rows, and the setting files' reveal lines — and then looks for the declared
    reveal's own wording appearing in an *earlier* chapter.

The real acceptance failure (chapter 2 asserting the chapter-8 location reveal) could only be
caught deterministically *after* the protection exists as data. So:

* **flags** are only ever raised against an *explicit* declaration — the outline pointing at a
  later chapter's 反转/真相/揭示, or an author-maintained protection entry. Nothing is guessed,
  so the check has no false positives and will not become a gate people learn to ignore;
* separately, the check **derives candidate protections** from the setting files and the
  foreshadow table and reports them as a checklist for the author to confirm. Candidate terms
  must be maximal, at least 3 characters, and appear in at most two chapters — that filter is
  what keeps character names and incidental phrasing out.

Measured on the reference project this yields a handful of precise candidates and zero
spurious flags. A general "does this early chapter semantically leak a later reveal" detector
is *not* implemented here: every deterministic approximation tried during this work either
missed the real case or produced dozens of false positives, and fabricating such a gate would
make the planner noisier without making it safer. That limitation is reported as a residual
risk rather than papered over.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple


SCHEMA_VERSION = "plan-consistency/v1"

BLOCKER = "blocker"
ADVISORY = "advisory"

# fields every chapter outline must state for the write/review chain to have a contract
REQUIRED_CHAPTER_FIELDS: Tuple[Tuple[str, str], ...] = (
    ("goal", "目标"),
    ("forbidden_zones", "本章禁区"),
    ("cbn", "CBN"),
    ("cen", "CEN"),
    ("beat_position", "beat_position"),
    ("hook_type", "hook_type"),
    ("scene_goal", "scene_goal"),
    ("scene_conflict", "scene_conflict"),
    ("sequel_decision", "sequel_decision"),
)

_REVEAL_REF_RE = re.compile(r"第\s*(\d+)\s*章[^。；;，,\n]{0,14}?(反转|真相|揭示|揭露|揭穿|谜底|秘密|悬念)")
_REVEAL_MARKER_RE = re.compile(r"反转|真相|揭示|揭露|揭穿|秘密|未公开|不公开|不载明|隐瞒|伏笔|悬念")
_CHAPTER_REF_RE = re.compile(r"第\s*(\d+)\s*章")
_NUMBER_TOKEN_RE = re.compile(r"-?\d+")
_CJK_RUN_RE = re.compile(r"[一-鿿]{2,}")

_CANDIDATE_STOPWORDS = frozenset(
    {
        "本章变化", "未闭合问题", "结构化节点", "必须覆盖节点", "本章禁区", "反派层级",
        "新增 craft 必填字段", "目标", "阻力", "代价", "核心冲突", "钩子", "章末未闭合问题",
        "不得", "不能", "已经", "之后", "之前", "以及", "并且", "但是", "因为", "所以",
    }
)


# --------------------------------------------------------------------------- #
# result model
# --------------------------------------------------------------------------- #


@dataclass
class Finding:
    code: str
    severity: str
    chapter: Optional[int]
    message: str
    evidence: Dict[str, Any] = field(default_factory=dict)
    options: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "code": self.code,
            "severity": self.severity,
            "chapter": self.chapter,
            "message": self.message,
            "evidence": self.evidence,
            "options": list(self.options),
        }


def _outline_sections(
    project_root: Path, volume: int
) -> Tuple[Optional[Path], Dict[int, str], List[int]]:
    """Return `(outline_path, {chapter: section}, chapters_in_file_order)`."""
    try:
        from chapter_outline_loader import _find_volume_outline_file
        from chapter_paths import find_outline_chapter_section, iter_outline_chapter_headings
    except ImportError:  # pragma: no cover
        from scripts.chapter_outline_loader import _find_volume_outline_file
        from scripts.chapter_paths import find_outline_chapter_section, iter_outline_chapter_headings

    outline_dir = Path(project_root) / "大纲"
    candidates = [
        outline_dir / f"第{volume}卷-详细大纲.md",
        outline_dir / f"第{volume}卷 - 详细大纲.md",
        outline_dir / f"第{volume}卷 详细大纲.md",
    ]
    path = next((item for item in candidates if item.is_file()), None)
    if path is None:
        path = _find_volume_outline_file(Path(project_root), (volume - 1) * 50 + 1)
    if path is None or not path.is_file():
        return None, {}, []

    text = path.read_text(encoding="utf-8")
    sections: Dict[int, str] = {}
    order: List[int] = []
    for heading in iter_outline_chapter_headings(text):
        if heading.num in sections:
            continue
        section = find_outline_chapter_section(text, heading.num)
        if section and not section.startswith("⚠️"):
            sections[heading.num] = section
            order.append(heading.num)
    return path, sections, order


def _directive(section: str) -> Dict[str, Any]:
    try:
        from chapter_outline_loader import parse_chapter_execution_directive
    except ImportError:  # pragma: no cover
        from scripts.chapter_outline_loader import parse_chapter_execution_directive

    return parse_chapter_execution_directive(section) or {}


# --------------------------------------------------------------------------- #
# deterministic checks
# --------------------------------------------------------------------------- #


def check_chapter_sequence(chapters: Sequence[int], *, expected_range: Optional[Tuple[int, int]] = None) -> List[Finding]:
    findings: List[Finding] = []
    if not chapters:
        findings.append(
            Finding(
                code="outline_empty",
                severity=BLOCKER,
                chapter=None,
                message="卷详细大纲里没有解析出任何章标题。",
                options=["确认章标题独占一行且写成 `## 第N章：标题`"],
            )
        )
        return findings

    duplicates = sorted({n for n in chapters if list(chapters).count(n) > 1})
    if duplicates:
        findings.append(
            Finding(
                code="outline_duplicate_chapters",
                severity=BLOCKER,
                chapter=duplicates[0],
                message=f"章纲里出现重复章号：{duplicates}",
                evidence={"chapters": list(chapters), "duplicates": duplicates},
                options=["删除或合并重复的章小节"],
            )
        )

    ordered = list(chapters)
    if ordered != sorted(ordered):
        findings.append(
            Finding(
                code="outline_out_of_order",
                severity=BLOCKER,
                chapter=None,
                message="章纲里的章号顺序不是递增的。",
                evidence={"chapters": ordered},
                options=["按章号重新排列章小节"],
            )
        )

    unique = sorted(set(ordered))
    if unique:
        gaps = [n for n in range(unique[0], unique[-1] + 1) if n not in set(unique)]
        if gaps:
            findings.append(
                Finding(
                    code="outline_chapter_gaps",
                    severity=BLOCKER,
                    chapter=gaps[0],
                    message=f"章号不连续，缺少：{gaps}",
                    evidence={"missing": gaps, "chapters": unique},
                    options=["补齐缺失章小节", "确认这是有意的跳号并在规划中说明"],
                )
            )

    if expected_range:
        start, end = expected_range
        outside = [n for n in unique if n < start or n > end]
        if outside:
            findings.append(
                Finding(
                    code="outline_outside_planned_range",
                    severity=BLOCKER,
                    chapter=outside[0],
                    message=f"章号超出本卷计划的 {start}-{end} 范围：{outside}",
                    evidence={"planned_range": [start, end], "outside": outside},
                    options=["修正章号", "更新 state.json 的 volumes_planned 章节范围"],
                )
            )
    return findings


def check_required_fields(sections: Dict[int, str]) -> List[Finding]:
    findings: List[Finding] = []
    for chapter in sorted(sections):
        directive = _directive(sections[chapter])
        missing = [label for key, label in REQUIRED_CHAPTER_FIELDS if not directive.get(key)]
        if missing:
            findings.append(
                Finding(
                    code="outline_chapter_missing_fields",
                    severity=BLOCKER,
                    chapter=chapter,
                    message=f"第{chapter}章章纲缺少必需字段：{'、'.join(missing)}",
                    evidence={"chapter": chapter, "missing": missing},
                    options=[f"按模板补齐 {label}" for label in missing]
                    + ["若字段确实不适用，写入「无」并在本章说明中记录"],
                )
            )
    return findings


def parse_timeline_anchors(timeline_text: str) -> List[Tuple[int, int]]:
    """Extract `(chapter, ordinal)` time anchors from a volume timeline table.

    Recognises `D-30` / `第3天` / `2016-03-17` style anchors and maps them to a comparable
    ordinal so monotonicity can be checked.
    """
    anchors: List[Tuple[int, int]] = []
    for raw_line in str(timeline_text or "").splitlines():
        line = raw_line.strip()
        if not line.startswith("|"):
            continue
        cells = [cell.strip() for cell in line.strip("|").split("|")]
        if len(cells) < 2:
            continue
        chapter_match = re.search(r"第\s*(\d+)\s*章", cells[0])
        if not chapter_match:
            continue
        chapter = int(chapter_match.group(1))
        anchor_cell = " ".join(cells[1:])
        ordinal = _anchor_ordinal(anchor_cell)
        if ordinal is not None:
            anchors.append((chapter, ordinal))
    return sorted(anchors)


def _anchor_ordinal(text: str) -> Optional[int]:
    day_match = re.search(r"D\s*[-−]\s*(\d+)", text)
    if day_match:
        return -int(day_match.group(1))
    day_match = re.search(r"D\s*\+\s*(\d+)", text)
    if day_match:
        return int(day_match.group(1))
    day_match = re.search(r"第\s*(\d+)\s*(?:天|日)", text)
    if day_match:
        return int(day_match.group(1))
    date_match = re.search(r"(\d{4})\s*[-/年]\s*(\d{1,2})\s*[-/月]\s*(\d{1,2})", text)
    if date_match:
        year, month, day = (int(part) for part in date_match.groups())
        return year * 10000 + month * 100 + day
    numbers = _NUMBER_TOKEN_RE.findall(text)
    if len(numbers) == 1:
        return int(numbers[0])
    return None


def check_time_anchor_monotonic(anchors: Sequence[Tuple[int, int]]) -> List[Finding]:
    findings: List[Finding] = []
    previous: Optional[Tuple[int, int]] = None
    for chapter, ordinal in anchors:
        if previous is not None and ordinal < previous[1]:
            findings.append(
                Finding(
                    code="timeline_not_monotonic",
                    severity=BLOCKER,
                    chapter=chapter,
                    message=(
                        f"时间线倒退：第{previous[0]}章的锚点晚于第{chapter}章"
                        f"（{previous[1]} > {ordinal}）"
                    ),
                    evidence={"previous_chapter": previous[0], "previous": previous[1],
                              "chapter": chapter, "current": ordinal},
                    options=["修正时间线表锚点", "确认倒叙需要在时间线表中显式标注"],
                )
            )
        previous = (chapter, ordinal)
    return findings


# --------------------------------------------------------------------------- #
# reveal protection (semantic-ish, declaration-anchored, advisory)
# --------------------------------------------------------------------------- #


def _cjk_candidates(text: str) -> set[str]:
    candidates: set[str] = set()
    for run in _CJK_RUN_RE.findall(str(text or "")):
        if len(run) < 2:
            continue
        candidates.add(run)
        for length in range(2, min(len(run), 10) + 1):
            candidates.add(run[:length])
            candidates.add(run[-length:])
    return {item for item in candidates if item not in _CANDIDATE_STOPWORDS}


def _reveal_field_text(section: str) -> str:
    directive = _directive(section)
    keys = ("chapter_change", "hook", "sequel_decision", "cen", "cbn", "scene_resolution")
    return " ".join(str(directive.get(key) or "") for key in keys)


def declared_reveal_protections(sections: Dict[int, str]) -> List[Dict[str, Any]]:
    """Reveals the plan itself declares, e.g. 「…为第8章位置反转保留」."""
    protections: List[Dict[str, Any]] = []
    for chapter in sorted(sections):
        for match in _REVEAL_REF_RE.finditer(sections[chapter]):
            target = int(match.group(1))
            if target <= chapter or target not in sections:
                continue
            protections.append(
                {
                    "declared_in_chapter": chapter,
                    "revealed_at_chapter": target,
                    "marker": match.group(2),
                    "declaration": match.group(0),
                    "source": f"outline:chapter_{chapter}",
                }
            )
    return protections


def _chapter_frequency(term: str, sections: Dict[int, str]) -> int:
    return sum(1 for section in sections.values() if term in section)


def _maximal_terms(text: str, *, min_length: int = 3, max_length: int = 12) -> set[str]:
    """Longest CJK runs (and their long prefixes/suffixes) from a source line.

    Substrings are kept only to allow partial overlap with chapter wording, but every candidate
    that is a substring of another candidate from the same line is dropped — that is what
    removes fragments like 「许知」 out of 「许知远」.
    """
    raw: set[str] = set()
    for run in _CJK_RUN_RE.findall(str(text or "")):
        for length in range(min_length, min(len(run), max_length) + 1):
            for start in range(0, len(run) - length + 1):
                raw.add(run[start:start + length])
    return {term for term in raw if term not in _CANDIDATE_STOPWORDS}


def _prune_terms(terms: Iterable[str]) -> List[str]:
    kept = [term for term in terms if len(term) >= 3]
    return [term for term in kept if not any(term != other and term in other for other in kept)]


# Outline template boilerplate: these are structure, not story content.
_FORMULAIC_TERMS = frozenset(
    {
        "章开端", "章收束", "章目标", "章阻力", "章冲突", "章变化", "章钩子", "章决定",
        "下章目标", "本章变化", "本章禁区", "必须覆盖节点", "结构化节点", "见 story_craft",
        "主角", "结果", "字段", "本章", "上章",
    }
)


def shared_runs(left: str, right: str, *, min_length: int = 3, max_length: int = 12) -> List[str]:
    """Longest common CJK runs between two texts.

    Using longest-common **runs** (rather than every shared substring) is what keeps this
    precise: chapter boilerplate like 「第N章开端 | 结果」 shares many short substrings with
    every other chapter, while an actual leaked reveal shares a *phrase*.
    """
    a = str(left or "")
    b = str(right or "")
    found: set[str] = set()
    for length in range(min_length, min(max_length, len(a)) + 1):
        for start in range(0, len(a) - length + 1):
            candidate = a[start:start + length]
            if not _CJK_RUN_RE.fullmatch(candidate):
                continue
            if candidate in b:
                found.add(candidate)
    return sorted(
        (term for term in found if term not in _FORMULAIC_TERMS and not any(term != o and term in o for o in found)),
        key=len,
        reverse=True,
    )


def derive_candidate_protections(project_root: Path, sections: Dict[int, str]) -> List[Dict[str, Any]]:
    """Candidate reveal protections harvested from the author's own planning material.

    Candidates are *informational*: they are printed as a confirmation checklist, never used to
    raise a finding. Each candidate must
      * occur in at least one chapter's reveal-bearing fields,
      * be maximal within its source line (no `许知` out of `许知远`),
      * be at least 3 characters, and
      * appear in at most two chapter sections (a term spread across the book is a name or a
        theme, not a reveal).
    """
    root = Path(project_root)
    candidates: List[Dict[str, Any]] = []

    def _collect(term_pool: Iterable[str], target: int, source: str, evidence: str, exempt: set[int]) -> None:
        reveal_text = _reveal_field_text(sections[target])
        shared = {term for term in term_pool if term in reveal_text}
        for term in _prune_terms(shared):
            if term in exempt:
                continue
            if _chapter_frequency(term, sections) > 2:
                continue
            candidates.append(
                {
                    "term": term,
                    "revealed_at_chapter": target,
                    "source": source,
                    "evidence": evidence,
                }
            )

    setting_dir = root / "设定集"
    if setting_dir.is_dir():
        for path in sorted(setting_dir.glob("*.md")):
            for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                if not _REVEAL_MARKER_RE.search(line):
                    continue
                for ref in _CHAPTER_REF_RE.finditer(line):
                    target = int(ref.group(1))
                    if target not in sections:
                        continue
                    exempt = {int(m.group(1)) for m in _CHAPTER_REF_RE.finditer(line)}
                    _collect(_maximal_terms(line), target, f"{path.name}:{line_no}", line.strip(), exempt)

    outline_dir = root / "大纲"
    for path in sorted(outline_dir.glob("*伏笔表.md")):
        for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if not line.strip().startswith("|"):
                continue
            cells = [cell.strip() for cell in line.strip("|").split("|")]
            if len(cells) < 7 or cells[1] not in {"中层", "深层"}:
                continue
            payoff_match = _CHAPTER_REF_RE.search(cells[5])
            if not payoff_match:
                continue
            target = int(payoff_match.group(1))
            if target not in sections:
                continue
            # a clue is *supposed* to appear in its burial chapter
            exempt = {int(m.group(1)) for m in _CHAPTER_REF_RE.finditer(cells[4])}
            _collect(_maximal_terms(cells[3]), target, f"{path.name}:{line_no}", cells[3], exempt)

    deduped: Dict[Tuple[str, int], Dict[str, Any]] = {}
    for item in candidates:
        deduped.setdefault((item["term"], item["revealed_at_chapter"]), item)
    return sorted(deduped.values(), key=lambda item: (item["revealed_at_chapter"], -len(item["term"])))


def load_declared_protections(project_root: str | Path) -> List[Dict[str, Any]]:
    """Author-maintained protection entries: {term, revealed_at_chapter, source}[]."""
    path = Path(project_root) / ".webnovel" / "intent" / "reveal_protection.json"
    if not path.is_file():
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return []
    entries = payload.get("protections") if isinstance(payload, dict) else payload
    if not isinstance(entries, list):
        return []
    out: List[Dict[str, Any]] = []
    for item in entries:
        if not isinstance(item, dict):
            continue
        term = str(item.get("term") or "").strip()
        try:
            target = int(item.get("revealed_at_chapter"))
        except (TypeError, ValueError):
            continue
        if term and target:
            out.append(
                {
                    "term": term,
                    "revealed_at_chapter": target,
                    "source": str(item.get("source") or "reveal_protection.json"),
                    "evidence": str(item.get("evidence") or ""),
                }
            )
    return out


def check_reveal_protection(
    sections: Dict[int, str],
    protections: Iterable[Dict[str, Any]],
    *,
    severity: str = ADVISORY,
) -> List[Finding]:
    """Flag chapters that state a protected reveal before its reveal chapter."""
    findings: List[Finding] = []
    for protection in protections:
        term = str(protection.get("term") or "").strip()
        target = int(protection.get("revealed_at_chapter") or 0)
        if not term or not target:
            continue
        for chapter in sorted(sections):
            if chapter >= target:
                continue
            if term in sections[chapter]:
                line = next(
                    (raw.strip() for raw in sections[chapter].splitlines() if term in raw),
                    "",
                )
                findings.append(
                    Finding(
                        code="intent_reveal_leak",
                        severity=severity,
                        chapter=chapter,
                        message=(
                            f"第{chapter}章章纲出现第{target}章的（受保护）反转用词「{term}」——"
                            "可能提前透光后续反转，读者/角色在本章就会知道本该后置的信息。"
                        ),
                        evidence={
                            "term": term,
                            "revealed_at_chapter": target,
                            "early_chapter": chapter,
                            "early_line": line,
                            "protection_source": protection.get("source", ""),
                            "protection_evidence": protection.get("evidence", ""),
                        },
                        options=[
                            f"从第{chapter}章改写掉「{term}」，改为不载明/模糊表述",
                            f"确认该信息在第{chapter}章对角色是可知的，并把保护条目降级（写回规划说明）",
                            f"把反转提前到第{chapter}章，并同步第{target}章与全书规划",
                        ],
                    )
                )
    return findings


# --------------------------------------------------------------------------- #
# orchestration
# --------------------------------------------------------------------------- #


def run_plan_consistency(
    project_root: str | Path,
    *,
    volume: int = 1,
    expected_range: Optional[Tuple[int, int]] = None,
) -> Dict[str, Any]:
    root = Path(project_root)
    outline_path, sections, file_order = _outline_sections(root, volume)

    findings: List[Finding] = []
    if outline_path is None:
        findings.append(
            Finding(
                code="outline_missing",
                severity=BLOCKER,
                chapter=None,
                message=f"找不到第{volume}卷详细大纲。",
                options=["先运行 /webnovel-plan 生成 大纲/第{volume}卷-详细大纲.md"],
            )
        )
        return _report(root, volume, outline_path, {}, findings, [])

    findings.extend(check_chapter_sequence(file_order or sorted(sections), expected_range=expected_range))
    findings.extend(check_required_fields(sections))

    timeline = root / "大纲" / f"第{volume}卷-时间线.md"
    if timeline.is_file():
        findings.extend(check_time_anchor_monotonic(parse_timeline_anchors(timeline.read_text(encoding="utf-8"))))

    # Findings come only from *explicit* declarations: the outline naming a later chapter's
    # reveal, or an author-maintained protection entry. Derived candidates are reported as a
    # confirmation checklist (see `candidate_protections`), never as findings.
    declared = declared_reveal_protections(sections)
    explicit_protections: List[Dict[str, Any]] = []
    for declaration in declared:
        # A declaration names the reveal chapter but not the term; bind the terms the declaring
        # chapter shares with that chapter's reveal wording. The same precision filter as the
        # candidate derivation applies, otherwise character names (「许知远」) and template
        # boilerplate (「下章目标」) would swamp the report.
        target = int(declaration["revealed_at_chapter"])
        residing = int(declaration["declared_in_chapter"])
        for term in shared_runs(_reveal_field_text(sections[residing]), _reveal_field_text(sections[target])):
            frequency = _chapter_frequency(term, sections)
            # a reveal term is rare by definition: present in this pair and at most one more
            # chapter. Anything spread through the whole volume is template boilerplate.
            if frequency > 2 or frequency >= len(sections):
                continue
            explicit_protections.append(
                {
                    "term": term,
                    "revealed_at_chapter": target,
                    "source": declaration["source"],
                    "evidence": declaration["declaration"],
                }
            )
    explicit_protections.extend(load_declared_protections(root))
    findings.extend(check_reveal_protection(sections, explicit_protections, severity=ADVISORY))
    candidates = derive_candidate_protections(root, sections)

    return _report(root, volume, outline_path, sections, findings, candidates)


def _report(
    root: Path,
    volume: int,
    outline_path: Optional[Path],
    sections: Dict[int, str],
    findings: Sequence[Finding],
    candidates: Sequence[Dict[str, Any]],
) -> Dict[str, Any]:
    blockers = [f for f in findings if f.severity == BLOCKER]
    advisories = [f for f in findings if f.severity != BLOCKER]
    return {
        "schema_version": SCHEMA_VERSION,
        "project_root": str(root),
        "volume": volume,
        "outline": outline_path.relative_to(root).as_posix() if outline_path else "",
        "chapters_found": sorted(sections),
        "ok": not blockers,
        "policy_action": "REJECT" if blockers else ("ALLOW_WITH_ADVISORY" if advisories else "ALLOW"),
        "blockers": [f.to_dict() for f in blockers],
        "advisories": [f.to_dict() for f in advisories],
        "candidate_protections": list(candidates),
        "candidate_protection_note": (
            "候选保护项仅供作者确认（写入 .webnovel/intent/reveal_protection.json 或本章禁区后才会产生 finding）；"
            "本检查不对未声明的语义泄露下判断。"
        ),
    }


def format_report_text(report: Dict[str, Any]) -> str:
    lines = [
        f"plan-consistency volume={report.get('volume')} ok={report.get('ok')} "
        f"policy_action={report.get('policy_action')}",
        f"  chapters: {report.get('chapters_found')}",
    ]
    for item in report.get("blockers") or []:
        lines.append(f"  BLOCKER [{item['code']}] {item['message']}")
    for item in report.get("advisories") or []:
        lines.append(f"  ADVISORY [{item['code']}] {item['message']}")
        for option in item.get("options") or []:
            lines.append(f"      option: {option}")
    for item in report.get("candidate_protections") or []:
        lines.append(
            f"  candidate protection: 「{item['term']}」 revealed at ch{item['revealed_at_chapter']} "
            f"({item['source']})"
        )
    return "\n".join(lines)
