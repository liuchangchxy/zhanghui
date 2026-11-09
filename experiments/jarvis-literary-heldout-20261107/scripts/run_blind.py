#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Blind A/B evaluation of held-out chapters (accepted B only).

Two judges from different model families; each chapter judged twice with the
positions reversed. Neither judge is told which arm is edited, nor the target
dimensions, nor any prior result.
"""
from __future__ import annotations

import hashlib
import json
import random
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from config import CHAPTERS, input_path, output_path  # noqa: E402
from llm_channels import parse_json, run_agentapi, run_proxy  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
BLIND = ROOT / "blind"
DIMENSIONS = [
    "OVERALL_PREFERENCE",
    "READING_APPEAL",
    "LOW_AUTHOR_EXPLANATION",
    "SENTENCE_NATURALNESS",
    "SCENE_IMMERSION",
    "SUBTEXT",
]

PROMPT = """你是一位敏锐、专业、公正的文学与小说正文质量评测仲裁员。
本评测只做一件事：对比同一部长篇小说第 @N@ 章的两个版本（LEFT 与 RIGHT），判断哪个版本更好。

【评测维度】
1. OVERALL_PREFERENCE —— 总体偏好：作为读者，你更愿意读哪一版。
2. READING_APPEAL —— 阅读吸引力：是否抓人，是否想继续往下读。
3. LOW_AUTHOR_EXPLANATION —— 哪一版作者直接解释更少（替读者总结、点题、下结论更少者为佳）。
4. SENTENCE_NATURALNESS —— 句段自然度：句子是否顺，长短是否有变化，段落节奏。
5. SCENE_IMMERSION —— 场景沉浸感：读者是否被放进具体时空里。
6. SUBTEXT —— 潜台词：该藏着的话有没有被直接说破；言外之意是否成立。

【判定要求】
- 每个维度给出 LEFT / RIGHT / TIE 之一，并给 0-1 置信度。
- 不要因为两版高度相似就默认 TIE；能感到差别就判断。
- 不要推测两版来源、不要在意长度差异本身，只评价文本。
- 理由必须引用具体文本现象，不要只给结论。

【输出】严格返回纯 JSON，不要任何多余文字：
{
  "chapter": @N@,
  "dimensions": {
@KEYS@
  },
  "overall_rationale": "两三句话"
}

==================== 小说 LEFT 第 @N@ 章 ====================
@LEFT@

==================== 小说 RIGHT 第 @N@ 章 ====================
@RIGHT@
"""

JSON_KEYS = ",\n".join(
    '    "%s": {"winner": "LEFT|RIGHT|TIE", "confidence": 0.0, "evidence": "一句话"}' % d
    for d in DIMENSIONS
)

CHAPTER_HEAD = re.compile(r"^#{0,4}\s*第\s*[0-9零一二三四五六七八九十百千两]+章[\s:：、·.。\-—]*.{0,14}$")


def split_prose(text: str) -> str:
    prose = re.sub(r"(?m)^\s*[0-9a-f]{64}\s*$", "", text)
    prose = re.sub(r"(?m)^.*封包验证指纹[^\n]*$\n?", "", prose)
    prose = re.sub(r"\n{3,}", "\n\n", prose).strip()
    lines = prose.splitlines()
    while lines:
        head = lines[0].strip()
        if not head or (CHAPTER_HEAD.match(head) and len(head) < 25):
            lines.pop(0)
            continue
        break
    return "\n".join(lines).strip()


def render(n: int, left: str, right: str) -> str:
    return (PROMPT.replace("@KEYS@", JSON_KEYS).replace("@N@", str(n))
            .replace("@LEFT@", left).replace("@RIGHT@", right))


def call_judge(judge: str, prompt: str, out: Path, title: str) -> tuple[str, dict]:
    if judge == "j1":
        return run_proxy(prompt, out, title, model="codex/gpt-6.1-terra",
                         temperature=0.2, max_tokens=8000)
    return run_agentapi(prompt, out, title)


def accepted_chapters() -> list[int]:
    p = ROOT / "outputs/RUN_RECORDS.json"
    rec = json.loads(p.read_text(encoding="utf-8"))
    out = []
    for ch in sorted(CHAPTERS):
        if rec.get(CHAPTERS[ch]["key"], {}).get("status") == "ACCEPTED" and output_path(ch).exists():
            out.append(ch)
    return out


def main() -> None:
    chapters = [int(x) for x in sys.argv[1:]] or accepted_chapters()
    rng = random.Random(20261108)
    key_path = BLIND / "blind_key.json"
    key = json.loads(key_path.read_text(encoding="utf-8")) if key_path.exists() else {}
    records = {}
    for ch in chapters:
        meta = CHAPTERS[ch]
        a = split_prose(input_path(ch).read_text(encoding="utf-8"))
        b = split_prose(output_path(ch).read_text(encoding="utf-8"))
        for judge in ("j1", "j2"):
            ck = f"{meta['key']}_{judge}"
            first_left = key.get(ck, {}).get("pass1_left")
            if first_left not in ("A", "B"):
                first_left = rng.choice(["A", "B"])
                key.setdefault(ck, {})["pass1_left"] = first_left
            key[ck].update({"chapter": ch, "judge": judge, "A": "original", "B": "edited"})
            for p in (1, 2):
                left_arm = first_left if p == 1 else ("B" if first_left == "A" else "A")
                left, right = (a, b) if left_arm == "A" else (b, a)
                prompt = render(ch, left, right)
                out = BLIND / f"{meta['key']}_{judge}_pass{p}"
                raw, call_meta = call_judge(judge, prompt, out, f"heldout-blind-{meta['key']}-{judge}-{p}")
                try:
                    data = parse_json(raw)
                    assert all(d in data.get("dimensions", {}) for d in DIMENSIONS)
                except Exception:
                    # Mechanical retry only: same prompt, same judge, same position.
                    raw, call_meta = call_judge(
                        judge, prompt, out, f"heldout-blind-{meta['key']}-{judge}-{p}-retry")
                    data = parse_json(raw)
                    assert all(d in data.get("dimensions", {}) for d in DIMENSIONS)
                (out / "response.txt").write_text(raw, encoding="utf-8")
                (out / "judgement.json").write_text(
                    json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
                records[f"{meta['key']}_{judge}_pass{p}"] = {
                    "chapter": ch,
                    "judge": judge,
                    "pass": p,
                    "left_arm": left_arm,
                    "prompt_sha256": hashlib.sha256(prompt.encode()).hexdigest(),
                    "raw_sha256": hashlib.sha256(raw.encode()).hexdigest(),
                    "created_at": datetime.now(timezone.utc).isoformat(),
                    "call": call_meta,
                }
                print(meta["key"], judge, f"pass{p}", "left=" + left_arm,
                      data.get("overall_rationale", "")[:80], flush=True)
    key_path.write_text(json.dumps(key, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    rp = BLIND / "RUN_RECORDS.json"
    existing = json.loads(rp.read_text(encoding="utf-8")) if rp.exists() else {}
    existing.update(records)
    rp.write_text(json.dumps(existing, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
