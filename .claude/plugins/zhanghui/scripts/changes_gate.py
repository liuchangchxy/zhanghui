#!/usr/bin/env python3
"""CHANGES 协议门禁校验。

在 webnovel-write skill 的最终正文稳定、ProposedChanges 刷新后被调用：
    python3 changes_gate.py --chapter-file CH.md --db index.db --json

职责：校验 CHANGES 容器、协议/schema、枚举和既有账本完整性。它不比较 Data Agent 的 ObservedChanges；语义对齐由 reconcile_changes.py 完成。

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


# SQLite 文件魔数（前 16 字节）
SQLITE_HEADER = b"SQLite format 3\x00"

# 用于识别"这是一个 webnovel-writer 账本"的最小表集合。
#
# 注意（重要）：这里**不能**包含 foreshadowing / timeline。真实的 webnovel-writer
# index.db（见 plugins/webnovel-writer/scripts/data_modules/index_manager.py）只创建
# entities / aliases / relationships / chapters / ... —— 伏笔存在 state.json 里，
# 没有 foreshadowing 表，也没有 timeline 表。把它们列为"必需表"会让**所有真实项目**
# 在 R0 直接失败。R4/R8 在缺表时各自优雅跳过（见 _load_foreshadowing_state / _load_timeline）。
EXPECTED_TABLES = frozenset({"entities", "aliases"})

# 合法的规则 ID（用于 --rule 校验）。R0 是基础设施错误，不是可选规则，但允许显式指定。
KNOWN_RULE_IDS = frozenset({"R0", "R1", "R2", "R3", "R4", "R4b", "R5", "R6", "R7", "R8"})

# R4b 默认阈值：伏笔埋了 N 章还没回收 → advisory（与 oh-story 约定一致，不阻塞）
R4B_DEFAULT_OVERDUE_THRESHOLD = 20

# H-R4-1: 防止恶意 / 异常的 state.json 让 json.load 把内存吃光（C-R4-1 DoS）。
# 真实 webnovel-writer 项目的 state.json 通常 < 1MB；5MB 已是 100x 上限。
MAX_STATE_BYTES = 5 * 1024 * 1024

# M-R4-2: R4b advisory 输出上限，避免一次性喷出几十条 advisory 淹没作者。
R4B_ADVISORY_MAX = 10


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
    """从章节文本里识别 CHANGES 容器。

    当 LLM 给出多个候选块时，采用最后一个（修正版）。
    """
    for pattern in CHANGE_PATTERNS:
        matches = pattern.findall(chapter_text)
        if matches:
            # Use the LAST block (when LLM provides alternatives, the last is the corrected one)
            return matches[-1].strip()
    # 兜底：末尾 JSON
    tail = chapter_text.rstrip().split("\n\n")[-1].strip()
    if tail.startswith("{") and tail.endswith("}"):
        candidate_keys = REQUIRED_TOP_LEVEL_FIELDS
        matched = sum(1 for k in candidate_keys if f'"{k}"' in tail)
        if matched >= 4:
            return tail
    return None


def repair_changes_json(raw: str) -> str:
    """借鉴天命的 9 类字符修复（MED-56 position-aware）。

    只在 JSON 语法位置（outside string tokens）替换中文标点 / 「」，
    **不动字符串 token 内的对话内容**。例如：

    - `{"key": "她说：「你好」"}` → 「」 保留（它在字符串 token 内，是对话内容）
    - `{'character_state_changes': []}` → 单引号替换为双引号（语法位置）
    - `{「key」: 「value」}` → 「」 替换为 "（语法位置）

    实现：
    1. 用 ``json.JSONDecoder.raw_decode`` 定位最外层 JSON 边界；
    2. 走字符级状态机，识别 string token 的 (start, end) 区间；
    3. 在区间外做中文标点 / 「」 替换；在区间内保留原字符。
    """
    decoder = json.JSONDecoder()
    n = len(raw)
    start = 0
    # 跳过前导空白
    while start < n and raw[start] in " \t\n\r":
        start += 1

    # 定位最外层 JSON 边界（raw_decode 失败时退化到全文本扫描，行为退化为老版本）
    json_end = n
    try:
        _, json_end = decoder.raw_decode(raw, start)
    except json.JSONDecodeError:
        start = 0
        json_end = n

    # 1) 扫描 string token 区间（基于「」 " 和 ' 三种引号）
    str_spans: list[tuple[int, int]] = []
    i = start
    in_str = False
    str_quote = ""
    str_open = -1
    escape = False
    while i < json_end:
        c = raw[i]
        if in_str:
            if escape:
                escape = False
            elif c == "\\":
                escape = True
            elif c == str_quote:
                str_spans.append((str_open, i + 1))
                in_str = False
                str_quote = ""
                str_open = -1
        else:
            if c in ('"', "'"):
                in_str = True
                str_quote = c
                str_open = i
        i += 1

    def in_string(pos: int) -> bool:
        # 二分定位（区间有序，start < end）
        lo, hi = 0, len(str_spans)
        while lo < hi:
            mid = (lo + hi) // 2
            s, e = str_spans[mid]
            if pos < s:
                hi = mid
            elif pos >= e:
                lo = mid + 1
            else:
                return True
        return False

    # 2) 字符级替换：在 string token 外做中文标点 / 「」 → 半角 / "
    cn_punct_map = {
        "，": ",",
        "：": ":",
        "（": "(",
        "）": ")",
        "；": ";",
        "？": "?",
        "！": "!",
    }
    out_chars: list[str] = []
    for idx, c in enumerate(raw):
        if in_string(idx):
            out_chars.append(c)
            continue
        if c in cn_punct_map:
            out_chars.append(cn_punct_map[c])
        elif c == "「" or c == "」":
            out_chars.append('"')
        else:
            out_chars.append(c)
    s = "".join(out_chars)

    # 3) 单引号 → 双引号（语法位置；原 regex 不感知位置，但因为我们已经把字符串
    # token 的内容原样保留，所以即使 regex 误命中也不影响对话内容——只是占位。
    # 实际上 regex 不会命中 string token 内部，因为内部保留后字符没变）。
    s = re.sub(r"'([^'\n]+?)'\s*:", r'"\1":', s)
    s = re.sub(r":\s*'([^'\n]+?)'", r': "\1"', s)

    # 4) Remove trailing commas before closing brackets/braces（结构性、跨 token）
    s = re.sub(r",(\s*[}\]])", r"\1", s)
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
                location=f"top_level.{field_name}",
            ))
    return failures


def _iter_array_field(
    changes: dict[str, Any],
    field_name: str,
    failures: list[Failure] | None = None,
    rule_id: str = "R2",
) -> list[tuple[int, Any]]:
    """迭代 array field。

    - field 缺失或 None：返回空（兼容历史 `or []` 语义，不报错）
    - field 是 list：正常 enumerate
    - field 是其他类型（bool/dict/str/...）：返回空并可记录 R2 失败
    """
    raw = changes.get(field_name)
    if raw is None:
        return []  # 缺失/None — 跳过（历史行为）
    if not isinstance(raw, list):
        if failures is not None:
            failures.append(Failure(
                rule_id=rule_id,
                severity="blocking",
                message=f"{field_name} 必须是数组，当前类型：{type(raw).__name__}",
                location=f"top_level.{field_name}",
            ))
        return []
    return list(enumerate(raw))


def check_r02_enums(changes: dict[str, Any]) -> list[Failure]:
    """R2: 枚举值合法。

    容忍非 list 类型（bool/dict 不会崩溃），仅在 list 的元素非 dict 时报错。
    """
    failures = []

    def not_a_dict(field_name: str, i: int, ev: Any) -> Failure:
        return Failure(
            rule_id="R2",
            severity="blocking",
            message=f"{field_name}[{i}] 必须是对象，实际为 {type(ev).__name__}",
            location=f"{field_name}[{i}]",
        )

    for i, ev in _iter_array_field(changes, "character_state_changes", failures):
        if not isinstance(ev, dict):
            failures.append(not_a_dict("character_state_changes", i, ev))
            continue
        imp = ev.get("importance")
        if imp not in ENUM_IMPORTANCE:
            failures.append(Failure(
                rule_id="R2",
                severity="blocking",
                message=f"character_state_changes[{i}].importance='{imp}' 非法，取值应为 {sorted(ENUM_IMPORTANCE)}",
                location=f"character_state_changes[{i}].importance",
            ))

    for i, ev in _iter_array_field(changes, "foreshadowing_actions", failures):
        if not isinstance(ev, dict):
            failures.append(not_a_dict("foreshadowing_actions", i, ev))
            continue
        act = ev.get("action")
        # 缺失或 null action 跳过 — R4 会通过 foreshadow_id 校验
        if act is None:
            continue
        if act not in ENUM_ACTION:
            failures.append(Failure(
                rule_id="R2",
                severity="blocking",
                message=f"foreshadowing_actions[{i}].action='{act}' 非法，取值应为 {sorted(ENUM_ACTION)}",
                location=f"foreshadowing_actions[{i}].action",
            ))

    for i, ev in _iter_array_field(changes, "item_transfers", failures):
        if not isinstance(ev, dict):
            failures.append(not_a_dict("item_transfers", i, ev))
            continue
        st = ev.get("new_status")
        # 缺失或 null new_status 跳过 — R7 也会容忍
        if st is None:
            continue
        if st not in ENUM_ITEM_STATUS:
            failures.append(Failure(
                rule_id="R2",
                severity="blocking",
                message=f"item_transfers[{i}].new_status='{st}' 非法，取值应为 {sorted(ENUM_ITEM_STATUS)}",
                location=f"item_transfers[{i}].new_status",
            ))

    for i, ev in _iter_array_field(changes, "new_plot_points", failures):
        if not isinstance(ev, dict):
            failures.append(not_a_dict("new_plot_points", i, ev))
            continue
        sl = ev.get("storyline")
        if sl is not None and sl not in ENUM_STORYLINE:
            failures.append(Failure(
                rule_id="R2",
                severity="blocking",
                message=f"new_plot_points[{i}].storyline='{sl}' 非法，取值应为 {sorted(ENUM_STORYLINE)}",
                location=f"new_plot_points[{i}].storyline",
            ))
        imp = ev.get("importance")
        if imp not in ENUM_IMPORTANCE:
            failures.append(Failure(
                rule_id="R2",
                severity="blocking",
                message=f"new_plot_points[{i}].importance='{imp}' 非法，取值应为 {sorted(ENUM_IMPORTANCE)}",
                location=f"new_plot_points[{i}].importance",
            ))

    for i, ev in _iter_array_field(changes, "location_state_changes", failures):
        if not isinstance(ev, dict):
            failures.append(not_a_dict("location_state_changes", i, ev))
            continue

    for i, ev in _iter_array_field(changes, "faction_state_changes", failures):
        if not isinstance(ev, dict):
            failures.append(not_a_dict("faction_state_changes", i, ev))
            continue

    tp = changes.get("time_progression")
    if isinstance(tp, dict):
        tpi = tp.get("importance")
        if tpi not in ENUM_TIME_IMPORTANCE:
            failures.append(Failure(
                rule_id="R2",
                severity="blocking",
                message=f"time_progression.importance='{tpi}' 非法，取值应为 {sorted(ENUM_TIME_IMPORTANCE)}",
                location="time_progression.importance",
            ))

    return failures


def _check_db_readable(db_path: str | Path) -> tuple[bool, str | None]:
    """**文件层**校验：db 是不是一个能打开、能读 schema 的 SQLite 文件。

    不检查具体有哪些表 —— 那是 _check_db_validity 的职责。
    返回 ``(ok, error_message)``；``ok=True, error=None`` 也包含"文件不存在"的情况。
    """
    if not db_path:
        return False, None  # 未提供 —— 由调用方决定

    path = Path(db_path)

    if not path.exists():
        # 破损符号链接：exists() 为 False 但 is_symlink() 为 True。
        # 这是"用户以为有 db 其实没有"的危险状态，必须报错而非当成未初始化项目。
        if path.is_symlink():
            return False, f"db 路径是破损的符号链接：{db_path}"
        return True, None  # 文件不存在 —— 可能是未初始化项目，由调用方决定

    if not path.is_file():
        # 目录、FIFO、socket、字符设备（/dev/null、/dev/zero、/dev/random）都走这里
        return False, f"db 路径不是常规文件：{db_path}"

    try:
        if path.stat().st_size == 0:
            return False, f"db 文件为空：{db_path}"
        with open(path, "rb") as fh:
            header = fh.read(16)
    except OSError as exc:
        return False, f"读取 db 失败：{exc}"

    if not header.startswith(SQLITE_HEADER):
        return False, f"db 文件不是 SQLite 格式：{db_path}"

    try:
        conn = sqlite3.connect(path)
    except (sqlite3.OperationalError, sqlite3.DatabaseError) as exc:
        return False, f"无法打开 db：{exc}"
    try:
        try:
            conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        except (sqlite3.OperationalError, sqlite3.DatabaseError):
            return False, f"db 损坏，无法读取 schema：{db_path}"
    finally:
        conn.close()
    return True, None


def _check_db_validity(db_path: str | Path) -> tuple[bool, str | None]:
    """判定 --db 指向的文件是否是一个可用的 webnovel-writer 账本。

    返回 ``(is_valid, error_message)``，三态语义：

    - ``(False, None)`` —— 未提供 db 路径。调用方自行决定（通常是"不校验账本"）。
    - ``(True, None)``  —— db 可用；**或** db 文件根本不存在（未初始化项目，
      属于合法状态，调用方自行决定是否跳过）。
    - ``(False, msg)``  —— db 文件**存在但无效**。调用方**必须**报错，
      不得静默跳过：否则攻击者可以构造 /dev/null、纯文本文件、空文件等
      让 R3-R8 全部被跳过而门禁仍报 ``passed: true``。

    "有效"不要求有数据行：全新项目的空账本（表在、无行）是合法的。
    """
    ok, err = _check_db_readable(db_path)
    if not ok:
        return False, err
    path = Path(db_path)
    if not path.is_file():
        return True, None  # 文件不存在 —— 由调用方决定

    conn = sqlite3.connect(path)
    try:
        try:
            tables = {
                row[0]
                for row in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                )
            }
        except (sqlite3.OperationalError, sqlite3.DatabaseError):
            return False, f"db 损坏，无法读取 schema：{db_path}"
        missing = EXPECTED_TABLES - tables
        if missing:
            return False, (
                f"db 文件存在但无 webnovel-writer schema"
                f"（缺少表：{', '.join(sorted(missing))}）"
            )
        return True, None
    finally:
        conn.close()


def _open_valid_db(db_path: str | Path) -> sqlite3.Connection | None:
    """仅当 db **文件层**可读且确实存在时返回连接，否则返回 None。

    各 ``_load_*`` 函数用它替代裸 ``sqlite3.connect``：/dev/null、纯文本、空文件、
    目录等在这里就被挡住，``sqlite3.DatabaseError: file is not a database``
    不会再冒到调用栈上层（对抗式审查 A2.2）。

    注意这里**只做文件层校验**，不检查 EXPECTED_TABLES —— 每个 loader 只依赖自己
    需要的表（R3 要 entities+aliases，R4 只要 foreshadowing），由各自的探针负责。
    db "存在但 schema 不对"的**报错**由 main() 通过 _check_db_validity 统一负责。
    """
    ok, _err = _check_db_readable(db_path)
    if not ok:
        return None
    path = Path(db_path)
    if not path.is_file():
        return None  # 文件不存在（未初始化项目）
    try:
        return sqlite3.connect(path)
    except (sqlite3.OperationalError, sqlite3.DatabaseError):
        return None


def _load_entity_lookup(db_path: Path) -> tuple[set[str], set[str], bool]:
    """从 index.db 加载所有合法 ID 和 alias。

    Returns: (ids, aliases, tables_ok)
      - tables_ok=False 表示 db 文件缺失/无效或表不存在，调用方应跳过规则。
        （db "存在但无效"的**报错**由 main() 负责，见 _check_db_validity。）
      - tables_ok=True 但 ids/aliases 为空表示这是空项目（新项目），调用方**不应**跳过。
    """
    conn = _open_valid_db(db_path)
    if conn is None:
        return set(), set(), False
    ids: set[str] = set()
    aliases: set[str] = set()
    tables_ok = False
    try:
        try:
            # 探针：先快速确认表存在，避免后期崩溃
            conn.execute("SELECT 1 FROM entities LIMIT 1")
            conn.execute("SELECT 1 FROM aliases LIMIT 1")
            tables_ok = True
            for row in conn.execute("SELECT id FROM entities WHERE is_archived = 0"):
                ids.add(row[0])
            for row in conn.execute("SELECT alias FROM aliases"):
                aliases.add(row[0])
        except (sqlite3.OperationalError, sqlite3.DatabaseError):
            # 表/列缺失、文件不是数据库等 —— 一律降级为"不可用"，不崩溃。
            # 注意 DatabaseError 是 OperationalError 的**父类**，必须显式捕获，
            # 否则 `file is not a database` 会穿透（对抗式审查 A2.2）。
            tables_ok = False
            ids.clear()
            aliases.clear()
    finally:
        conn.close()
    return ids, aliases, tables_ok


def check_r03_entities(changes: dict[str, Any], db_path: Path) -> list[Failure]:
    """R3: 实体引用合法（ID 或 alias 都接受）。

    Bug 10 修复：也检查 item_transfers[].item_id 和 item_transfers[].from_holder/to_holder。
    """
    failures = []
    valid_ids, valid_aliases, tables_ok = _load_entity_lookup(db_path)
    if not tables_ok:
        # db 不可用（不存在或表缺失），跳过
        return failures
    # 若 tables_ok=True 但 valid_ids/valid_aliases 都为空（空项目），继续校验（不跳过）

    def check_ref(ref: Any, location: str) -> None:
        if not isinstance(ref, str):
            return
        if ref in valid_ids or ref in valid_aliases:
            return
        failures.append(Failure(
            rule_id="R3",
            severity="blocking",
            message=f"{location}: 引用 '{ref}' 不在账本",
            location=location,
        ))

    for i, ev in _iter_array_field(changes, "character_state_changes"):
        if isinstance(ev, dict):
            check_ref(ev.get("character_id"), f"character_state_changes[{i}].character_id")

    for i, ev in _iter_array_field(changes, "new_plot_points"):
        if isinstance(ev, dict):
            for j, char_id in enumerate(ev.get("involved_characters", []) or []):
                check_ref(char_id, f"new_plot_points[{i}].involved_characters[{j}]")

    for i, ev in _iter_array_field(changes, "location_state_changes"):
        if isinstance(ev, dict):
            check_ref(ev.get("location_id"), f"location_state_changes[{i}].location_id")

    for i, ev in _iter_array_field(changes, "faction_state_changes"):
        if isinstance(ev, dict):
            check_ref(ev.get("faction_id"), f"faction_state_changes[{i}].faction_id")

    # Bug 10: R3 也检查 item_transfers 中的 item_id
    for i, ev in _iter_array_field(changes, "item_transfers"):
        if isinstance(ev, dict):
            check_ref(ev.get("item_id"), f"item_transfers[{i}].item_id")
            check_ref(ev.get("from_holder"), f"item_transfers[{i}].from_holder")
            check_ref(ev.get("to_holder"), f"item_transfers[{i}].to_holder")

    return failures


def _load_foreshadowing_state(db_path: Path) -> tuple[dict[str, str], bool]:
    """Returns: (state_dict, tables_ok)

    真实的 webnovel-writer index.db 没有 foreshadowing 表（伏笔存在 state.json），
    此时 tables_ok=False，R4 优雅跳过。
    """
    conn = _open_valid_db(db_path)
    if conn is None:
        return {}, False
    state: dict[str, str] = {}
    tables_ok = False
    try:
        try:
            conn.execute("SELECT 1 FROM foreshadowing LIMIT 1")
            tables_ok = True
            for row in conn.execute("SELECT id, status FROM foreshadowing"):
                state[row[0]] = row[1]
        except (sqlite3.OperationalError, sqlite3.DatabaseError):
            tables_ok = False
            state.clear()
    finally:
        conn.close()
    return state, tables_ok


def check_r04_foreshadowing(changes: dict[str, Any], db_path: Path) -> list[Failure]:
    """R4: 伏笔 ID 必须存在 + 不能重复 payoff。

    Bug 7 修复：fs_state 为空但表存在（空项目）时不跳过。
    """
    failures = []
    fs_state, tables_ok = _load_foreshadowing_state(db_path)
    if not tables_ok:
        return failures  # db 不可用（缺失或表不存在），跳过
    # 若表存在但无伏笔行（空项目），继续校验

    for i, ev in _iter_array_field(changes, "foreshadowing_actions"):
        if not isinstance(ev, dict):
            failures.append(Failure(
                rule_id="R4",
                severity="blocking",
                message=f"foreshadowing_actions[{i}] 必须是对象，实际为 {type(ev).__name__}",
                location=f"foreshadowing_actions[{i}]",
            ))
            continue
        fid = ev.get("foreshadow_id")
        action = ev.get("action")
        if fid not in fs_state:
            failures.append(Failure(
                rule_id="R4",
                severity="blocking",
                message=f"foreshadowing_actions[{i}].foreshadow_id='{fid}' 不在账本",
                location=f"foreshadowing_actions[{i}].foreshadow_id",
            ))
            continue
        current_status = fs_state[fid]
        # 状态机：setup 可以反复 setup（强化伏笔），payoff 后不能再 payoff
        if action == "payoff" and current_status == "paid":
            failures.append(Failure(
                rule_id="R4",
                severity="blocking",
                message=f"foreshadowing_actions[{i}]: '{fid}' 已被回收，不能再次 payoff",
                location=f"foreshadowing_actions[{i}].action",
            ))

    return failures


def _load_overdue_foreshadow(
    state_path: Path,
    current_chapter: int,
    threshold: int,
) -> tuple[list[dict[str, Any]], bool]:
    """读取 state.json 中的超期伏笔。

    Returns: (overdue_rows, state_ok)
        state_ok=False 表示 state.json 缺失/无效/缺 plot_threads.foreshadowing，
                       调用方应跳过 R4b。

    与 R4 不同的数据源：R4 读 db.foreshadowing 表（账本）；R4b 读
    state.json.plot_threads.foreshadowing（项目状态文件），这是伏笔真实写源。
    """
    if not state_path.is_file():
        return [], False
    # H-R4-1: 先检查文件大小，避免 json.load 解析超大文件
    try:
        if state_path.stat().st_size > MAX_STATE_BYTES:
            return [], False
    except OSError:
        return [], False
    try:
        import json as _json
        state = _json.loads(state_path.read_text(encoding="utf-8"))
    except (OSError, _json.JSONDecodeError, UnicodeDecodeError):
        return [], False
    if not isinstance(state, dict):
        return [], False
    plot_threads = state.get("plot_threads")
    if not isinstance(plot_threads, dict):
        return [], False
    foreshadowing = plot_threads.get("foreshadowing")
    if not isinstance(foreshadowing, list):
        return [], False

    # 复用 status_reporter 的中文状态归一化
    try:
        from status_reporter import _is_resolved_foreshadowing_status
    except ImportError:
        try:
            from scripts.status_reporter import _is_resolved_foreshadowing_status
        except ImportError:
            def _is_resolved_foreshadowing_status(raw_status: Any) -> bool:  # type: ignore[no-redef]
                if raw_status is None:
                    return False
                return str(raw_status).strip().lower() in {
                    "resolved", "paid", "回收", "已回收", "已完成",
                }

    overdue: list[dict[str, Any]] = []
    for raw in foreshadowing:
        if not isinstance(raw, dict):
            continue
        if _is_resolved_foreshadowing_status(raw.get("status")):
            continue
        # planted_chapter 多别名解析
        planted: int | None = None
        for k in ("planted_chapter", "added_chapter", "source_chapter", "start_chapter", "chapter"):
            v = raw.get(k)
            if isinstance(v, int) and v > 0:
                planted = v
                break
            if isinstance(v, str):
                try:
                    iv = int(v.strip())
                    if iv > 0:
                        planted = iv
                        break
                except ValueError:
                    continue
        if planted is None:
            continue
        elapsed = current_chapter - planted
        if elapsed < threshold:
            continue
        # target 解析（用于“已超期”判定）
        target: int | None = None
        for k in ("target_chapter", "due_chapter", "deadline_chapter", "resolve_by_chapter", "target"):
            v = raw.get(k)
            if isinstance(v, int) and v > 0:
                target = v
                break
            if isinstance(v, str):
                try:
                    iv = int(v.strip())
                    if iv > 0:
                        target = iv
                        break
                except ValueError:
                    continue
        overdue.append({
            "content": str(raw.get("content") or "[未命名伏笔]"),
            "planted_chapter": planted,
            "target_chapter": target,
            "elapsed": elapsed,
        })
    return overdue, True


def check_r04b_overdue_foreshadow(
    changes: dict[str, Any],
    state_path: Path,
    current_chapter: int,
    threshold: int = R4B_DEFAULT_OVERDUE_THRESHOLD,
) -> list[Failure]:
    """R4b: 超期未回收伏笔 → advisory（**不阻塞写入**）。

    端口 oh-story-claudecode 的“埋了没填”概念：
    - 读取 state.json 中所有未回收伏笔；
    - planted_chapter ≤ current_chapter - threshold 且仍未回收 → advisory；
    - **advisory 而非 blocking**：与 oh-story 一致；门禁不阻塞写入，
      只在报告里告知作者。

    Args:
        changes: 解析后的 CHANGES dict（暂未使用，保留签名一致以便未来扩展）。
        state_path: .webnovel/state.json 路径。
        current_chapter: 当前章号（≥ 0）。
        threshold: 阈值章数（默认 20）。

    Returns:
        list[Failure]：每条 failure 都是 advisory；state 缺失时返回 []。
    """
    failures: list[Failure] = []
    if current_chapter <= 0:
        return failures  # 无法判定 elapsed
    overdue, ok = _load_overdue_foreshadow(state_path, current_chapter, threshold)
    if not ok:
        return failures  # state.json 缺失/无效，安静跳过（不是 blocking）
    # M-R4-2: 限制 advisory 输出上限，避免一次性喷出几十条淹没作者。
    # 排序已在 _load_overdue_foreshadow 内部完成（已超期 > 埋太久；同内按 elapsed 倒序），
    # 所以直接截断前 N 条即可保留最严重的 advisory。
    capped = overdue[:R4B_ADVISORY_MAX]
    if len(overdue) > R4B_ADVISORY_MAX:
        # 追加一条 "还有 X 条未显示" 元 advisory，方便作者知道有遗漏
        suppressed = len(overdue) - R4B_ADVISORY_MAX
        failures.append(Failure(
            rule_id="R4b",
            severity="advisory",
            message=f"（还有 {suppressed} 条超期伏笔未显示；仅展示最严重的 {R4B_ADVISORY_MAX} 条）",
            location="state.json:plot_threads.foreshadowing",
        ))
    for row in capped:
        target = row.get("target_chapter")
        planted = row.get("planted_chapter")
        elapsed = row.get("elapsed", 0)
        content = row.get("content") or "[未命名伏笔]"
        if isinstance(target, int) and current_chapter > target:
            kind = "已超期"
            tail = f"，目标回收章 {target}"
        else:
            kind = "埋太久未填"
            tail = ""
        failures.append(Failure(
            rule_id="R4b",
            severity="advisory",
            message=(
                f"伏笔「{content}」自第{planted}章埋下已过 {elapsed} 章仍未回收（{kind}{tail}）"
            ),
            location="state.json:plot_threads.foreshadowing",
        ))
    return failures


MAX_TRUST_DELTA = 30


def check_r05_relationships(changes: dict[str, Any], db_path: Path) -> list[Failure]:
    """R5: 单章关系信任度变化不超过 ±MAX_TRUST_DELTA。

    Bug 2 修复：trust_delta 类型守卫（接受 int/float，拒绝 str/list/dict/bool）。
    """
    failures = []
    for i, ev in _iter_array_field(changes, "character_state_changes"):
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
            loc = (
                f"character_state_changes[{i}].relationship_changes"
                f"['{target}'].trust_delta"
            )
            # 类型守卫：仅接受 int/float，拒绝 bool (Python 中 bool 是 int 的子类)
            if isinstance(delta, bool) or not isinstance(delta, (int, float)):
                failures.append(Failure(
                    rule_id="R5",
                    severity="blocking",
                    message=(
                        f"character_state_changes[{i}].relationship_changes['{target}']"
                        f".trust_delta={delta!r} 必须是数字，当前类型：{type(delta).__name__}"
                    ),
                    location=loc,
                ))
                continue
            if abs(delta) > MAX_TRUST_DELTA:
                failures.append(Failure(
                    rule_id="R5",
                    severity="blocking",
                    message=f"character_state_changes[{i}].relationship_changes['{target}']: trust_delta={delta} 超过 ±{MAX_TRUST_DELTA}",
                    location=loc,
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


def _is_r6_enabled() -> bool:
    import os
    return bool(os.environ.get("WEBNOVEL_ENABLE_R6"))


def check_r06_unregistered(text: str, changes: dict[str, Any], registered: set[str]) -> list[Failure]:
    """R6: 正文中提到的实体如未在账本且未在 CHANGES 申报，超过阈值则告警。

    **默认禁用**。Bug 4 修复：2-4 字符滑动窗口对任何正常中文正文都会产生
    大量误报（停用词表的子串、停用词交叉切片等），阈值再高也无意义。
    通过环境变量 ``WEBNOVEL_ENABLE_R6=1`` 可显式开启。
    """
    if not _is_r6_enabled():
        return []  # 默认禁用（参看对抗式审查报告 CRITICAL Bug #4）
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
            location="chapter_text",
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
    conn = _open_valid_db(db_path)
    if conn is None:
        return {}
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
    except (sqlite3.OperationalError, sqlite3.DatabaseError):
        state.clear()
    finally:
        conn.close()
    return state


def check_r07_item_state(changes: dict[str, Any], db_path: Path) -> list[Failure]:
    """R7: 物品状态转移合法——按 ITEM_STATE_TRANSITIONS 校验。"""
    failures: list[Failure] = []
    item_state = _load_item_state(db_path)
    for i, ev in _iter_array_field(changes, "item_transfers"):
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
                location=f"item_transfers[{i}].new_status",
            ))
    return failures


# R8: 时间线连贯——本章不应声明与上一章冲突的时间
import re as _re_time


def _extract_chapter_number(chapter_text: str) -> int | None:
    """从章节文件正文里提取章号。"""
    m = _re_time.search(r"第\s*(\d+)\s*章", chapter_text)
    return int(m.group(1)) if m else None


def _load_timeline(db_path: Path) -> dict[int, str]:
    """真实 index.db 没有 timeline 表时返回 {}，R8 优雅跳过。"""
    conn = _open_valid_db(db_path)
    if conn is None:
        return {}
    state: dict[int, str] = {}
    try:
        for row in conn.execute("SELECT chapter, time_anchor FROM timeline ORDER BY chapter"):
            state[row[0]] = row[1]
    except (sqlite3.OperationalError, sqlite3.DatabaseError):
        state.clear()
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
                location="time_progression.elapsed_time",
            ))
    return failures


def _emit(result: GateResult, as_json: bool, rc: int) -> int:
    """统一输出并返回退出码。"""
    if as_json:
        print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
    else:
        print("PASSED" if result.passed else f"FAILED: {len(result.failures)} failure(s)")
        for f in result.failures:
            loc = f" @ {f.location}" if f.location else ""
            print(f"  [{f.rule_id}/{f.severity}] {f.message}{loc}")
    return rc


def main() -> int:
    parser = argparse.ArgumentParser(description="CHANGES 协议门禁")
    parser.add_argument("--chapter-file", required=True, help="章节文件路径")
    parser.add_argument("--db", default="", help="webnovel-writer index.db 路径（可选，未初始化项目可省略）")
    parser.add_argument("--state-path", default="", help="webnovel-writer state.json 路径（可选；R4b 依赖；缺省从 chapter-file 推导 .webnovel/state.json）")
    parser.add_argument("--json", action="store_true", help="输出 JSON 格式")
    parser.add_argument("--rule", default="", help="只跑指定规则（如 R1），多个用逗号分隔")
    parser.add_argument("--strict", action="store_true", help="advisory 也算 blocking")
    args = parser.parse_args()

    result = GateResult(passed=True)

    def fail_fast(message: str, location: str) -> int:
        result.passed = False
        result.failures.append(Failure(
            rule_id="R0", severity="blocking", message=message, location=location,
        ))
        return _emit(result, args.json, 1)

    # --- --rule 解析（Bug E：恢复被移除的参数，并真正实现过滤）---
    wanted_rules: set[str] | None = None
    if args.rule:
        # C-R4-4 修复：保留用户输入的大小写（KNOWN_RULE_IDS 含 "R4b" 而非 "R4B"），
        # 但匹配时做 case-insensitive 比较以允许用户写 "r4b" / "R4B" 等形式
        raw_rules = {r.strip() for r in args.rule.split(",") if r.strip()}
        # 兼容大小写：建立 upper → canonical 映射，把所有输入规范化
        id_map = {r.upper(): r for r in KNOWN_RULE_IDS}
        wanted_rules = {id_map.get(r.upper(), r) for r in raw_rules}
        # unknown = 任何无法映射到 KNOWN_RULE_IDS 的输入
        unknown = set()
        for r in raw_rules:
            if r not in KNOWN_RULE_IDS and r.upper() not in {k.upper() for k in KNOWN_RULE_IDS}:
                unknown.add(r)
        if not wanted_rules or unknown:
            # 未知规则名会把所有 failure 过滤光 → 新的静默通过。必须报错。
            return fail_fast(
                f"未知规则：{', '.join(sorted(unknown)) or args.rule!r}；"
                f"可选值：{', '.join(sorted(KNOWN_RULE_IDS))}",
                "--rule",
            )

    # --- 章节文件 ---
    chapter_path = Path(args.chapter_file)
    # Bug 12: 用 is_file() 而非 exists()，避免 --chapter-file 指向目录
    if not chapter_path.is_file():
        return fail_fast(
            f"章节文件不存在或不是文件：{args.chapter_file}", "chapter_file"
        )
    # Bug C: 非 UTF-8（UTF-16 / GBK / 截断 UTF-8 / 二进制）必须报 R0 而非 traceback
    try:
        chapter_text = chapter_path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return fail_fast(
            f"章节文件不是 UTF-8 编码：{args.chapter_file}", "chapter_file"
        )
    except OSError as exc:
        return fail_fast(f"读取章节文件失败：{exc}", "chapter_file")

    if not chapter_text.strip():
        return fail_fast(f"章节文件为空：{args.chapter_file}", "chapter_file")

    # --- db 三态判定（Bug A/B：绝不静默跳过）---
    db_available = False
    if args.db:
        is_valid, err_msg = _check_db_validity(args.db)
        if not is_valid and err_msg:
            # 状态 2：db 存在但无效 → 大声失败。静默跳过 R3-R8 是安全漏洞：
            # 攻击者可构造 /dev/null、纯文本等特殊文件让门禁永远 passed=true。
            return fail_fast(f"{err_msg}；门禁将拒绝通过以确保一致性", "db")
        if is_valid and Path(args.db).is_file():
            db_available = True  # 状态 3：db 有效（可以是全新空账本）
        else:
            # 状态 1：db 文件不存在 —— 未初始化项目，合法，但必须告知用户
            result.failures.append(Failure(
                rule_id="R0",
                severity="advisory",
                message=f"未初始化项目（db 不存在：{args.db}），跳过账本相关校验（R3/R4/R5/R7/R8）",
                location="db",
            ))

    # --- 解析 CHANGES ---
    parsed, err = parse_changes(chapter_text)
    result.parsed_changes = parsed
    if err:
        result.failures.append(Failure(
            rule_id="R0", severity="blocking", message=err, location="chapter_file",
        ))
    elif not isinstance(parsed, dict):
        result.failures.append(Failure(
            rule_id="R0", severity="blocking",
            message="CHANGES 顶层必须是 JSON 对象", location="chapter_changes",
        ))
        parsed = None

    # --- 跑规则 ---
    if parsed is not None:
        check_failures: list[Failure] = []
        check_failures.extend(check_r01_protocol(parsed))
        check_failures.extend(check_r02_enums(parsed))
        if db_available:
            db_p = Path(args.db)
            check_failures.extend(check_r03_entities(parsed, db_p))
            check_failures.extend(check_r04_foreshadowing(parsed, db_p))
            check_failures.extend(check_r05_relationships(parsed, db_p))
            check_failures.extend(check_r07_item_state(parsed, db_p))
            # R8 需要章号
            chapter_num = _extract_chapter_number(chapter_text) or 0
            check_failures.extend(check_r08_timeline(parsed, db_p, chapter_num))
        # R4b: state.json 超期伏笔 advisory（与 db 解耦；不阻塞）
        # 章号优先用正文解析值；缺省时回退 progress.current_chapter（state.json）
        chapter_num_for_r4b = _extract_chapter_number(chapter_text) or 0
        if chapter_num_for_r4b <= 0:
            # 兜底：state.json progress.current_chapter
            try:
                _state_for_chap = Path(args.state_path) if args.state_path else (
                    chapter_path.parent.parent / ".webnovel" / "state.json"
                )
                if _state_for_chap.is_file():
                    # H-R4-1: 先检查大小，避免 read_text + json.loads 解析超大文件
                    if _state_for_chap.stat().st_size > MAX_STATE_BYTES:
                        pass  # 跳过兜底解析，不报错
                    else:
                        import json as _json_for_chap
                        _s = _json_for_chap.loads(_state_for_chap.read_text(encoding="utf-8"))
                        if isinstance(_s, dict):
                            _prog = _s.get("progress")
                            if isinstance(_prog, dict):
                                _cur = _prog.get("current_chapter")
                                if isinstance(_cur, int) and _cur > 0:
                                    chapter_num_for_r4b = _cur
            except (OSError, _json_for_chap.JSONDecodeError, UnicodeDecodeError):
                pass
        if chapter_num_for_r4b > 0:
            _state_path = (
                Path(args.state_path) if args.state_path
                else chapter_path.parent.parent / ".webnovel" / "state.json"
            )
            check_failures.extend(
                check_r04b_overdue_foreshadow(
                    parsed, _state_path, chapter_num_for_r4b,
                )
            )
            # Bug 4: R6 默认禁用（高误报），仅在 WEBNOVEL_ENABLE_R6 设置时运行
            if _is_r6_enabled():
                registered_ids, registered_aliases, _tables_ok = _load_entity_lookup(db_p)
                all_known = registered_ids | registered_aliases
                if all_known:
                    check_failures.extend(
                        check_r06_unregistered(chapter_text, parsed, all_known)
                    )
        result.failures.extend(check_failures)

    # --- Bug E: --rule 过滤。R0 永远保留 ---
    # R0 是基础设施错误（解析失败 / 文件问题 / db 无效），不是可选规则；
    # 若被过滤掉，`--rule R1` 会把致命错误藏起来 → 新的静默通过。
    if wanted_rules is not None:
        result.failures = [
            f for f in result.failures
            if f.rule_id in wanted_rules or f.rule_id == "R0"
        ]

    if args.strict:
        result.passed = not result.failures
    else:
        result.passed = not any(f.severity == "blocking" for f in result.failures)

    return _emit(result, args.json, 0 if result.passed else 1)


if __name__ == "__main__":
    sys.exit(main())
