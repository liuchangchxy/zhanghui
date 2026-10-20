#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Normal-use local revision planning (task E).

Why this module exists
----------------------
Reviewer findings used to be actionable only through `revise_chapter.py`, which
located problems exclusively by `## §N` headings. Real chapters do not have those
headings, and `RejectionContract` defaulted to `blocking=True` findings only — while a
normal Reviewer's output is mostly non-blocking advice. The net effect was that any
reviewer finding could only be fixed by re-drafting the whole chapter and paying for a
full re-review.

This module is the missing middle: it turns a Reviewer JSON into a **targeted revision
plan** that says exactly which spans of prose must change, why, and how far the edit is
allowed to reach. The actual rewriting is done by the *host* model (Claude Code); nothing
here assumes a paid API key. Verification is deterministic and happens afterwards:

    Reviewer JSON  ->  plan (targets + spans)  ->  host edits  ->  apply  ->  verify
                                                                          |
                                            boundary + resolution check --+

The existing governance chain is untouched: after a revision the working draft is
re-ingested (`runtime ingest-draft`) to get a fresh draft identity, re-reviewed, and only
then may it reach `runtime commit`.
"""
from __future__ import annotations

import difflib
import hashlib
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple


SCHEMA_VERSION = "revision-plan/v1"

# kinds of revision target — drives which safety path the caller must use
KIND_STYLE_ONLY = "STYLE_ONLY"
KIND_LOCAL_FACT = "LOCAL_FACT"
KIND_STRUCTURAL = "STRUCTURAL"
KIND_CANON_HISTORY = "CANON_HISTORY"

# locator strategies
LOC_PARAGRAPH = "paragraph"
LOC_LINE = "line"
LOC_SECTION = "section"
LOC_QUOTE = "quote"
LOC_CHAPTER = "chapter"
LOC_UNRESOLVED = "unresolved"

_STYLE_CATEGORIES = {"ai_flavor", "pacing", "beat_compliance", "foreshadow_compliance"}

# --------------------------------------------------------------------------- #
# Finding ownership
# --------------------------------------------------------------------------- #
# Not every finding can be fixed by editing prose. A missing
# `do_not_copy_check.json` is a pipeline artifact problem, an unlinked foreshadow loop is
# ledger bookkeeping, and a rhythm-curve advisory is a heuristic opinion — feeding any of
# them to a prose editor makes the model polish the same sentences round after round while
# the actual cause sits untouched. Each finding is therefore routed to exactly one owner,
# and only `PROSE_EDIT` findings enter the automatic revision plan.
OWNER_PROSE_EDIT = "PROSE_EDIT"
OWNER_ARTIFACT_REPAIR = "ARTIFACT_REPAIR"
OWNER_GOVERNANCE_REPAIR = "GOVERNANCE_REPAIR"
OWNER_ADVISORY = "ADVISORY"

OWNER_REPAIR_HINTS = {
    OWNER_ARTIFACT_REPAIR: "重新生成/补齐缺失的产物文件（例如重跑 review 主流程生成 do_not_copy_check.json），不要改正文。",
    OWNER_GOVERNANCE_REPAIR: "在账本/治理数据层修复（伏笔登记、loop 关联、元数据补全），不要改正文。",
    OWNER_ADVISORY: "仅记录建议；如需采纳请显式 `--include-advisory`，不要为了清零 advisory 反复改写正文。",
}

_CRAFT_CATEGORIES = {"beat_compliance", "foreshadow_compliance", "pacing"}

# Findings that name a *generated artifact* rather than a prose defect.
_ARTIFACT_REF_RE = re.compile(
    r"(do_not_copy_check\.json|[a-z_]+_(?:result|check|audit|report)\.json|\*_result\.json)",
    re.IGNORECASE,
)
_ARTIFACT_MISSING_RE = re.compile(
    r"(不存在|缺失|未找到|无法读取|格式错误|missing|not found|invalid json|unreadable)",
    re.IGNORECASE,
)

# Findings that are bookkeeping/ledger metadata rather than prose.
_GOVERNANCE_RE = re.compile(
    r"(legacy_unlinked|loop_id|伏笔元数据|元数据|账本|ledger|未关联|未绑定|未登记|"
    r"registration|bookkeeping)",
    re.IGNORECASE,
)


def classify_finding_owner(issue: Dict[str, Any]) -> str:
    """Route one Reviewer finding to the layer that can actually fix it.

    Only `PROSE_EDIT` findings belong in a targeted prose revision. Everything else is
    reported with its owner and a repair hint, so the loop converges on the real cause
    instead of rewriting the same paragraph again.
    """
    if not isinstance(issue, dict):
        return OWNER_ADVISORY

    category = str(issue.get("category") or "other")
    authority = str(issue.get("authority") or "")
    gate_id = str(issue.get("gate_id") or "")
    description = str(issue.get("description") or "")
    evidence = str(issue.get("evidence") or "")
    fix_hint = str(issue.get("fix_hint") or "")
    text = " ".join((description, evidence, fix_hint))

    # Artifact-level problems: the finding is about a file the pipeline was supposed to
    # produce, so no amount of prose editing can make it disappear.
    if _ARTIFACT_REF_RE.search(text) and _ARTIFACT_MISSING_RE.search(text):
        return OWNER_ARTIFACT_REPAIR

    # Ledger / metadata bookkeeping (e.g. a foreshadow loop that cannot be linked to an id).
    if _GOVERNANCE_RE.search(text):
        return OWNER_GOVERNANCE_REPAIR

    # Craft & methodology heuristics are advisory by construction.
    if (
        authority == "CRAFT_HEURISTIC"
        or gate_id.startswith("story_craft.")
        or category in _CRAFT_CATEGORIES
    ):
        return OWNER_ADVISORY

    return OWNER_PROSE_EDIT

_SECTION_HEADING_RE = re.compile(r"^##\s+(§\d+)\b", re.MULTILINE)
_PARAGRAPH_REF_RE = re.compile(r"第\s*(\d+)\s*(?:[-—~至]\s*(\d+)\s*)?段")
_LINE_REF_RE = re.compile(r"第\s*(\d+)\s*(?:[-—~至]\s*(\d+)\s*)?行")
_LINE_REF_EN_RE = re.compile(r"\blines?\s+(\d+)\s*(?:[-—~]\s*(\d+))?", re.IGNORECASE)
_SECTION_REF_RE = re.compile(r"§\s*(\d+)\s*(?:[-—~]\s*§?\s*(\d+))?")
_CHAPTER_REF_RE = re.compile(r"^\s*chapter\s+\d+\s*$", re.IGNORECASE)

_QUOTE_PATTERNS = (
    re.compile(r"「([^」]{2,120})」"),
    re.compile(r"『([^』]{2,120})』"),
    re.compile(r"“([^”]{2,120})”"),
    re.compile(r"『([^』]{2,120})』"),
    re.compile(r"`([^`]{2,120})`"),
    re.compile(r"\"([^\"]{2,120})\""),
    re.compile(r"'([^']{2,120})'"),
)


class RevisionApplyError(ValueError):
    """Raised when a host edit cannot be applied unambiguously / against the wrong draft."""


class RevisionBindingError(RevisionApplyError):
    """Raised when a review/plan is not bound to the draft it is being used on."""


def sha256_text(text: str) -> str:
    return hashlib.sha256(str(text).encode("utf-8")).hexdigest()


def _prose_subject_sha256(text: str) -> str:
    from .reconciliation import prose_subject_sha256

    return prose_subject_sha256(text)


# --------------------------------------------------------------------------- #
# Draft identity / version protection
# --------------------------------------------------------------------------- #
# A revision plan is only meaningful for the exact draft it was built from. Two things make
# that checkable:
#
#   * the draft's *content* hash: `ingest_draft` stores `draft_fingerprint = sha256(prose)`,
#     so the working draft file on disk must hash to the active draft's fingerprint — if it
#     does not, the file has unregistered edits and any plan built from it is unsound;
#   * the reviewer result's declared identity, when it carries one (`draft_id` /
#     `draft_fingerprint`).
#
# Before this, `revise apply` only compared the individual planned spans, so a plan made
# against draft A could still be applied to an unrelated draft B as long as B happened to
# contain the same sentences.

ACTIVE_DRAFT_FILE = "draft.json"


def resolve_active_draft_identity(project_root: str | Path, chapter: int) -> Dict[str, Any]:
    """Read the active ingested draft identity for a chapter from the runtime registry."""
    path = Path(project_root) / ".webnovel" / "runtime" / f"chapter_{int(chapter):03d}" / ACTIVE_DRAFT_FILE
    if not path.is_file():
        return {"available": False, "reason": "no_active_draft", "path": str(path)}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {"available": False, "reason": f"unreadable_active_draft: {exc}", "path": str(path)}
    if not isinstance(payload, dict):
        return {"available": False, "reason": "malformed_active_draft", "path": str(path)}
    prose = str(payload.get("prose") or "")
    subject_fp = str(payload.get("review_subject_fingerprint") or "")
    if not subject_fp and prose:
        # Drafts ingested before the review-subject fingerprint existed: derive it from the
        # stored prose rather than reporting the identity as unavailable.
        subject_fp = _prose_subject_sha256(prose)
    return {
        "available": True,
        "path": str(path),
        "draft_id": str(payload.get("draft_id") or ""),
        "draft_fingerprint": str(payload.get("draft_fingerprint") or ""),
        "review_subject_fingerprint": subject_fp,
    }


def check_draft_version(plan: Dict[str, Any], draft_text: str) -> None:
    """Refuse to operate on a draft that is not the one the plan was built from.

    Raises `RevisionApplyError` with a concrete repair hint instead of silently editing the
    wrong version.
    """
    expected = str(plan.get("draft_sha256") or "")
    if not expected:
        raise RevisionBindingError(
            "revision plan has no draft_sha256; regenerate it with `revise plan`"
        )
    actual = sha256_text(draft_text)
    if actual != expected:
        raise RevisionBindingError(
            "draft version mismatch: the working draft has changed since the revision plan was "
            f"built (plan={expected[:12]}, draft={actual[:12]}). "
            "重新运行 `revise plan` 生成与新草稿匹配的计划；不要把旧计划用在已变更的草稿上。"
        )
    fingerprint = str(plan.get("draft_fingerprint") or "")
    if fingerprint and fingerprint != actual:
        raise RevisionBindingError(
            "draft identity mismatch: the plan was bound to draft_fingerprint "
            f"{fingerprint[:12]} but the current draft hashes to {actual[:12]}."
        )


_REVIEW_IDENTITY_KEYS = ("draft_id", "draft_fingerprint", "review_subject_fingerprint")


def review_result_identity(reviewer_json: Dict[str, Any]) -> Dict[str, str]:
    """Pull a declared draft identity out of a reviewer result, if it carries one."""
    identity: Dict[str, str] = {}
    for key in _REVIEW_IDENTITY_KEYS:
        value = reviewer_json.get(key)
        if isinstance(value, str) and value.strip():
            identity[key] = value.strip()
    nested = reviewer_json.get("draft")
    if isinstance(nested, dict):
        for key in _REVIEW_IDENTITY_KEYS:
            value = nested.get(key)
            if isinstance(value, str) and value.strip() and key not in identity:
                identity[key] = value.strip()
    return identity


def _file_line_of(text: str, offset: int) -> int:
    """1-based physical line number of a character offset."""
    if offset <= 0:
        return 1
    return str(text).count("\n", 0, offset) + 1


# --------------------------------------------------------------------------- #
# prose segmentation
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class Paragraph:
    """A non-empty line of the chapter file.

    `index` is the 1-based paragraph number the Reviewer refers to as `第N段`; `start`/`end`
    are the character span of the paragraph *excluding* its trailing newline, so replacing a
    paragraph never silently eats the line break that follows it.

    `file_line` is the *physical* 1-based line number in the file. It differs from `index`
    whenever the file contains a heading or blank lines — the exact situation where a
    Reviewer reference like `正文第11行（第11段）` used to be resolved to the wrong paragraph.
    """

    index: int
    start: int
    end: int
    text: str
    file_line: int = 0

    @property
    def line_number(self) -> int:
        return self.index


def iter_paragraphs(text: str) -> List[Paragraph]:
    """Index non-empty lines.

    The chapter files written by this project put one narrative paragraph (or one line of
    dialogue) per line, and the Reviewer's `第N段` references line up with that indexing.
    """
    paragraphs: List[Paragraph] = []
    offset = 0
    index = 0
    for raw_line in str(text).splitlines(keepends=True):
        body = raw_line.rstrip("\r\n")
        if body.strip():
            index += 1
            start = offset
            end = offset + len(body)
            paragraphs.append(
                Paragraph(
                    index=index,
                    start=start,
                    end=end,
                    text=body,
                    file_line=_file_line_of(text, start),
                )
            )
        offset += len(raw_line)
    return paragraphs


def _section_span(text: str, section_id: str) -> Optional[Tuple[int, int]]:
    pattern = re.compile(
        rf"^(##\s+{re.escape(section_id)}(?!\d).*?)(?=^##\s|\Z)", re.MULTILINE | re.DOTALL
    )
    match = pattern.search(text)
    if not match:
        return None
    return match.start(), match.end()


def _expand_range(lo: int, hi: Optional[int]) -> Tuple[int, int]:
    if hi is None:
        return lo, lo
    return (lo, hi) if lo <= hi else (hi, lo)


# --------------------------------------------------------------------------- #
# target model
# --------------------------------------------------------------------------- #


@dataclass
class RevisionTarget:
    issue_id: str
    severity: str
    category: str
    blocking: bool
    kind: str
    location_raw: str
    locator: str
    start: int
    end: int
    line_start: int
    line_end: int
    before_text: str
    fix_hint: str
    description: str
    anchor_quote: str = ""
    ambiguity: str = ""
    resolvable: bool = True
    file_line_start: int = 0
    file_line_end: int = 0
    # Which layer owns this finding. Only PROSE_EDIT targets are meant to be rewritten here.
    owner: str = OWNER_PROSE_EDIT

    def to_dict(self) -> Dict[str, Any]:
        return {
            "issue_id": self.issue_id,
            "severity": self.severity,
            "category": self.category,
            "blocking": self.blocking,
            "kind": self.kind,
            "owner": self.owner,
            "location_raw": self.location_raw,
            "locator": self.locator,
            "start": self.start,
            "end": self.end,
            "line_start": self.line_start,
            "line_end": self.line_end,
            "before_text": self.before_text,
            "fix_hint": self.fix_hint,
            "description": self.description,
            "anchor_quote": self.anchor_quote,
            "ambiguity": self.ambiguity,
            "resolvable": self.resolvable,
            # `line_start`/`line_end` follow the Reviewer's paragraph numbering; the
            # `file_line_*` pair is the physical line in the draft file.
            "file_line_start": self.file_line_start,
            "file_line_end": self.file_line_end,
            "span_sha256": sha256_text(self.before_text),
        }

    def with_span(
        self,
        *,
        locator: str,
        start: int,
        end: int,
        line_start: int,
        line_end: int,
        before_text: str,
        kind: Optional[str] = None,
        anchor_quote: str = "",
        text: str = "",
    ) -> "RevisionTarget":
        """Return a copy carrying the same issue metadata but a concrete prose span."""
        return RevisionTarget(
            issue_id=self.issue_id,
            severity=self.severity,
            category=self.category,
            blocking=self.blocking,
            kind=kind or self.kind,
            location_raw=self.location_raw,
            locator=locator,
            start=start,
            end=end,
            line_start=line_start,
            line_end=line_end,
            before_text=before_text,
            fix_hint=self.fix_hint,
            description=self.description,
            anchor_quote=anchor_quote or self.anchor_quote,
            ambiguity=self.ambiguity,
            resolvable=True,
            file_line_start=_file_line_of(text, start),
            file_line_end=_file_line_of(text, max(start, end - 1)),
        )


def _extract_quotes(*texts: str) -> List[str]:
    found: List[str] = []
    for text in texts:
        for pattern in _QUOTE_PATTERNS:
            for match in pattern.finditer(str(text or "")):
                candidate = match.group(1).strip()
                if candidate and candidate not in found:
                    found.append(candidate)
    return found


def classify_issue_kind(issue: Dict[str, Any]) -> str:
    """Decide which fact-safety path a finding must take.

    * STYLE_ONLY   — expression-level; may be accepted through the Semantic Judge style check
    * LOCAL_FACT   — a factual correction inside the in-flight draft; must go through the
                     governed draft revision + re-review path
    * STRUCTURAL   — spans the whole chapter (or the finding has no usable anchor)
    * CANON_HISTORY— the chapter is already accepted; ordinary revision must refuse
    """
    if str(issue.get("canon_history") or "").lower() in {"1", "true", "yes"}:
        return KIND_CANON_HISTORY
    category = str(issue.get("category") or "other")
    gate_id = str(issue.get("gate_id") or "")
    if gate_id.startswith("story_craft") or category in _STYLE_CATEGORIES:
        return KIND_STYLE_ONLY
    if category in {"continuity", "setting", "character", "timeline", "logic"}:
        return KIND_LOCAL_FACT
    return KIND_LOCAL_FACT


def _deferred_entry(issue: Dict[str, Any], owner: str) -> Dict[str, Any]:
    """A finding that must NOT enter the prose revision loop, with the layer that owns it."""
    return {
        "owner": owner,
        "category": str(issue.get("category") or "other"),
        "severity": str(issue.get("severity") or "medium"),
        "blocking": bool(issue.get("blocking")),
        "location": str(issue.get("location") or ""),
        "description": str(issue.get("description") or ""),
        "repair_hint": OWNER_REPAIR_HINTS.get(owner, ""),
    }


def _issue_id(issue: Dict[str, Any], index: int) -> str:
    for key in ("issue_id", "id", "constraint_id"):
        value = issue.get(key)
        if value:
            return str(value)
    payload = json.dumps(
        [issue.get("severity"), issue.get("category"), issue.get("location"), issue.get("description")],
        ensure_ascii=False,
        sort_keys=True,
    )
    return f"issue-{index:03d}-{sha256_text(payload)[:8]}"


def _span_for_paragraphs(
    base: "RevisionTarget",
    text: str,
    paragraphs: Sequence[Paragraph],
    lo: int,
    hi: int,
    locator: str,
) -> Optional["RevisionTarget"]:
    selected = [p for p in paragraphs if lo <= p.index <= hi]
    if not selected:
        return None
    return base.with_span(
        locator=locator,
        start=selected[0].start,
        end=selected[-1].end,
        line_start=selected[0].line_number,
        line_end=selected[-1].line_number,
        before_text=text[selected[0].start:selected[-1].end],
        text=text,
    )


def _span_for_file_lines(
    base: "RevisionTarget",
    text: str,
    paragraphs: Sequence[Paragraph],
    lo: int,
    hi: int,
    locator: str,
) -> Optional["RevisionTarget"]:
    """Map a 1-based *physical file line* range to a character span.

    Reviewer locations such as `正文第11行` refer to the line numbering a reader sees in the
    file, not to the Nth non-empty paragraph. Blank lines and the chapter heading therefore
    shift the two numbering systems apart; resolving a line reference through the paragraph
    index (the old behaviour) silently edited the wrong paragraph.
    """
    selected = [p for p in paragraphs if lo <= p.file_line <= hi]
    if not selected:
        return None
    return base.with_span(
        locator=locator,
        start=selected[0].start,
        end=selected[-1].end,
        line_start=selected[0].index,
        line_end=selected[-1].index,
        before_text=text[selected[0].start:selected[-1].end],
        text=text,
    )


def _anchor_quotes(issue: Dict[str, Any]) -> List[str]:
    """Quoted text the finding itself points at, used to disambiguate locators."""
    anchors: List[str] = []
    for key in ("anchor_quote", "excerpt"):
        value = str(issue.get(key) or "").strip()
        if value:
            anchors.append(value)
    anchors.extend(
        _extract_quotes(
            str(issue.get("description") or ""),
            str(issue.get("evidence") or ""),
            str(issue.get("fix_hint") or ""),
            json.dumps(issue.get("structured_evidence") or [], ensure_ascii=False),
        )
    )
    # Keep order, drop duplicates and trivially short fragments.
    return [a for a in dict.fromkeys(anchors) if len(a) >= 2]


def _select_candidate(
    resolved: Sequence[Tuple[str, "RevisionTarget"]],
    anchors: Sequence[str],
) -> Optional[Tuple[str, "RevisionTarget"]]:
    """Pick one locator among candidates that disagree.

    Rules:
    * identical spans -> first candidate;
    * a quoted anchor contained by exactly one span -> that span;
    * none/ambiguous -> ``None`` so the caller can mark the finding unresolvable instead of
      silently editing the wrong paragraph.
    """
    if len(resolved) == 1:
        return resolved[0]
    if len({(t.start, t.end) for _, t in resolved}) == 1:
        return resolved[0]
    scored: List[Tuple[int, str, "RevisionTarget"]] = []
    for locator, target in resolved:
        score = sum(len(anchor) for anchor in anchors if anchor in target.before_text)
        scored.append((score, locator, target))
    best = max(score for score, _, _ in scored)
    if best <= 0:
        return None
    winners = [(locator, target) for score, locator, target in scored if score == best]
    if len(winners) == 1:
        return winners[0]
    # A tie means both spans quote the finding equally well. Prefer the explicit physical
    # line reference, which is the unambiguous half of `第N行（第N段）`.
    for locator, target in winners:
        if locator == LOC_LINE:
            return locator, target
    return winners[0]


def _expand_quote_span(
    base: "RevisionTarget",
    text: str,
    paragraphs: Sequence[Paragraph],
    quote: str,
) -> Tuple[Optional["RevisionTarget"], str]:
    """Locate a quote, expanding to its enclosing paragraph.

    Returns (target, ambiguity). Ambiguity is reported instead of guessing a position:
    replacing the wrong occurrence would silently corrupt prose.
    """
    if not quote:
        return None, ""
    occurrences = [m.start() for m in re.finditer(re.escape(quote), text)]
    if not occurrences:
        return None, "quote_not_found"
    hit_paragraphs: Dict[int, Paragraph] = {}
    for occurrence in occurrences:
        for paragraph in paragraphs:
            if paragraph.start <= occurrence < paragraph.end:
                hit_paragraphs[paragraph.index] = paragraph
                break
    if not hit_paragraphs:
        return None, "quote_not_in_paragraph"
    if len(hit_paragraphs) > 1:
        # The same wording appears in more than one paragraph: refuse to guess.
        return None, "ambiguous_quote"
    paragraph = next(iter(hit_paragraphs.values()))
    return (
        base.with_span(
            locator=LOC_QUOTE,
            start=paragraph.start,
            end=paragraph.end,
            line_start=paragraph.line_number,
            line_end=paragraph.line_number,
            before_text=text[paragraph.start:paragraph.end],
            anchor_quote=quote,
            text=text,
        ),
        "",
    )


def locate_issue(text: str, issue: Dict[str, Any], *, index: int = 0) -> RevisionTarget:
    """Resolve one Reviewer finding to a concrete span of the working draft."""
    paragraphs = iter_paragraphs(text)
    location = str(issue.get("location") or "")
    description = str(issue.get("description") or "")
    fix_hint = str(issue.get("fix_hint") or "")
    kind = classify_issue_kind(issue)

    base = RevisionTarget(
        issue_id=_issue_id(issue, index),
        severity=str(issue.get("severity") or "medium"),
        category=str(issue.get("category") or "other"),
        blocking=bool(issue.get("blocking")),
        kind=kind,
        location_raw=location,
        locator=LOC_UNRESOLVED,
        start=0,
        end=0,
        line_start=0,
        line_end=0,
        before_text="",
        fix_hint=fix_hint,
        description=description,
    )

    candidates: List[Tuple[str, Optional[RevisionTarget], str]] = []

    # 1) legacy §N section reference
    section_match = _SECTION_REF_RE.search(location)
    if section_match:
        lo, hi = _expand_range(int(section_match.group(1)), int(section_match.group(2)) if section_match.group(2) else None)
        span_lo: Optional[int] = None
        span_hi: Optional[int] = None
        for n in range(lo, hi + 1):
            span = _section_span(text, f"§{n}")
            if span is None:
                continue
            span_lo = span[0] if span_lo is None else min(span_lo, span[0])
            span_hi = span[1] if span_hi is None else max(span_hi, span[1])
        if span_lo is not None and span_hi is not None:
            inside = [p for p in paragraphs if p.start >= span_lo and p.end <= span_hi]
            candidates.append(
                (
                    LOC_SECTION,
                    base.with_span(
                        locator=LOC_SECTION,
                        start=span_lo,
                        end=span_hi,
                        line_start=inside[0].line_number if inside else 0,
                        line_end=inside[-1].line_number if inside else 0,
                        before_text=text[span_lo:span_hi],
                        text=text,
                    ),
                    "",
                )
            )

    # 2) 第N段 / 第N-M段
    paragraph_match = _PARAGRAPH_REF_RE.search(location)
    if paragraph_match:
        lo, hi = _expand_range(
            int(paragraph_match.group(1)),
            int(paragraph_match.group(2)) if paragraph_match.group(2) else None,
        )
        target = _span_for_paragraphs(base, text, paragraphs, lo, hi, LOC_PARAGRAPH)
        candidates.append((LOC_PARAGRAPH, target, "" if target else "paragraph_out_of_range"))

    # 3) 第N行 / line N
    line_match = _LINE_REF_RE.search(location) or _LINE_REF_EN_RE.search(location)
    if line_match:
        lo, hi = _expand_range(
            int(line_match.group(1)),
            int(line_match.group(2)) if line_match.group(2) else None,
        )
        target = _span_for_file_lines(base, text, paragraphs, lo, hi, LOC_LINE)
        candidates.append((LOC_LINE, target, "" if target else "line_out_of_range"))

    # 4) exact quote carried by the finding (description / fix_hint / structured evidence)
    for quote in _extract_quotes(description, fix_hint, json.dumps(issue.get("structured_evidence") or [], ensure_ascii=False)):
        target, ambiguity = _expand_quote_span(base, text, paragraphs, quote)
        if target is not None:
            candidates.append((LOC_QUOTE, target, ""))
            break
        if ambiguity:
            candidates.append((LOC_QUOTE, None, ambiguity))

    # 5) whole-chapter reference -> structural: needs a re-draft decision, never a targeted patch
    if not candidates and _CHAPTER_REF_RE.match(location):
        candidates.append(
            (
                LOC_CHAPTER,
                base.with_span(
                    locator=LOC_CHAPTER,
                    start=0,
                    end=len(text),
                    line_start=paragraphs[0].line_number if paragraphs else 0,
                    line_end=paragraphs[-1].line_number if paragraphs else 0,
                    before_text=text,
                    kind=KIND_STRUCTURAL,
                    text=text,
                ),
                "",
            )
        )

    resolved = [(locator, target) for locator, target, _ in candidates if target is not None]
    if resolved:
        selected = _select_candidate(resolved, _anchor_quotes(issue))
        if selected is None:
            base.locator = LOC_UNRESOLVED
            base.resolvable = False
            base.ambiguity = "line_paragraph_conflict"
            return base
        locator, target = selected
        target.locator = locator
        return target

    # nothing locatable -> keep the finding visible instead of dropping it
    base.locator = LOC_UNRESOLVED
    base.resolvable = False
    base.ambiguity = next((a for _, t, a in candidates if t is None and a), "no_locator")
    return base


# --------------------------------------------------------------------------- #
# plan
# --------------------------------------------------------------------------- #


def _merge_spans(targets: Iterable[RevisionTarget]) -> List[Tuple[int, int]]:
    """Union of the *targeted* spans.

    Chapter-scope (STRUCTURAL) findings are excluded on purpose: they mean "this needs a
    re-draft decision", not "you may rewrite the whole chapter in place". Leaving them in the
    editable set would silently license an unbounded rewrite.
    """
    spans = sorted(
        (t.start, t.end)
        for t in targets
        if t.resolvable and t.locator != LOC_CHAPTER and t.end > t.start
    )
    merged: List[Tuple[int, int]] = []
    for start, end in spans:
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))
    return merged


def build_revision_plan(
    draft_text: str,
    reviewer_json: Dict[str, Any],
    *,
    chapter: Optional[int] = None,
    draft_id: str = "",
    draft_fingerprint: str = "",
    include_advisory: bool = False,
    blocking_only: bool = False,
    rejected: bool = False,
    active_draft: Optional[Dict[str, Any]] = None,
    require_review_binding: bool = True,
) -> Dict[str, Any]:
    """Turn Reviewer output into a targeted revision plan.

    Scope of the plan is *ownership*, not severity. Every finding is routed by
    `classify_finding_owner`; only `PROSE_EDIT` findings become targets, because only they
    can be fixed by editing the prose. Artifact problems, ledger bookkeeping and craft
    advisories are returned in `deferred` with their owner and a repair hint — the previous
    contract put all of them in the plan, which is why an unfixable finding such as a
    missing `do_not_copy_check.json` kept the edit loop spinning without ever closing.

    `include_advisory=True` is an explicit opt-in to also plan the craft advisories; it is
    off by default because a plain `ALLOW_WITH_ADVISORY` review does not mean the chapter
    must be rewritten.

    Version protection: the plan is bound to the *content* of the draft it was built from, and
    to the active draft identity when one is available. `require_review_binding=True` refuses a
    Reviewer result that declares a draft identity contradicting this draft, and refuses a
    result that declares nothing unless the caller opts in explicitly — an old review must
    never be reused on a new draft silently.
    """
    draft_sha = sha256_text(draft_text)
    active = dict(active_draft or {})
    identity: Dict[str, Any] = {"verified": False, "source": "none"}

    if active.get("available"):
        active_fp = str(active.get("draft_fingerprint") or "")
        active_id = str(active.get("draft_id") or "")
        if active_fp and active_fp != draft_sha:
            raise RevisionBindingError(
                "工作草稿自 ingest 之后已被改动："
                f"active draft_fingerprint={active_fp[:12]} 但草稿当前 sha256={draft_sha[:12]}。"
                "先运行 `runtime ingest-draft` 重新登记草稿，再基于新草稿生成修订计划。"
            )
        draft_id = active_id or draft_id
        draft_fingerprint = active_fp or draft_fingerprint
        identity = {"verified": bool(active_fp), "source": "runtime.active_draft", "draft_id": draft_id}
    elif active:
        identity = {"verified": False, "source": "runtime.unavailable", "reason": active.get("reason", "")}
        if require_review_binding:
            raise RevisionBindingError(
                "找不到在编草稿身份（.webnovel/runtime/chapter_NNN/draft.json）："
                f"{active.get('reason') or 'no_active_draft'}。"
                "修订必须针对已登记的草稿；先 `runtime ingest-draft`，或显式传 --allow-unregistered-draft。"
            )

    declared = review_result_identity(reviewer_json)
    draft_subject_sha = _prose_subject_sha256(draft_text)
    review_binding: Dict[str, Any] = {
        "declared": dict(declared),
        "verified": False,
        "mode": "unbound",
        "subject_fingerprint": draft_subject_sha,
    }
    if declared.get("review_subject_fingerprint"):
        # The Reviewer read this exact prose. A `<chapter_changes>` fix since then changes the
        # full-draft hash but not one reviewed character, so the review is still about the
        # prose in front of us — that is the whole point of binding on the subject.
        if declared["review_subject_fingerprint"] != draft_subject_sha:
            raise RevisionBindingError(
                "审查结果声明的 review_subject_fingerprint 与当前草稿正文不一致："
                f"review={declared['review_subject_fingerprint'][:12]} draft={draft_subject_sha[:12]}。"
                "这是把旧审查用在（已变更的）新草稿上；请对新草稿重新运行 Reviewer。"
            )
        review_binding.update({"verified": True, "mode": "declared_review_subject"})
    elif declared.get("draft_fingerprint"):
        if declared["draft_fingerprint"] != draft_sha:
            raise RevisionBindingError(
                "审查结果声明的 draft_fingerprint 与当前草稿不一致："
                f"review={declared['draft_fingerprint'][:12]} draft={draft_sha[:12]}。"
                "这是把旧审查用在（已变更的）新草稿上；请对新草稿重新运行 Reviewer。"
            )
        review_binding.update({"verified": True, "mode": "declared_fingerprint"})
    elif declared.get("draft_id"):
        if draft_id and declared["draft_id"] != draft_id:
            raise RevisionBindingError(
                "审查结果声明的 draft_id 与当前在编草稿不一致："
                f"review={declared['draft_id']} draft={draft_id}。请对新草稿重新运行 Reviewer。"
            )
        review_binding.update({"verified": True, "mode": "declared_draft_id"})
    elif require_review_binding:
        raise RevisionBindingError(
            "审查结果没有声明它审查的是哪一版草稿（draft_id / draft_fingerprint 均为空），"
            "无法确认它属于当前草稿。请重新运行 Reviewer 并按其输出契约回填草稿身份，"
            "或显式传 --allow-unbound-review 承担该风险。"
        )

    issues = reviewer_json.get("issues")
    if not isinstance(issues, list):
        raise ValueError("reviewer JSON must contain an 'issues' list")

    resolved_chapter = chapter
    if resolved_chapter is None:
        try:
            resolved_chapter = int(reviewer_json.get("chapter"))
        except (TypeError, ValueError):
            resolved_chapter = 0

    selected: List[Dict[str, Any]] = []
    deferred: List[Dict[str, Any]] = []
    for issue in issues:
        if not isinstance(issue, dict):
            continue
        owner = classify_finding_owner(issue)
        if owner == OWNER_ADVISORY and not include_advisory:
            deferred.append(_deferred_entry(issue, owner))
            continue
        if owner not in (OWNER_PROSE_EDIT, OWNER_ADVISORY):
            deferred.append(_deferred_entry(issue, owner))
            continue
        if blocking_only and not issue.get("blocking"):
            continue
        selected.append({**issue, "_owner": owner})

    targets: List[RevisionTarget] = []
    for index, issue in enumerate(selected):
        target = locate_issue(draft_text, issue, index=index)
        target.owner = str(issue.get("_owner") or OWNER_PROSE_EDIT)
        if rejected and target.kind != KIND_CANON_HISTORY:
            target.kind = KIND_CANON_HISTORY
        targets.append(target)

    spans = _merge_spans(targets)
    plan = {
        "schema_version": SCHEMA_VERSION,
        "chapter": resolved_chapter,
        "draft_id": draft_id,
        "draft_fingerprint": draft_fingerprint,
        "draft_sha256": draft_sha,
        "draft_identity": identity,
        "review_binding": review_binding,
        "include_advisory": include_advisory,
        "targets": [t.to_dict() for t in targets],
        "editable_spans": [{"start": s, "end": e} for s, e in spans],
        "deferred": deferred,
        "summary": {
            "total": len(targets),
            "blocking": sum(1 for t in targets if t.blocking),
            "advisory": sum(1 for t in targets if not t.blocking),
            "resolvable": sum(1 for t in targets if t.resolvable),
            "unresolved": sum(1 for t in targets if not t.resolvable),
            "ambiguous": sum(1 for t in targets if t.ambiguity),
            "chapter_scope": sum(1 for t in targets if t.locator == LOC_CHAPTER),
            "canon_history": sum(1 for t in targets if t.kind == KIND_CANON_HISTORY),
            "by_kind": {
                kind: sum(1 for t in targets if t.kind == kind)
                for kind in (KIND_STYLE_ONLY, KIND_LOCAL_FACT, KIND_STRUCTURAL, KIND_CANON_HISTORY)
            },
            "deferred": len(deferred),
            "deferred_by_owner": {
                owner: sum(1 for item in deferred if item.get("owner") == owner)
                for owner in (
                    OWNER_ARTIFACT_REPAIR,
                    OWNER_GOVERNANCE_REPAIR,
                    OWNER_ADVISORY,
                )
            },
        },
    }
    return plan


# --------------------------------------------------------------------------- #
# apply (host-provided edits) + verify
# --------------------------------------------------------------------------- #


def apply_edits(
    draft_text: str,
    plan: Dict[str, Any],
    edits: Sequence[Dict[str, Any]],
) -> Tuple[str, Dict[str, Any]]:
    """Apply host-authored replacements to the planned spans.

    Each edit is `{"target_id": <issue_id>, "new_text": "..."}`. Two gates run before any
    replacement:

    1. the **whole draft** must hash to `plan.draft_sha256` (version protection), and
    2. each planned span must still match its recorded `before_text`.

    Either check failing means the draft is not the one the plan describes, and we refuse
    rather than editing blind.
    """
    check_draft_version(plan, draft_text)
    targets = {str(t.get("issue_id")): t for t in plan.get("targets") or []}
    results: List[Dict[str, Any]] = []
    # apply from the end so earlier offsets stay valid
    ordered = sorted(
        edits,
        key=lambda e: int(targets.get(str(e.get("target_id")), {}).get("start") or 0),
        reverse=True,
    )
    text = draft_text
    for edit in ordered:
        target_id = str(edit.get("target_id") or "")
        target = targets.get(target_id)
        if target is None:
            raise RevisionApplyError(f"unknown target_id: {target_id!r}")
        new_text = str(edit.get("new_text") or "")
        start, end = int(target["start"]), int(target["end"])
        before = str(target["before_text"])
        current = text[start:end]
        if current != before:
            raise RevisionApplyError(
                f"target {target_id} drifted: draft span no longer matches the plan "
                f"(expected sha {sha256_text(before)[:12]}, found {sha256_text(current)[:12]})"
            )
        text = text[:start] + new_text + text[end:]
        results.append(
            {
                "target_id": target_id,
                "changed": new_text != before,
                "locator": target.get("locator"),
                "line_start": target.get("line_start"),
                "line_end": target.get("line_end"),
                "kind": target.get("kind"),
            }
        )

    changed = text != draft_text
    return text, {
        "changed": changed,
        "edits_applied": len(results),
        "edits_that_changed_text": sum(1 for r in results if r["changed"]),
        "results": list(reversed(results)),
        "before_sha256": sha256_text(draft_text),
        "after_sha256": sha256_text(text),
    }


def verify_minimal_edit(
    before_text: str,
    after_text: str,
    plan: Dict[str, Any],
) -> Dict[str, Any]:
    """Verify that only the planned spans changed, and report which targets were addressed.

    Boundary check: every differing region between before and after must be contained in a
    planned span. Anything else is an out-of-scope rewrite and is reported as a violation —
    "改一个时间数字，只修改必要句段" is enforced here rather than trusted.

    The `before_text` is also required to be the draft the plan was built from; otherwise the
    whole comparison would be meaningless.
    """
    version_error = ""
    try:
        check_draft_version(plan, before_text)
    except RevisionApplyError as exc:
        version_error = str(exc)

    spans = [(int(s["start"]), int(s["end"])) for s in plan.get("editable_spans") or []]

    out_of_scope: List[Dict[str, Any]] = []

    def _tightened(i1: int, i2: int) -> Optional[Tuple[int, int]]:
        """Trim whitespace from a changed region; None when nothing but whitespace changed."""
        segment = before_text[i1:i2]
        left = len(segment) - len(segment.lstrip())
        right = len(segment) - len(segment.rstrip())
        tight = (i1 + left, i2 - right)
        return tight if tight[0] < tight[1] else None

    def _inside_spans(tight: Tuple[int, int]) -> bool:
        return any(lo <= tight[0] and tight[1] <= hi for lo, hi in spans)

    def _adjacent_to_span(i1: int, i2: int) -> bool:
        return any(lo - 1 <= i1 <= hi + 1 for lo, hi in spans)

    if before_text != after_text:
        matcher = difflib.SequenceMatcher(None, before_text, after_text, autojunk=False)
        for tag, i1, i2, _j1, _j2 in matcher.get_opcodes():
            if tag == "equal":
                continue
            tight = _tightened(i1, i2)
            if tight is None:
                # whitespace-only change: allowed when it touches a planned span, otherwise
                # reported (it can legitimately be a paragraph join at a planned boundary).
                if _adjacent_to_span(i1, i2):
                    continue
            elif _inside_spans(tight):
                continue
            out_of_scope.append(
                {
                    "tag": tag,
                    "before_start": i1,
                    "before_end": i2,
                    "before_excerpt": before_text[max(0, i1 - 20): i2 + 20],
                }
            )

    untouched: List[Dict[str, Any]] = []
    resolved: List[str] = []
    for target in plan.get("targets") or []:
        if not target.get("resolvable"):
            continue
        start, end = int(target["start"]), int(target["end"])
        snippet_before = before_text[start:end]
        snippet_after = after_text[start:end] if len(after_text) == len(before_text) else None
        if snippet_after is not None and snippet_after == snippet_before:
            untouched.append({"issue_id": target["issue_id"], "locator": target.get("locator")})
            continue
        # length changed → fall back to "is the original paragraph text still present verbatim?"
        if snippet_after is None and snippet_before and snippet_before in after_text:
            untouched.append({"issue_id": target["issue_id"], "locator": target.get("locator")})
            continue
        resolved.append(str(target["issue_id"]))

    result = {
        "schema_version": "revision-verify/v1",
        "changed": before_text != after_text,
        "plan_draft_sha256": str(plan.get("draft_sha256") or ""),
        "before_sha256_matches_plan": not version_error,
        "draft_version_error": version_error,
        "spans": [{"start": s, "end": e} for s, e in spans],
        "out_of_scope_changes": out_of_scope,
        "boundary_ok": not out_of_scope,
        "resolved_targets": resolved,
        "untouched_targets": untouched,
        # Full-draft hashes: artifact provenance for the exact files compared.
        "before_sha256": sha256_text(before_text),
        "after_sha256": sha256_text(after_text),
        # Prose-only hashes: the review subject on either side of the revision. These are what
        # closure evidence is bound to, so a `<chapter_changes>` fix inside the same revision
        # does not make a genuinely verified closure look unverifiable.
        "before_prose_sha256": _prose_subject_sha256(before_text),
        "after_prose_sha256": _prose_subject_sha256(after_text),
        "revision_round": plan.get("round") or plan.get("revision_round"),
    }
    result["ok"] = (
        result["boundary_ok"] and not version_error and (not result["changed"] or bool(resolved))
    )
    return result


def load_plan(path: str | Path) -> Dict[str, Any]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, dict) or "targets" not in data:
        raise ValueError(f"not a revision plan: {path}")
    return data


def write_plan(path: str | Path, plan: Dict[str, Any]) -> Path:
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8")
    return out


def format_plan_text(plan: Dict[str, Any]) -> str:
    summary = plan.get("summary") or {}
    binding = plan.get("review_binding") or {}
    lines = [
        f"revision plan  chapter={plan.get('chapter')}  draft_id={plan.get('draft_id') or '-'}",
        f"  draft_sha256={str(plan.get('draft_sha256') or '')[:16]}  "
        f"review_binding={'verified:' + str(binding.get('mode')) if binding.get('verified') else 'UNVERIFIED'}",
        (
            f"  targets={summary.get('total')} blocking={summary.get('blocking')} "
            f"advisory={summary.get('advisory')} resolvable={summary.get('resolvable')} "
            f"unresolved={summary.get('unresolved')} ambiguous={summary.get('ambiguous')}"
        ),
        f"  kinds={summary.get('by_kind')}",
    ]
    if summary.get("deferred"):
        lines.append(
            f"  deferred={summary.get('deferred')} (不由正文修订处理) "
            f"{summary.get('deferred_by_owner')}"
        )
    for target in plan.get("targets") or []:
        marker = "!" if target.get("blocking") else " "
        where = f"L{target.get('line_start')}-{target.get('line_end')}" if target.get("line_start") else "-"
        lines.append(
            f" [{marker}] {target.get('issue_id')} {target.get('severity')}/{target.get('category')} "
            f"{target.get('kind')} owner={target.get('owner')} via {target.get('locator')} {where}"
        )
        if target.get("fix_hint"):
            lines.append(f"      fix: {target['fix_hint']}")
        if target.get("ambiguity"):
            lines.append(f"      ambiguity: {target['ambiguity']}（不会自动替换，请人工指定位置）")
    for item in plan.get("deferred") or []:
        lines.append(
            f" [deferred:{item.get('owner')}] {item.get('severity')}/{item.get('category')} "
            f"{item.get('location')} {item.get('description')}"
        )
        if item.get("repair_hint"):
            lines.append(f"      repair: {item['repair_hint']}")
    return "\n".join(lines)
