"""Deterministically align writer declarations with final-prose extraction.

The reconciliation exists to answer one question: *does the Writer's proposal describe
the same facts the final prose actually shows?* It is not a second Canon store and it does
not decide what is true — it pairs a declaration with an observation, and only when a
pair is impossible does it report a conflict.

Earlier versions only understood `character_state_changes -> state_deltas` plus the realm
special case, so a normal chapter's item transfer, location change, foreshadow setup and
open question all fell into `opaque` and `matched` stayed 0 even when the proposal and the
extraction agreed. The mapping below covers the structured categories the CHANGES protocol
actually emits, and compares values with a normalization pass that treats paraphrases and
synonyms as the same fact while still surfacing genuinely different values.
"""
from __future__ import annotations

import difflib
import hashlib
import json
import re
from collections import defaultdict
from typing import Any

from .chapter_commit_schema import ExtractionResult

REQUIRED_CHANGE_FIELDS = (
    "character_state_changes", "new_plot_points", "foreshadowing_actions",
    "location_state_changes", "faction_state_changes", "time_progression",
    "item_transfers", "unresolved_questions",
)
FIELD_ALIASES = {
    "修为": "realm", "境界": "realm", "realm": "realm",
    "持有": "holder", "持有者": "holder", "归属": "holder", "归属者": "holder",
    "所有": "holder", "保管": "holder",
    "owner": "holder", "holder": "holder", "custodian": "holder", "custody": "holder",
    "伤势": "injury", "伤情": "injury", "injury": "injury", "health": "injury",
    "时间": "time", "年代": "time", "日期": "time", "time": "time",
    "位置": "location.current", "所在地": "location.current",
}
VALUE_ALIASES = {
    "foundation establishment": "筑基", "foundation_establishment": "筑基",
    "foundation-establishment": "筑基", "筑基期": "筑基",
}
SUPPORTED_MAPPINGS = [
    "character_state_changes -> state_deltas / character_state_changed",
    "realm entity_delta patch/current",
    "power_breakthrough event realm",
    "item_transfers -> holder state_delta / artifact_obtained",
    "location_state_changes -> location state_delta",
    "faction_state_changes -> faction state_delta",
    "foreshadowing_actions -> open_loop/promise events",
    "unresolved_questions -> open_loop content",
    "new_plot_points -> accepted event text (paraphrase match)",
    "time_progression -> accepted event/time state (paraphrase match)",
]
OPAQUE_CATEGORIES = [
    "non-realm entity_deltas",
    "unmapped accepted_events",
]

# Text facts are paired by meaning rather than identity. The thresholds are deliberately
# high: a false match would hide a real proposal/observation divergence, which is worse
# than leaving a pair visibly unmatched.
TEXT_MATCH_MIN_RATIO = 0.60
TEXT_MATCH_MIN_BIGRAM = 0.42
# Free-text declarations (plot points, open questions, `new_state` summaries) are whole
# paragraphs, while observations are short field values. Comparing them with the strict
# structured-value thresholds leaves every real pair unmatched. These looser thresholds are
# used *only* for text pairing — structured values still use the strict pair above.
TEXT_SUMMARY_MIN_RATIO = 0.45
TEXT_SUMMARY_MIN_BIGRAM = 0.22
# A long declaration and a long observation rarely share enough surface n-grams even when
# they describe one fact ("老周反复说‘我只负责看站，不负责记录’" vs the extractor's
# "……反复以……‘我只负责看站，不负责记录’回应"). Whole-text ratio is diluted by the extra
# detail on both sides, so free-text pairing also accepts a strong shared core phrase.
TEXT_SUMMARY_MIN_CONTAINMENT = 0.60
TEXT_SUMMARY_MIN_LCS = 10
# Short texts ("记录消失" / "原有记录不见了") are dominated by a shared prefix, which makes
# the ratio and bigram thresholds unsafe: "老周负责看站" / "老周负责记录" scores high while
# stating two different facts. For a short text the shorter whole phrase has to be present.
TEXT_SHORT_MAX_CHARS = 16
TEXT_SHORT_MIN_CONTAINMENT = 0.75
# Frequency/degree markers that do not change the fact being stated.
TEXT_MATCH_NOISE = (
    "反复", "多次", "一再", "一遍遍", "连续", "再次", "又重新", "又一次",
    "两遍", "三遍", "每次",
)
# High-confidence paraphrases. Each mapping keeps the predicate intact; it only removes
# wording differences that would otherwise make one fact look like two.
TEXT_MATCH_EQUIVALENTS = (
    ("不见踪影", "消失"), ("不见了", "消失"), ("查不到", "消失"),
    ("找不到", "消失"), ("没了", "消失"), ("删掉", "消失"),
    ("删除", "消失"), ("抹除", "消失"), ("抹去", "消失"), ("清除", "消失"),
    ("注意到", "发现"), ("察觉到", "发现"),
    ("答道", "说"), ("说道", "说"), ("问道", "说"), ("回答", "说"), ("回应", "说"),
    ("告诫", "警告"), ("提醒", "警告"),
    ("汇报", "报告"), ("报给", "报告"), ("上报", "报告"), ("通报", "报告"),
    ("返回", "回"), ("回到", "回"),
    ("检索", "查"), ("查询", "查"), ("搜索", "查"), ("查找", "查"), ("搜寻", "查"),
    ("名下", "名义"), ("口头", ""),
)
# Structured facts can describe the same object with a different modifier ("密封胶残片" /
# "透明胶残片"). When the field is the same and exactly one observed entity is this close,
# the pair is treated as the same entity and the alias is recorded in the matched entry.
ENTITY_MATCH_MIN_SCORE = 0.50

_CN_DIGITS = {"〇": 0, "零": 0, "一": 1, "二": 2, "两": 2, "三": 3, "四": 4,
              "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}
_CN_UNITS = {"十": 10, "百": 100, "千": 1000}


def _digest(value: Any) -> str:
    raw = value if isinstance(value, str) else json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _key(value: Any) -> str:
    text = str(value or "").strip().casefold().replace("_", " ")
    return re.sub(r"\s+", " ", text)


def _field(value: Any) -> str:
    normalized = _key(value)
    return FIELD_ALIASES.get(normalized, normalized)


def normalize_field(value: Any) -> str:
    """Canonical field key shared by reconciliation and the Canon fact validator."""
    return _field(value)


def _value(value: Any) -> str:
    normalized = _key(value)
    return VALUE_ALIASES.get(normalized, normalized)


def _strip_for_compare(text: str) -> str:
    return re.sub(r"[\s，,。．.!！?？；;：:“”\"'‘’（）()\[\]【】<>《》…—\-、/]+", "", str(text or "")).casefold()


def _cn_number(token: str) -> int | None:
    token = str(token or "").strip()
    if not token:
        return None
    if token.isdigit():
        return int(token)
    total = 0
    current = 0
    for char in token:
        if char in _CN_DIGITS:
            current = _CN_DIGITS[char]
        elif char in _CN_UNITS:
            unit = _CN_UNITS[char]
            if current == 0:
                current = 1
            total += current * unit
            current = 0
        else:
            return None
    return total + current


_NUM_TOKEN = r"[〇零一二两三四五六七八九十百千\d]+"
_YEARS_AGO_RE = re.compile(rf"({_NUM_TOKEN})\s*年\s*(?:之)?前")
_YEAR_RE = re.compile(rf"({_NUM_TOKEN})\s*年")


def _time_values(text: str) -> set[tuple[str, int]]:
    """Structured time mentions: ('ago', n) for `n年前`, ('year', n) for `n年`."""
    raw = str(text or "")
    found: set[tuple[str, int]] = set()
    for match in _YEARS_AGO_RE.finditer(raw):
        number = _cn_number(match.group(1))
        if number is not None:
            found.add(("ago", number))
    for match in _YEAR_RE.finditer(raw):
        # Skip the `年` covered by `n年前`.
        if _YEARS_AGO_RE.search(raw, max(0, match.start() - 2)):
            continue
        number = _cn_number(match.group(1))
        if number is not None:
            found.add(("year", number))
    return found


_INJURY_RE = re.compile(r"(烫伤|烧伤|骨折|受伤|擦伤|割伤|伤口|渗血|渗液|红肿|淤青|中毒|昏迷|残疾|重伤|轻伤|裂伤|创面|虎口)")
_ABSENCE_RE = re.compile(r"(无伤|完好|痊愈|伤愈|康复|没伤|没有伤|未受伤|无碍|好了|愈合)")
_NEGATION_RE = re.compile(r"(无|未|不|没|没有|并非|不是)")
_NUMBER_RE = re.compile(r"\d+(?:\.\d+)?")


def _bigrams(text: str) -> set[str]:
    clean = _strip_for_compare(text)
    if len(clean) < 2:
        return {clean} if clean else set()
    return {clean[i:i + 2] for i in range(len(clean) - 1)}


def _text_ratio(a: str, b: str) -> float:
    return difflib.SequenceMatcher(None, _strip_for_compare(a), _strip_for_compare(b)).ratio()


def _bigram_overlap(a: str, b: str) -> float:
    left, right = _bigrams(a), _bigrams(b)
    if not left or not right:
        return 0.0
    return len(left & right) / len(left | right)


def _normalize_for_pairing(text: str) -> str:
    """Normalize free text for summary pairing without touching structured values."""
    normalized = _strip_for_compare(text)
    for noise in TEXT_MATCH_NOISE:
        normalized = normalized.replace(noise, "")
    for source, target in TEXT_MATCH_EQUIVALENTS:
        normalized = normalized.replace(source, target)
    return normalized


def _pairing_ngrams(text: str, size: int = 4) -> set[str]:
    normalized = _normalize_for_pairing(text)
    if len(normalized) < size:
        return {normalized} if normalized else set()
    return {normalized[i:i + size] for i in range(len(normalized) - size + 1)}


def _pairing_containment(a: str, b: str, size: int = 4) -> float:
    left, right = _pairing_ngrams(a, size), _pairing_ngrams(b, size)
    if not left or not right:
        return 0.0
    return len(left & right) / min(len(left), len(right))


def _pairing_ratio(a: str, b: str) -> float:
    return difflib.SequenceMatcher(
        None, _normalize_for_pairing(a), _normalize_for_pairing(b)
    ).ratio()


def _pairing_bigram_overlap(a: str, b: str) -> float:
    left, right = _pairing_ngrams(a, 2), _pairing_ngrams(b, 2)
    if not left or not right:
        return 0.0
    return len(left & right) / len(left | right)


def _longest_common_substring(a: str, b: str) -> int:
    left, right = _normalize_for_pairing(a), _normalize_for_pairing(b)
    if not left or not right:
        return 0
    match = difflib.SequenceMatcher(None, left, right, autojunk=False).find_longest_match(
        0, len(left), 0, len(right)
    )
    return match.size


def texts_share_fact(a: str, b: str) -> bool:
    """True when two free-text descriptions are the same fact, not merely similar words.

    Long texts may pair on ratio, containment of the shorter text, or a shared core phrase
    (>= 10 characters) such as a quotation. Short texts are stricter: the shorter phrase
    must be essentially contained, because a shared prefix ("老周负责……") is not evidence
    that the predicates agree.
    """
    left = _normalize_for_pairing(a)
    right = _normalize_for_pairing(b)
    if not left or not right:
        return left == right
    if left == right:
        return True

    shorter, longer = (left, right) if len(left) <= len(right) else (right, left)
    containment = _pairing_containment(a, b)

    if len(longer) <= TEXT_SHORT_MAX_CHARS:
        # Short vs short: a shared prefix is not a shared fact.
        if containment >= TEXT_SHORT_MIN_CONTAINMENT:
            return True
        lcs = _longest_common_substring(a, b)
        return lcs >= max(4, int(0.90 * len(shorter)))

    if len(shorter) <= TEXT_SHORT_MAX_CHARS:
        # Short vs long: the short statement must be present in the observation.
        lcs = _longest_common_substring(a, b)
        return containment >= TEXT_SHORT_MIN_CONTAINMENT or lcs >= max(
            TEXT_SUMMARY_MIN_LCS, int(0.80 * len(shorter))
        )

    return (
        _pairing_ratio(a, b) >= TEXT_SUMMARY_MIN_RATIO
        or _pairing_bigram_overlap(a, b) >= TEXT_SUMMARY_MIN_BIGRAM
        or containment >= TEXT_SUMMARY_MIN_CONTAINMENT
        or _longest_common_substring(a, b) >= TEXT_SUMMARY_MIN_LCS
    )


def _injury_present(text: str) -> bool:
    return bool(_INJURY_RE.search(str(text or "")))


def _injury_absent(text: str) -> bool:
    return bool(_ABSENCE_RE.search(str(text or "")))


def _numbers(text: str) -> set[str]:
    return set(_NUMBER_RE.findall(str(text or "")))


def values_equivalent(before: Any, after: Any) -> bool:
    """True when two values describe the same fact (exact, paraphrase or synonym)."""
    left, right = _value(before), _value(after)
    if left == right:
        return True
    left_clean, right_clean = _strip_for_compare(left), _strip_for_compare(right)
    if not left_clean or not right_clean:
        return left_clean == right_clean
    if left_clean in right_clean or right_clean in left_clean:
        return True

    left_time, right_time = _time_values(left), _time_values(right)
    if left_time or right_time:
        # Time is a hard dimension: two different elapsed values are not a paraphrase.
        return bool(left_time) and left_time == right_time

    left_injured, right_injured = _injury_present(left), _injury_present(right)
    left_absent, right_absent = _injury_absent(left), _injury_absent(right)
    if (left_injured and right_absent) or (right_injured and left_absent):
        return False
    if left_injured and right_injured:
        # Same injury family; different wording/sharpness is not a new fact.
        return True

    left_numbers, right_numbers = _numbers(left), _numbers(right)
    if left_numbers and right_numbers and left_numbers != right_numbers:
        return False

    if _bigram_overlap(left, right) >= TEXT_MATCH_MIN_BIGRAM:
        return True
    return _text_ratio(left, right) >= TEXT_MATCH_MIN_RATIO


def values_conflict(before: Any, after: Any, *, kind: str = "state") -> bool:
    """True only when the two values are provably different, not merely worded differently."""
    if values_equivalent(before, after):
        return False
    left, right = str(before or ""), str(after or "")
    left_time, right_time = _time_values(left), _time_values(right)
    if kind == "time" or left_time or right_time:
        return bool(left_time) and bool(right_time) and left_time != right_time
    left_injured, right_injured = _injury_present(left), _injury_present(right)
    left_absent, right_absent = _injury_absent(left), _injury_absent(right)
    if (left_injured and right_absent) or (right_injured and left_absent):
        return True
    if kind == "ownership":
        # Holder names are short identities: a different non-empty name is a different fact.
        return bool(_strip_for_compare(left)) and bool(_strip_for_compare(right))
    if kind == "realm":
        # Realm names are a closed-vocabulary identity: once normalized, two different
        # realm names are two different facts. Relationship descriptions are free text
        # ("有限合作" vs "以工单为凭的搭档"), so they are deliberately not hard conflicts.
        return bool(_strip_for_compare(left)) and bool(_strip_for_compare(right))
    left_numbers, right_numbers = _numbers(left), _numbers(right)
    if left_numbers and right_numbers and left_numbers != right_numbers:
        return True
    return False


def classify_fact_kind(field: str, value: Any) -> str:
    field_key = _field(field)
    value_text = str(value or "")
    if field_key in {"realm"}:
        return "realm"
    if field_key in {"holder"}:
        return "ownership"
    if field_key in {"injury"}:
        return "injury"
    if field_key in {"time"} or _time_values(value_text):
        return "time"
    if _injury_present(value_text) or _injury_absent(value_text):
        return "injury"
    if re.search(r"(持有|归属|所有|保管|owner|holder)", field_key):
        return "ownership"
    return "state"


def _changes_document(chapter_text: str):
    # Parser owns format recognition and the corresponding removal spans.
    from changes_gate import parse_changes_document

    return parse_changes_document(chapter_text)


def validate_proposed_changes(proposed: Any) -> dict[str, Any]:
    if not isinstance(proposed, dict):
        raise ValueError("CHANGES must be a JSON object")
    missing = set(REQUIRED_CHANGE_FIELDS) - proposed.keys()
    if missing:
        raise ValueError("CHANGES missing required fields: " + ", ".join(sorted(missing)))
    for name in REQUIRED_CHANGE_FIELDS:
        value = proposed[name]
        if name == "time_progression":
            if value is not None and not isinstance(value, dict):
                raise ValueError("CHANGES.time_progression must be an object or null")
        elif not isinstance(value, list):
            raise ValueError(f"CHANGES.{name} must be a list")
        elif any(not isinstance(item, dict) for item in value):
            raise ValueError(f"CHANGES.{name} items must be objects")
    return proposed


def split_chapter_and_changes(chapter_text: str) -> tuple[str, dict[str, Any]]:
    """Parse the proposal and return prose with the parser-selected source removed."""
    document = _changes_document(chapter_text)
    if document.error or document.proposed_changes is None:
        raise ValueError(f"invalid CHANGES: {document.error or 'missing parsed value'}")
    return document.prose_only, validate_proposed_changes(document.proposed_changes)


def prose_only_text(chapter_text: str) -> str:
    """Best-effort prose-only projection of a chapter file (never raises).

    This is the text the Reviewer actually reads. Unlike `split_chapter_and_changes` it does
    not require a valid proposal: a missing or malformed `<chapter_changes>` container yields
    the raw text, so callers that *hash* the result always get a stable value instead of an
    exception. Use `split_chapter_and_changes` when the parsed proposal itself is required.
    """
    try:
        return _changes_document(chapter_text).prose_only
    except Exception:
        return chapter_text


def prose_subject_sha256(chapter_text: str) -> str:
    """SHA-256 of the prose the Reviewer consumes, with the CHANGES container excluded.

    The full-draft hash (`draft_fingerprint`) changes when *any* byte of the working draft
    changes, including a `<chapter_changes>` reconciliation fix that leaves the prose
    untouched. Reviewing is a function of the prose plus the governed review context, not of
    the proposal block, so review validity is bound to this value instead. The full-draft
    hash is still recorded alongside it as artifact provenance.
    """
    return hashlib.sha256(prose_only_text(chapter_text).encode("utf-8")).hexdigest()


# --------------------------------------------------------------------------- #
# Proposal facts
# --------------------------------------------------------------------------- #


def _fact(*, entity: Any, field: str, value: Any, source_type: str, source_index: int,
          kind: str | None = None, text: str = "", old: Any = None,
          event_type: str = "") -> dict[str, Any]:
    raw_value = "" if value is None else str(value)
    return {
        "entity": _key(entity),
        "field": _field(field),
        "value": _value(raw_value),
        "raw_value": raw_value,
        "old": "" if old is None else str(old),
        "kind": kind or classify_fact_kind(field, raw_value),
        "source_type": source_type,
        "source_index": source_index,
        "text": str(text or raw_value),
        "event_type": event_type,
    }


def _proposal_facts(proposed: dict[str, Any]) -> list[dict[str, Any]]:
    facts: list[dict[str, Any]] = []
    for index, item in enumerate(proposed["character_state_changes"]):
        entity = item.get("entity_id") or item.get("character_id")
        raw_value = item.get("new") or item.get("new_value") or item.get("new_state")
        raw_field = item.get("field") or item.get("field_name")
        if not raw_field and isinstance(raw_value, str):
            match = re.match(r"\s*([^:=：]+)\s*[:=：]\s*(.+)\s*$", raw_value)
            if match:
                raw_field, raw_value = match.group(1), match.group(2)
            elif _value(str(raw_value).removeprefix("突破")) in {"筑基", "炼气", "金丹", "元婴"}:
                raw_field, raw_value = "realm", str(raw_value).removeprefix("突破")
        if entity and raw_field and raw_value is not None:
            facts.append(_fact(entity=entity, field=str(raw_field), value=raw_value,
                               source_type="character_state_changes", source_index=index))
        elif entity and raw_value:
            # `new_state` is commonly a free-text state description. Keep it as a text
            # declaration so it can still be paired with the observation that describes it.
            facts.append(_fact(entity=entity, field="__state_text__", value=raw_value,
                               source_type="character_state_changes", source_index=index,
                               kind="text", text=str(raw_value)))
        relationships = item.get("relationship_changes")
        if entity and isinstance(relationships, dict):
            # A relationship change is a real fact in the same slot as an observed
            # `relationship_changed` event (`relationship:<other>`), so mapping it here is
            # what lets a normal chapter's relationship updates reconcile instead of
            # disappearing into "no deterministic mapping".
            for other, relation in relationships.items():
                if isinstance(relation, dict):
                    value = (relation.get("relation") or relation.get("relationship")
                             or relation.get("status") or relation.get("emotion_phase"))
                else:
                    value = relation
                if other and value:
                    facts.append(_fact(
                        entity=entity, field=f"relationship:{_key(other)}", value=value,
                        source_type="character_state_changes", source_index=index,
                        kind="relationship", text=str(value),
                    ))

    for index, item in enumerate(proposed["item_transfers"]):
        entity = item.get("item_id") or item.get("item_name") or item.get("item")
        holder = (item.get("to_holder") or item.get("to_character") or item.get("to")
                  or item.get("new_holder"))
        if entity and holder:
            facts.append(_fact(entity=entity, field="holder", value=holder,
                               source_type="item_transfers", source_index=index,
                               kind="ownership", old=item.get("from_holder") or item.get("from_character"),
                               text=str(item.get("event") or item.get("detail") or item.get("item_name") or "")))
        elif entity and item.get("new_status"):
            facts.append(_fact(entity=entity, field="status", value=item.get("new_status"),
                               source_type="item_transfers", source_index=index,
                               text=str(item.get("event") or item.get("detail") or "")))

    for category in ("location_state_changes", "faction_state_changes"):
        for index, item in enumerate(proposed[category]):
            entity = (item.get("location_id") or item.get("location_name")
                      or item.get("faction_id") or item.get("faction_name"))
            value = item.get("new_status") or item.get("new_state")
            if entity and value:
                field = "location.state" if category == "location_state_changes" else "faction.state"
                facts.append(_fact(entity=entity, field=field, value=value,
                                   source_type=category, source_index=index,
                                   text=str(item.get("event") or item.get("detail") or "")))
            elif entity:
                text = item.get("event") or item.get("detail")
                if text:
                    facts.append(_fact(entity=entity, field="__state_text__", value=text,
                                       source_type=category, source_index=index,
                                       kind="text", text=str(text)))

    for index, item in enumerate(proposed["foreshadowing_actions"]):
        target = item.get("foreshadow_id") or item.get("target") or item.get("name")
        action = str(item.get("action") or "").strip().lower()
        if target and action:
            # `content`/`detail` is the beat the Writer actually declared. Falling back to
            # the id made a declaration pair on "FS-001" instead of on its text, so a real
            # observation of the same beat could never match.
            declared_text = next(
                (
                    str(value).strip()
                    for value in (
                        item.get("content"), item.get("detail"),
                        item.get("description"), item.get("summary"),
                    )
                    if value and str(value).strip()
                ),
                str(target),
            )
            facts.append(_fact(entity=target, field="foreshadow", value=action,
                               source_type="foreshadowing_actions", source_index=index,
                               kind="foreshadow", text=declared_text))

    for index, item in enumerate(proposed["new_plot_points"]):
        text = item.get("context") or item.get("description") or ""
        if text:
            facts.append(_fact(entity="__plot__", field="__plot_text__", value=text,
                               source_type="new_plot_points", source_index=index,
                               kind="text", text=str(text)))

    for index, item in enumerate(proposed["unresolved_questions"]):
        text = item.get("question") or item.get("content") or ""
        if text:
            facts.append(_fact(entity="__question__", field="__question_text__", value=text,
                               source_type="unresolved_questions", source_index=index,
                               kind="text", text=str(text)))

    time_value = proposed.get("time_progression")
    if isinstance(time_value, dict):
        text = " ".join(str(time_value.get(key) or "") for key in
                        ("time_period", "elapsed_time", "key_time_event")).strip()
        if text:
            facts.append(_fact(entity="__chapter_time__", field="time", value=text,
                               source_type="time_progression", source_index=0,
                               kind="time", text=text))
    return facts


# --------------------------------------------------------------------------- #
# Observed facts
# --------------------------------------------------------------------------- #


def _event_fact(event: dict[str, Any], index: int) -> list[dict[str, Any]]:
    event_type = _key(event.get("event_type") or event.get("type")).replace(" ", "_")
    payload = event.get("payload") if isinstance(event.get("payload"), dict) else event
    subject = event.get("subject") or event.get("entity_id") or event.get("entity")
    facts: list[dict[str, Any]] = []
    if event_type in {"character_state_changed", "state_changed"} and subject:
        field = payload.get("field") or payload.get("field_name")
        value = payload.get("new") if "new" in payload else payload.get("new_value")
        if field and value is not None:
            facts.append(_fact(entity=subject, field=str(field), value=value,
                               source_type="accepted_events", source_index=index,
                               old=payload.get("old"), event_type=event_type))
    elif event_type == "power_breakthrough" and subject:
        value = payload.get("realm") or payload.get("new_realm") or payload.get("new")
        if value is not None:
            facts.append(_fact(entity=subject, field="realm", value=value,
                               source_type="accepted_events", source_index=index,
                               event_type=event_type))
    elif event_type == "artifact_obtained" and subject:
        artifact = payload.get("artifact_id") or payload.get("name") or subject
        owner = payload.get("owner") or payload.get("to_holder")
        if artifact and owner:
            facts.append(_fact(entity=artifact, field="holder", value=owner,
                               source_type="accepted_events", source_index=index,
                               kind="ownership", text=str(payload.get("name") or artifact),
                               event_type=event_type))
    elif event_type == "relationship_changed" and subject:
        to_entity = payload.get("to_entity") or payload.get("target")
        relation = payload.get("relationship_type") or payload.get("relation")
        if to_entity and relation:
            facts.append(_fact(entity=subject, field=f"relationship:{_key(to_entity)}",
                               value=relation, source_type="accepted_events",
                               source_index=index, kind="relationship",
                               text=str(payload.get("detail") or relation), event_type=event_type))
    elif event_type in {"open_loop_created", "promise_created", "open_loop_closed", "promise_paid_off"}:
        content = payload.get("content") or payload.get("question") or payload.get("detail")
        unanswered = payload.get("unanswered_question")
        if content:
            action = "payoff" if event_type in {"open_loop_closed", "promise_paid_off"} else "setup"
            # The loop's open question is part of the same observation; an unresolved-
            # question declaration is allowed to pair with it, not only with the summary.
            observation_text = " ".join(
                str(part) for part in (content, unanswered) if part
            )
            facts.append(_fact(entity=subject or "__open_loop__", field="open_loop",
                               value=content, source_type="accepted_events", source_index=index,
                               kind="open_loop", text=observation_text, event_type=action))
    return facts


def _entity_realm_fact(delta: dict[str, Any], index: int) -> dict[str, Any] | None:
    entity = delta.get("entity_id") or delta.get("entity")
    patch = delta.get("patch") if isinstance(delta.get("patch"), dict) else {}
    current = delta.get("current") if isinstance(delta.get("current"), dict) else {}
    nested_patch = patch.get("current") if isinstance(patch.get("current"), dict) else {}
    value = patch.get("realm", patch.get("current.realm", nested_patch.get("realm", current.get("realm"))))
    if entity and value is not None:
        return _fact(entity=entity, field="realm", value=value,
                     source_type="entity_deltas", source_index=index)
    return None


def _observed_facts(observed: dict[str, Any]) -> list[dict[str, Any]]:
    facts: list[dict[str, Any]] = []
    for index, item in enumerate(observed["state_deltas"]):
        entity, field = item.get("entity_id"), item.get("field")
        value = item.get("new")
        if entity and field and value is not None:
            facts.append(_fact(entity=entity, field=str(field), value=value,
                               source_type="state_deltas", source_index=index,
                               old=item.get("old")))
    for index, item in enumerate(observed["entity_deltas"]):
        fact = _entity_realm_fact(item, index)
        if fact:
            facts.append(fact)
    for index, event in enumerate(observed["accepted_events"]):
        facts.extend(_event_fact(event, index))
    return facts


# --------------------------------------------------------------------------- #
# Matching
# --------------------------------------------------------------------------- #


def _pair_text(declaration: dict[str, Any], facts: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Best observed text fact for a free-text declaration, or None when nothing is close."""
    entity = declaration["entity"]
    # A chapter's time statement can only pair with an observed time fact, and a plot point
    # or open question can pair with the structured state/loop facts that describe it. The
    # remaining declarations are scoped to their own entity so one character's state is
    # never explained by another's.
    candidates = [fact for fact in facts if fact["kind"] in {"text", "open_loop", "foreshadow", "state", "time", "relationship"}]
    if entity == "__chapter_time__":
        candidates = [fact for fact in candidates if fact["kind"] == "time"]
    elif entity not in {"__plot__", "__question__"}:
        scoped = [fact for fact in candidates if fact["entity"] == entity]
        if scoped:
            candidates = scoped
    if not candidates:
        return None
    scored = []
    for fact in candidates:
        if not texts_share_fact(declaration["text"], fact["text"]):
            continue
        containment = _pairing_containment(declaration["text"], fact["text"])
        lcs = _longest_common_substring(declaration["text"], fact["text"])
        ratio = _pairing_ratio(declaration["text"], fact["text"])
        overlap = _pairing_bigram_overlap(declaration["text"], fact["text"])
        scored.append(((containment, lcs, ratio, overlap), fact))
    if not scored:
        return None
    scored.sort(key=lambda item: item[0], reverse=True)
    return scored[0][1]


def _resolve_ownership_key(
    key: tuple[str, str], declarations: list[dict[str, Any]],
    observed_by_key: dict[tuple[str, str], list[dict[str, Any]]],
) -> tuple[str, str]:
    """Resolve an item name that the Writer and the extractor described differently.

    Only ownership facts take this path: item names vary by modifier and head noun
    ("密封胶残片" / "透明胶残片"), while character names and realm names are stable
    identities that must match exactly. A near match must also be unique — two plausible
    observed items means the alias is not provable, so the declaration stays unmatched.
    """
    if key in observed_by_key or not all(item["kind"] == "ownership" for item in declarations):
        return key
    entity, field = key
    scored = []
    for observed_key in observed_by_key:
        if observed_key[1] != field:
            continue
        score = max(_text_ratio(entity, observed_key[0]), _bigram_overlap(entity, observed_key[0]))
        scored.append((score, observed_key))
    scored.sort(key=lambda item: item[0], reverse=True)
    if not scored or scored[0][0] < ENTITY_MATCH_MIN_SCORE:
        return key
    if len(scored) > 1 and scored[1][0] >= scored[0][0] - 0.10:
        return key
    return scored[0][1]


def _equivalent_any(value: str, candidates: list[str]) -> list[str]:
    return [candidate for candidate in candidates if values_equivalent(value, candidate)]


def reconcile_changes(proposed_changes: Any, observed_changes: Any, *, chapter_text: str) -> dict[str, Any]:
    """Return derived audit data. A conflict anywhere blocks the whole payload."""
    proposed = validate_proposed_changes(proposed_changes)
    observed = ExtractionResult.model_validate(observed_changes).model_dump()
    declarations = _proposal_facts(proposed)
    facts = _observed_facts(observed)
    normalized_proposal_sources = {(item["source_type"], item["source_index"]) for item in declarations}

    # Internal consistency: the same canonical (entity, field) must not carry two values
    # that are provably different. Paraphrases of one value do not count. Text-like facts
    # (open loops, promises, foreshadowing, state descriptions) are plural by nature: one
    # character can owe three promises without any of them contradicting the others.
    _TEXT_LIKE_KINDS = {"text", "open_loop", "foreshadow"}
    observed_by_key: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    proposals_by_key: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for fact in facts:
        if fact["kind"] not in _TEXT_LIKE_KINDS:
            observed_by_key[(fact["entity"], fact["field"])].append(fact)
    for fact in declarations:
        if fact["kind"] not in _TEXT_LIKE_KINDS:
            proposals_by_key[(fact["entity"], fact["field"])].append(fact)

    conflicts: list[dict[str, Any]] = []

    def _internal_conflict(key, evidence, label):
        values = []
        for item in evidence:
            # Two representations of one fact (a summary in `state_deltas` and the detailed
            # event text) are not a contradiction just because they are worded differently.
            # Only a *provable* conflict counts.
            if not any(
                values_equivalent(item["raw_value"], seen)
                or not values_conflict(item["raw_value"], seen, kind=item["kind"])
                for seen in values
            ):
                values.append(item["raw_value"])
        if len(values) > 1:
            conflicts.append({"type": f"{label}_internal_conflict", "entity": key[0],
                              "field": key[1], "values": values, "evidence": evidence})

    for key, evidence in sorted(observed_by_key.items(), key=lambda x: x[0]):
        _internal_conflict(key, evidence, "observed")
    for key, evidence in sorted(proposals_by_key.items(), key=lambda x: x[0]):
        _internal_conflict(key, evidence, "proposal")

    matched, proposed_not_observed, unproposed_observed = [], [], []
    matched_observed_sources: set[tuple[str, int]] = set()

    for key, declarations_for_key in sorted(proposals_by_key.items(), key=lambda x: x[0]):
        resolved_key = _resolve_ownership_key(key, declarations_for_key, observed_by_key)
        evidence = observed_by_key.get(resolved_key, [])
        if not evidence:
            for item in declarations_for_key:
                proposed_not_observed.append({"proposed": {"source": item["source_type"], "index": item["source_index"]},
                                              "reason": "no matching observed entity/field"})
            continue
        entity_alias = (
            {"proposed_entity": key[0], "observed_entity": resolved_key[0]}
            if resolved_key != key else None
        )
        observed_values = [item["value"] for item in evidence]
        for item in declarations_for_key:
            equivalent = _equivalent_any(item["value"], observed_values)
            if equivalent:
                hits = [fact for fact in evidence if fact["value"] in equivalent]
                entry = {"proposed": {"source": item["source_type"], "index": item["source_index"]},
                         "observed": [{"source": fact["source_type"], "index": fact["source_index"]}
                                      for fact in hits],
                         "reason": "normalized entity and field match with paraphrase-equivalent value"}
                if entity_alias:
                    entry["entity_alias"] = entity_alias
                matched.append(entry)
                matched_observed_sources.update((fact["source_type"], fact["source_index"]) for fact in hits)
        proposal_values = [item["value"] for item in declarations_for_key]
        unmatched = [
            (item["value"], item["kind"])
            for item in declarations_for_key
            if not _equivalent_any(item["value"], observed_values)
        ]
        if unmatched:
            # Only a *provable* divergence is a conflict. "Same slot, different wording" is
            # already handled by `values_equivalent`; a state description that merely reads
            # differently must not become a hard conflict.
            hard = any(
                values_conflict(value, observed, kind=kind)
                for value, kind in unmatched
                for observed in observed_values
            )
            if hard:
                conflicts.append({"type": "proposal_observed_conflict", "entity": key[0], "field": key[1],
                                  "proposed_values": sorted(set(proposal_values)),
                                  "observed_values": sorted(set(observed_values)),
                                  "evidence": evidence})

    # Free-text declarations (plot points, questions, state descriptions, time) pair by
    # meaning. They cannot establish a structured field conflict on their own.
    for item in declarations:
        if item["kind"] == "text":
            hit = _pair_text(item, facts)
            if hit is None:
                proposed_not_observed.append({"proposed": {"source": item["source_type"], "index": item["source_index"]},
                                              "reason": "no observation is paraphrase-equivalent"})
            else:
                matched.append({"proposed": {"source": item["source_type"], "index": item["source_index"]},
                                "observed": [{"source": hit["source_type"], "index": hit["source_index"]}],
                                "reason": "paraphrase-equivalent observation"})
                matched_observed_sources.add((hit["source_type"], hit["source_index"]))

    # Foreshadow actions pair on the detail text, but the action direction must agree.
    for item in declarations:
        if item["kind"] != "foreshadow":
            continue
        hit = _pair_text(item, facts)
        if hit is None:
            proposed_not_observed.append({"proposed": {"source": item["source_type"], "index": item["source_index"]},
                                          "reason": "no matching open-loop observation"})
            continue
        observed_action = str(hit.get("event_type") or "")
        if observed_action and observed_action != item["value"]:
            conflicts.append({"type": "proposal_observed_conflict", "entity": item["entity"],
                              "field": "foreshadow",
                              "proposed_values": [item["value"]],
                              "observed_values": [observed_action],
                              "evidence": [hit]})
        else:
            matched.append({"proposed": {"source": item["source_type"], "index": item["source_index"]},
                            "observed": [{"source": hit["source_type"], "index": hit["source_index"]}],
                            "reason": "paraphrase-equivalent foreshadow action"})
            matched_observed_sources.add((hit["source_type"], hit["source_index"]))

    for field in REQUIRED_CHANGE_FIELDS:
        value = proposed[field]
        items = value if isinstance(value, list) else ([value] if isinstance(value, dict) else [])
        for index, _ in enumerate(items):
            if field == "character_state_changes" and (field, index) not in normalized_proposal_sources:
                proposed_not_observed.append({"proposed": {"source": field, "index": index},
                                              "reason": "no deterministic proposal fact mapping"})
            elif field in {"new_plot_points", "unresolved_questions", "time_progression",
                           "foreshadowing_actions", "item_transfers",
                           "location_state_changes", "faction_state_changes"}:
                # These are mapped above; only report when the category produced no fact.
                if (field, index) not in normalized_proposal_sources:
                    proposed_not_observed.append({"proposed": {"source": field, "index": index},
                                                  "reason": "no deterministic observed mapping"})

    for source, index in sorted((fact["source_type"], fact["source_index"]) for fact in facts):
        if (source, index) not in matched_observed_sources:
            unproposed_observed.append({"observed": {"source": source, "index": index},
                                        "reason": "final-prose observation has no deterministic proposal match"})

    status = "conflict" if conflicts else "passed"
    return {
        "schema_version": "story-reconciliation/v1", "status": status,
        "coverage": {"deterministic_mappings": SUPPORTED_MAPPINGS, "opaque_categories": OPAQUE_CATEGORIES},
        "matched": matched, "proposed_not_observed": proposed_not_observed,
        "unproposed_observed": unproposed_observed, "conflicts": conflicts,
        "accepted_payload": {key: observed[key] for key in ("accepted_events", "state_deltas", "entity_deltas")},
        "accepted_sources": [
            {"accepted": {"field": field, "index": index}, "observed": {"source": field, "index": index},
             "prose_sha256": _digest(_changes_document(chapter_text).prose_only)}
            for field in ("accepted_events", "state_deltas", "entity_deltas")
            for index, _ in enumerate(observed[field])
        ],
        "proposed_sha256": _digest(proposed),
        "observed_sha256": _digest(observed), "chapter_sha256": _digest(chapter_text),
        "prose_sha256": _digest(_changes_document(chapter_text).prose_only),
    }


def verify_reconciliation_freshness(result: dict[str, Any], *, chapter_text: str) -> None:
    if result.get("status") != "passed":
        raise ValueError("reconciliation has not passed")
    if result.get("chapter_sha256") != _digest(chapter_text):
        raise ValueError("stale reconciliation: final chapter changed after reconciliation")


def verify_observed_payload(result: dict[str, Any], observed_changes: Any) -> dict[str, list[dict[str, Any]]]:
    """Compatibility validator for audit readers; never grants commit authority."""
    if not isinstance(result, dict) or result.get("schema_version") != "story-reconciliation/v1":
        raise ValueError("missing or invalid reconciliation_result")
    if result.get("status") != "passed" or result.get("conflicts"):
        raise ValueError("reconciliation did not pass; chapter commit is blocked")
    observed = ExtractionResult.model_validate(observed_changes).model_dump()
    if result.get("observed_sha256") != _digest(observed):
        raise ValueError("stale reconciliation: extraction_result changed after reconciliation")
    accepted = result.get("accepted_payload")
    fields = ("accepted_events", "state_deltas", "entity_deltas")
    if not isinstance(accepted, dict) or any(accepted.get(field) != observed[field] for field in fields):
        raise ValueError("reconciliation accepted payload does not match observed extraction")
    return {field: observed[field] for field in fields}
