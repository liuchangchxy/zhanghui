#!/usr/bin/env python3
"""Reviewer 输出 → RejectionContract 转换与校验。

Reviewer 的原始 JSON（见 plugins/webnovel-writer/agents/reviewer.md §7）
是结构化但"散文式"的：每个 issue 有 location / description / fix_hint
但没有显式"保留哪些段"。

RejectionContract 在它之上加 3 件事：
1. 过滤（默认只收 blocking=true）
2. 校验（location/fix_hint 必填，category 在白名单）
3. 合并（多次 reviewer 跑出的 contract 可聚合）
"""
from __future__ import annotations

import enum
from dataclasses import dataclass, field
from typing import Any, Iterable


VALID_CATEGORIES = frozenset({
    "continuity", "setting", "character", "timeline", "logic", "pacing", "other",
})


class Severity(str, enum.Enum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


@dataclass
class IssueRef:
    """单条 issue 的引用 + 修复指令。"""
    severity: Severity
    category: str
    location: str  # "第3段" / "§2-§5" / 具体引用
    description: str
    fix_hint: str
    blocking: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "severity": self.severity.value,
            "category": self.category,
            "location": self.location,
            "description": self.description,
            "fix_hint": self.fix_hint,
            "blocking": self.blocking,
        }


@dataclass
class RejectionContract:
    """一组要修的 issue + 元数据。"""
    chapter: int
    issues: list[IssueRef] = field(default_factory=list)
    source: str = "reviewer"  # 来源标识，方便调试

    def to_dict(self) -> dict[str, Any]:
        return {
            "chapter": self.chapter,
            "source": self.source,
            "issues": [i.to_dict() for i in self.issues],
        }


def build_contract_from_reviewer_output(
    reviewer_json: dict[str, Any],
    include_advisory: bool = False,
    source: str = "reviewer",
) -> RejectionContract:
    """从 reviewer 的原始 JSON 构造 contract。

    include_advisory=False（默认）：只收 blocking=True 的 issue。
    include_advisory=True：全收，按 severity 顺序保留。
    """
    chapter = reviewer_json.get("chapter")
    if chapter is None:
        raise ValueError("reviewer_json 缺少 chapter 字段")

    raw_issues = reviewer_json.get("issues", [])
    if include_advisory:
        selected = raw_issues
    else:
        selected = [i for i in raw_issues if i.get("blocking")]

    issues: list[IssueRef] = []
    for raw in selected:
        sev = raw.get("severity", "high")
        try:
            sev_enum = Severity(sev)
        except ValueError:
            sev_enum = Severity.HIGH

        issues.append(IssueRef(
            severity=sev_enum,
            category=raw.get("category", "other"),
            location=raw.get("location", ""),
            description=raw.get("description", ""),
            fix_hint=raw.get("fix_hint", ""),
            blocking=bool(raw.get("blocking", False)),
        ))

    return RejectionContract(chapter=chapter, issues=issues, source=source)


def validate_contract(contract: RejectionContract) -> None:
    """合法性校验。raise ValueError 说明哪里坏了。"""
    if not contract.issues:
        raise ValueError("contract 需要至少一个 issue")

    for idx, issue in enumerate(contract.issues):
        if not issue.location.strip():
            raise ValueError(f"contract.issues[{idx}].location 必填")
        if not issue.description.strip():
            raise ValueError(f"contract.issues[{idx}].description 必填")
        if not issue.fix_hint.strip():
            raise ValueError(f"contract.issues[{idx}].fix_hint 必填")
        if issue.category not in VALID_CATEGORIES:
            raise ValueError(
                f"contract.issues[{idx}].category={issue.category!r} 不在白名单 {sorted(VALID_CATEGORIES)}"
            )


def merge_contracts(contracts: Iterable[RejectionContract]) -> RejectionContract:
    """合并多个 contract（必须同一章节）。"""
    contracts = list(contracts)
    if not contracts:
        raise ValueError("至少需要一个 contract")
    chapters = {c.chapter for c in contracts}
    if len(chapters) > 1:
        raise ValueError(f"合并的 contract 必须是同一章节，得到 {sorted(chapters)}")

    chapter = contracts[0].chapter
    merged_issues: list[IssueRef] = []
    for c in contracts:
        merged_issues.extend(c.issues)
    return RejectionContract(
        chapter=chapter,
        issues=merged_issues,
        source="+".join({c.source for c in contracts}),
    )


def targets_text(contract: RejectionContract) -> str:
    """生成给重写 LLM 看的"目标段 + 修复指令"汇总文本。

    按 location 聚合；同一段有多个 fix_hint 用换行分隔。
    """
    grouped: dict[str, list[str]] = {}
    order: list[str] = []
    for issue in contract.issues:
        if issue.location not in grouped:
            order.append(issue.location)
            grouped[issue.location] = []
        grouped[issue.location].append(
            f"  - [{issue.severity.value}/{issue.category}] {issue.fix_hint}（{issue.description}）"
        )

    lines = [f"针对第 {contract.chapter} 章的局部重写任务："]
    for loc in order:
        lines.append(f"\n## {loc}")
        lines.extend(grouped[loc])
    return "\n".join(lines)
