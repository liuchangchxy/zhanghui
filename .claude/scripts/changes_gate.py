#!/usr/bin/env python3
"""CHANGES 协议门禁校验。

在 webnovel-write skill 的 Step 2A 之后被调用：
    python3 changes_gate.py --chapter-file CH.md --db index.db --json

返回 JSON：{"passed": bool, "failures": [{"rule_id", "severity", "message", "location"}]}
"""
from __future__ import annotations

import argparse
import json
import re
import sqlite3
import sys
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any

# 8 个顶级字段，借鉴天命 12 字段砍到核心 8 个
REQUIRED_TOP_LEVEL_FIELDS = frozenset({
    "character_state_changes",
    "new_plot_points",
    "foreshadowing_actions",
    "location_state_changes",
    "faction_state_changes",
    "time_progression",
    "item_transfers",
    "unresolved_questions",
})

# 容器形式优先级
CHANGE_PATTERNS = [
    re.compile(r"<chapter_changes>(.*?)</chapter_changes>", re.DOTALL | re.IGNORECASE),
    re.compile(r"---CHANGES---(.*?)(?=---|\Z)", re.DOTALL),
    re.compile(r"^#\s*CHANGES\s*\n(.*?)(?=^#|\Z)", re.DOTALL | re.MULTILINE | re.IGNORECASE),
]


@dataclass
class Failure:
    rule_id: str
    severity: str  # "blocking" | "advisory"
    message: str
    location: str = ""


@dataclass
class GateResult:
    passed: bool
    failures: list[Failure] = field(default_factory=list)
    parsed_changes: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "failures": [asdict(f) for f in self.failures],
        }


def extract_changes_block(chapter_text: str) -> str | None:
    """从章节文本里识别 CHANGES 容器。"""
    for pattern in CHANGE_PATTERNS:
        m = pattern.search(chapter_text)
        if m:
            return m.group(1).strip()
    # 兜底：末尾 JSON
    tail = chapter_text.rstrip().split("\n\n")[-1].strip()
    if tail.startswith("{") and tail.endswith("}"):
        candidate_keys = REQUIRED_TOP_LEVEL_FIELDS
        matched = sum(1 for k in candidate_keys if f'"{k}"' in tail)
        if matched >= 4:
            return tail
    return None


def repair_changes_json(raw: str) -> str:
    """借鉴天命的 9 类字符修复。"""
    s = raw
    # 中文标点 → 半角
    s = s.replace("，", ",").replace("：", ":").replace("（", "(").replace("）", ")")
    s = s.replace("；", ";").replace("？", "?").replace("！", "!").replace("「", '"').replace("」", '"')
    # 单引号 → 双引号（仅在键/值的引号位置）
    s = re.sub(r"'([^'\n]+?)'\s*:", r'"\1":', s)
    s = re.sub(r":\s*'([^'\n]+?)'", r': "\1"', s)
    # 缺尾引号自动闭合：扫描所有 key 后面是否缺引号
    # （简化版：依赖 LLM 输出时遵守 json 格式；此处不实现复杂修复）
    return s


def parse_changes(chapter_text: str) -> tuple[dict[str, Any] | None, str | None]:
    """返回 (parsed_dict, error_message)。"""
    block = extract_changes_block(chapter_text)
    if block is None:
        return None, "未找到 CHANGES 容器（支持 <chapter_changes>、---CHANGES---、# CHANGES、末尾 JSON 兜底）"
    repaired = repair_changes_json(block)
    try:
        parsed = json.loads(repaired)
    except json.JSONDecodeError as e:
        return None, f"CHANGES JSON 解析失败：{e}"
    return parsed, None


# R1 + R2: 校验
ENUM_IMPORTANCE = frozenset({"normal", "important", "critical"})
ENUM_ACTION = frozenset({"setup", "payoff"})
ENUM_STORYLINE = frozenset({"main", "sub", "character_arc"})
ENUM_ITEM_STATUS = frozenset({"active", "lost", "destroyed", "sealed"})
ENUM_TIME_IMPORTANCE = frozenset({"normal", "important", "critical"})


def check_r01_protocol(changes: dict[str, Any]) -> list[Failure]:
    """R1: 8 个顶级字段必须显式存在。"""
    failures = []
    for field_name in REQUIRED_TOP_LEVEL_FIELDS:
        if field_name not in changes:
            failures.append(Failure(
                rule_id="R1",
                severity="blocking",
                message=f"缺少必填字段：{field_name}",
            ))
    return failures


def check_r02_enums(changes: dict[str, Any]) -> list[Failure]:
    """R2: 枚举值合法。"""
    failures = []

    for i, ev in enumerate(changes.get("character_state_changes", []) or []):
        if isinstance(ev, dict):
            imp = ev.get("importance")
            if imp not in ENUM_IMPORTANCE:
                failures.append(Failure(
                    rule_id="R2",
                    severity="blocking",
                    message=f"character_state_changes[{i}].importance='{imp}' 非法，取值应为 {sorted(ENUM_IMPORTANCE)}",
                ))

    for i, ev in enumerate(changes.get("foreshadowing_actions", []) or []):
        if isinstance(ev, dict):
            act = ev.get("action")
            if act not in ENUM_ACTION:
                failures.append(Failure(
                    rule_id="R2",
                    severity="blocking",
                    message=f"foreshadowing_actions[{i}].action='{act}' 非法，取值应为 {sorted(ENUM_ACTION)}",
                ))

    for i, ev in enumerate(changes.get("item_transfers", []) or []):
        if isinstance(ev, dict):
            st = ev.get("new_status")
            if st not in ENUM_ITEM_STATUS:
                failures.append(Failure(
                    rule_id="R2",
                    severity="blocking",
                    message=f"item_transfers[{i}].new_status='{st}' 非法，取值应为 {sorted(ENUM_ITEM_STATUS)}",
                ))

    for i, ev in enumerate(changes.get("new_plot_points", []) or []):
        if isinstance(ev, dict):
            sl = ev.get("storyline")
            if sl is not None and sl not in ENUM_STORYLINE:
                failures.append(Failure(
                    rule_id="R2",
                    severity="blocking",
                    message=f"new_plot_points[{i}].storyline='{sl}' 非法，取值应为 {sorted(ENUM_STORYLINE)}",
                ))
            imp = ev.get("importance")
            if imp not in ENUM_IMPORTANCE:
                failures.append(Failure(
                    rule_id="R2",
                    severity="blocking",
                    message=f"new_plot_points[{i}].importance='{imp}' 非法，取值应为 {sorted(ENUM_IMPORTANCE)}",
                ))

    tp = changes.get("time_progression")
    if isinstance(tp, dict):
        tpi = tp.get("importance")
        if tpi not in ENUM_TIME_IMPORTANCE:
            failures.append(Failure(
                rule_id="R2",
                severity="blocking",
                message=f"time_progression.importance='{tpi}' 非法，取值应为 {sorted(ENUM_TIME_IMPORTANCE)}",
            ))

    return failures


def _load_entity_lookup(db_path: Path) -> tuple[set[str], set[str]]:
    """从 index.db 加载所有合法 ID 和 alias。"""
    if not Path(db_path).exists():
        # db 不存在时返回空集——所有引用都会被标记为未知（由调用方决定是否阻塞）
        return set(), set()
    conn = sqlite3.connect(db_path)
    ids = set()
    aliases = set()
    try:
        for row in conn.execute("SELECT id FROM entities WHERE is_archived = 0"):
            ids.add(row[0])
        for row in conn.execute("SELECT alias FROM aliases"):
            aliases.add(row[0])
    finally:
        conn.close()
    return ids, aliases


def check_r03_entities(changes: dict[str, Any], db_path: Path) -> list[Failure]:
    """R3: 实体引用合法（ID 或 alias 都接受）。"""
    failures = []
    valid_ids, valid_aliases = _load_entity_lookup(db_path)
    if not valid_ids and not valid_aliases:
        # db 不可用，跳过此规则
        return failures

    def check_ref(ref: Any, location: str) -> None:
        if not isinstance(ref, str):
            return
        if ref in valid_ids or ref in valid_aliases:
            return
        failures.append(Failure(
            rule_id="R3",
            severity="blocking",
            message=f"{location}: 引用 '{ref}' 不在账本",
        ))

    for i, ev in enumerate(changes.get("character_state_changes", []) or []):
        if isinstance(ev, dict):
            check_ref(ev.get("character_id"), f"character_state_changes[{i}].character_id")

    for i, ev in enumerate(changes.get("new_plot_points", []) or []):
        if isinstance(ev, dict):
            for j, char_id in enumerate(ev.get("involved_characters", []) or []):
                check_ref(char_id, f"new_plot_points[{i}].involved_characters[{j}]")

    for i, ev in enumerate(changes.get("location_state_changes", []) or []):
        if isinstance(ev, dict):
            check_ref(ev.get("location_id"), f"location_state_changes[{i}].location_id")

    for i, ev in enumerate(changes.get("faction_state_changes", []) or []):
        if isinstance(ev, dict):
            check_ref(ev.get("faction_id"), f"faction_state_changes[{i}].faction_id")

    return failures


def _load_foreshadowing_state(db_path: Path) -> dict[str, str]:
    if not Path(db_path).exists():
        return {}
    conn = sqlite3.connect(db_path)
    state = {}
    try:
        for row in conn.execute("SELECT id, status FROM foreshadowing"):
            state[row[0]] = row[1]
    finally:
        conn.close()
    return state


def check_r04_foreshadowing(changes: dict[str, Any], db_path: Path) -> list[Failure]:
    """R4: 伏笔 ID 必须存在 + 不能重复 payoff。"""
    failures = []
    fs_state = _load_foreshadowing_state(db_path)
    if not fs_state:
        return failures  # db 不可用，跳过

    for i, ev in enumerate(changes.get("foreshadowing_actions", []) or []):
        if not isinstance(ev, dict):
            continue
        fid = ev.get("foreshadow_id")
        action = ev.get("action")
        if fid not in fs_state:
            failures.append(Failure(
                rule_id="R4",
                severity="blocking",
                message=f"foreshadowing_actions[{i}].foreshadow_id='{fid}' 不在账本",
            ))
            continue
        current_status = fs_state[fid]
        # 状态机：setup 可以反复 setup（强化伏笔），payoff 后不能再 payoff
        if action == "payoff" and current_status == "paid":
            failures.append(Failure(
                rule_id="R4",
                severity="blocking",
                message=f"foreshadowing_actions[{i}]: '{fid}' 已被回收，不能再次 payoff",
            ))

    return failures


MAX_TRUST_DELTA = 30


def check_r05_relationships(changes: dict[str, Any], db_path: Path) -> list[Failure]:
    """R5: 单章关系信任度变化不超过 ±MAX_TRUST_DELTA。"""
    failures = []
    for i, ev in enumerate(changes.get("character_state_changes", []) or []):
        if not isinstance(ev, dict):
            continue
        rel_changes = ev.get("relationship_changes", {}) or {}
        if not isinstance(rel_changes, dict):
            continue
        for target, info in rel_changes.items():
            if not isinstance(info, dict):
                continue
            delta = info.get("trust_delta")
            if delta is None:
                continue
            if abs(delta) > MAX_TRUST_DELTA:
                failures.append(Failure(
                    rule_id="R5",
                    severity="blocking",
                    message=f"character_state_changes[{i}].relationship_changes['{target}']: trust_delta={delta} 超过 ±{MAX_TRUST_DELTA}",
                ))
    return failures


# 常见中文名/称谓/虚词停用词，避免误报
ENTITY_STOPWORDS = frozenset({
    # 代词
    "他", "她", "它", "我", "你", "我们", "他们", "她们", "它们",
    "自己", "大家", "对方", "旁人", "某人",
    "这", "那", "这个", "那个", "这些", "那些",
    "什么", "怎么", "为什么", "谁", "哪里",
    # 角色称谓
    "主角", "配角", "反派", "路人",
    # 常用虚词/连接词/时间词（极容易产生 2-4 字切片）
    "然后", "然而", "于是",
    "这时", "此时", "此时此", "此间",
    "之间", "其中", "这般", "这般一",
    "本来", "原来",
    "竟然", "突然", "忽然",
    "不禁", "不由",
})

# 中文姓名启发式：2-4 字 + 不在停用词 + 不含标点
ENTITY_PATTERN = re.compile(r"[一-龥]{2,4}")
_CHINESE_RUN_PATTERN = re.compile(r"[一-龥]+")


def extract_chapter_entities(text: str) -> set[str]:
    """从正文提取可能的实体名（启发式）。

    对每个连续中文 run，枚举所有 2-4 字窗口作为候选。
    """
    candidates = set()
    for run in _CHINESE_RUN_PATTERN.finditer(text):
        s = run.group()
        L = len(s)
        if L < 2:
            continue
        for n in (2, 3, 4):
            if L < n:
                continue
            for i in range(L - n + 1):
                sub = s[i:i+n]
                if sub not in ENTITY_STOPWORDS:
                    candidates.add(sub)
    return candidates


def check_r06_unregistered(text: str, changes: dict[str, Any], registered: set[str]) -> list[Failure]:
    """R6: 正文中提到的实体如未在账本且未在 CHANGES 申报，超过阈值则告警。

    若 `registered` 为空集合（未初始化账本），直接跳过——没有账本可对比。
    """
    if not registered:
        return []  # 防御性早返回：空账本无意义
    threshold = 15
    PLACEHOLDER = " "  # 非中文占位符，破坏中文 run
    # 用账本中已知的中文名替换正文，避免对账本名内部切片产生误报
    text_cleaned = text
    for name in registered:
        if isinstance(name, str) and re.fullmatch(ENTITY_PATTERN, name):
            if name in text_cleaned:
                text_cleaned = text_cleaned.replace(name, PLACEHOLDER * len(name))

    mentioned = extract_chapter_entities(text_cleaned)

    # 申报了的实体也算已知
    declared = set()
    for ev in changes.get("character_state_changes", []) or []:
        if isinstance(ev, dict):
            cid = ev.get("character_id")
            if cid:
                declared.add(cid)
    for ev in changes.get("new_plot_points", []) or []:
        if isinstance(ev, dict):
            for cid in ev.get("involved_characters", []) or []:
                declared.add(cid)

    unregistered = mentioned - registered - declared
    if len(unregistered) > threshold:
        return [Failure(
            rule_id="R6",
            severity="blocking",
            message=f"正文中出现 {len(unregistered)} 个未登记实体（阈值 {threshold}）：{sorted(unregistered)[:10]}...",
        )]
    return []


# R7: 物品状态机——合法转移图
ITEM_STATE_TRANSITIONS: dict[str | None, set[str]] = {
    None: {"active", "lost", "destroyed", "sealed"},
    "active": {"active", "lost", "destroyed", "sealed"},
    "lost": {"active", "destroyed"},
    "sealed": {"active", "destroyed", "lost"},
    "destroyed": set(),  # destroyed 是终态
}


def _load_item_state(db_path: Path) -> dict[str, str]:
    """从 index.db 读取每个 item 的当前 status。

    兼容 entities.current_json 字段（JSON 里有 status key）。
    """
    if not Path(db_path).exists():
        return {}
    conn = sqlite3.connect(db_path)
    state: dict[str, str] = {}
    try:
        for row in conn.execute(
            "SELECT id, current_json FROM entities WHERE type='item'"
        ):
            item_id, raw_json = row[0], row[1]
            if not raw_json:
                continue
            import json as _json
            try:
                cur = _json.loads(raw_json)
            except _json.JSONDecodeError:
                continue
            if isinstance(cur, dict):
                status = cur.get("status")
                if isinstance(status, str):
                    state[item_id] = status
    except sqlite3.OperationalError:
        pass
    finally:
        conn.close()
    return state


def check_r07_item_state(changes: dict[str, Any], db_path: Path) -> list[Failure]:
    """R7: 物品状态转移合法——按 ITEM_STATE_TRANSITIONS 校验。"""
    failures: list[Failure] = []
    item_state = _load_item_state(db_path)
    for i, ev in enumerate(changes.get("item_transfers", []) or []):
        if not isinstance(ev, dict):
            continue
        item_id = ev.get("item_id")
        new_status = ev.get("new_status")
        if not item_id or not new_status:
            continue  # 没 ID/新状态就不强制校验
        prev_status = item_state.get(item_id)
        legal_next = ITEM_STATE_TRANSITIONS.get(prev_status, set())
        # legal_next 为空（如 destroyed 是终态）或 new_status 不在合法集合内，均视为非法
        if not legal_next or new_status not in legal_next:
            failures.append(Failure(
                rule_id="R7",
                severity="blocking",
                message=(
                    f"item_transfers[{i}]: '{item_id}' 从 '{prev_status}' → "
                    f"'{new_status}' 非法转移，合法目标：{sorted(legal_next)}"
                ),
            ))
    return failures


# R8: 时间线连贯——本章不应声明与上一章冲突的时间
import re as _re_time


def _extract_chapter_number(chapter_text: str) -> int | None:
    """从章节文件正文里提取章号。"""
    m = _re_time.search(r"第\s*(\d+)\s*章", chapter_text)
    return int(m.group(1)) if m else None


def _load_timeline(db_path: Path) -> dict[int, str]:
    if not Path(db_path).exists():
        return {}
    conn = sqlite3.connect(db_path)
    state = {}
    try:
        for row in conn.execute("SELECT chapter, time_anchor FROM timeline ORDER BY chapter"):
            state[row[0]] = row[1]
    except sqlite3.OperationalError:
        pass
    finally:
        conn.close()
    return state


def check_r08_timeline(changes: dict[str, Any], db_path: Path, current_chapter: int) -> list[Failure]:
    """R8: 时间线连贯——本章不应声明与上一章冲突的时间。"""
    failures = []
    tp = changes.get("time_progression")
    if not tp or not isinstance(tp, dict):
        return failures
    elapsed = (tp.get("elapsed_time") or "").strip()
    if not elapsed:
        return failures

    timeline = _load_timeline(db_path)
    if not timeline:
        return failures  # db 不可用跳过

    # 简单启发式：检测"回到"、"倒退"等关键词
    suspicious_keywords = ["回到", "倒退", "前一年", "三年前", "十年前"]
    if any(kw in elapsed for kw in suspicious_keywords):
        # 进一步要求上一章存在
        if (current_chapter - 1) in timeline:
            failures.append(Failure(
                rule_id="R8",
                severity="advisory",  # 注意：启发式不确定，用 advisory
                message=f"time_progression.elapsed_time='{elapsed}' 含倒退关键词，请人工确认",
            ))
    return failures


def main() -> int:
    parser = argparse.ArgumentParser(description="CHANGES 协议门禁")
    parser.add_argument("--chapter-file", required=True, help="章节文件路径")
    parser.add_argument("--db", default="", help="webnovel-writer index.db 路径（可选，未初始化项目可省略）")
    parser.add_argument("--json", action="store_true", help="输出 JSON 格式")
    parser.add_argument("--rule", help="只跑指定规则（如 R1）")
    parser.add_argument("--strict", action="store_true", help="advisory 也算 blocking")
    args = parser.parse_args()

    chapter_text = Path(args.chapter_file).read_text(encoding="utf-8")
    parsed, err = parse_changes(chapter_text)
    result = GateResult(passed=True, parsed_changes=parsed)
    if err:
        result.passed = False
        result.failures.append(Failure(rule_id="R0", severity="blocking", message=err))

    if parsed:
        check_failures = []
        for check_fn in (check_r01_protocol, check_r02_enums):
            check_failures.extend(check_fn(parsed))
        if args.db:
            check_failures.extend(check_r03_entities(parsed, Path(args.db)))
            check_failures.extend(check_r04_foreshadowing(parsed, Path(args.db)))
            check_failures.extend(check_r05_relationships(parsed, Path(args.db)))
            check_failures.extend(check_r07_item_state(parsed, Path(args.db)))
        result.failures.extend(check_failures)
        if args.strict:
            result.passed = not result.failures
        else:
            result.passed = not any(f.severity == "blocking" for f in result.failures)

    # R6 需要 chapter 全文 + 已加载的 registered ids
    # 若 --db 缺失/空集合，跳过——没有账本可对比就是没初始化
    if parsed and args.db:
        registered_ids, registered_aliases = _load_entity_lookup(Path(args.db))
        all_known = registered_ids | registered_aliases
        if all_known:
            chapter_text_for_r6 = Path(args.chapter_file).read_text(encoding="utf-8")
            for f in check_r06_unregistered(chapter_text_for_r6, parsed, all_known):
                result.failures.append(f)
                if not args.strict and f.severity == "blocking":
                    result.passed = False
            if args.strict:
                result.passed = not result.failures

    # R8 需要 chapter 全文（提取章号）+ db
    if parsed:
        chapter_text_for_r8 = Path(args.chapter_file).read_text(encoding="utf-8")
        chapter_num = _extract_chapter_number(chapter_text_for_r8) or 0
        if args.db:
            for f in check_r08_timeline(parsed, Path(args.db), chapter_num):
                result.failures.append(f)
        if args.strict:
            result.passed = not result.failures
        else:
            result.passed = not any(f.severity == "blocking" for f in result.failures)

    if args.json:
        print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
    else:
        print("PASSED" if result.passed else f"FAILED: {len(result.failures)} failure(s)")
        for f in result.failures:
            print(f"  [{f.rule_id}/{f.severity}] {f.message}")

    return 0 if result.passed else 1


if __name__ == "__main__":
    sys.exit(main())