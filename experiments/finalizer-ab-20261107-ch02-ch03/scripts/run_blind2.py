#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Blind two-version literary A/B: R = Writer raw, C = Finalizer candidate.

Two judges from different model families, with reversed positions:
  J1 = Antigravity Gemini Flash (neutral project); 甲=R, 乙=C
  J2 = local Anthropic-compatible proxy;           甲=C, 乙=R

The judge never sees which text is raw or candidate, nor the hypothesis.
Only the six agreed dimensions are scored.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
OLD_SCRIPTS = Path("/Users/chang/Desktop/Code/zhanghui/experiments/finalizer-ab-20261107/scripts")
sys.path.insert(0, str(OLD_SCRIPTS))

from llm_channels import parse_json, run_agentapi, run_proxy  # noqa: E402

PROMPT = """你是一位独立、专业、公正的文学评审。下面给你同一部长篇小说同一章的两个版本，分别标为「甲」「乙」。它们是同一情节的两种文字处理，顺序不代表优劣。

请只根据文本本身评价，不要猜测版本来源、生成方式或实验目的，也不要因为某一版更长或更短就偏好或贬低它。

【只看这六个维度】
1. OVERALL_PREFERENCE：作为读者，你更愿意读哪一版。
2. READING_APPEAL：哪一版更抓人、更让人想继续读下去。
3. LOW_AUTHOR_EXPLANATION：哪一版更少由叙述者替读者解释刚发生的动作/对白的意义。
4. SENTENCE_NATURALNESS：哪一版的句子更自然、更少翻译腔或电报体。
5. SCENE_IMMERSION：哪一版更能让读者进入场景（器物、声音、身体动作、空间位置）。
6. SUBTEXT：哪一版更让潜台词留在动作和对白里，而不是被点破。

【判定要求】
- 每个维度给 winner（"甲" / "乙" / "TIE"）、confidence（0 到 1 的小数）、evidence（必须引用具体原句或具体处理，不能只写“更好”“更自然”）。
- 不要因为两版高度相似就默认 TIE；只有确实分不出高下时才判 TIE。
- 同一维度两版各有得失时可以判 TIE，但要在 evidence 里说清各自的得失。
- 如果某一版有明显硬伤（事实/人物/逻辑/结构上的问题），请在该维度的 evidence 里直接指出原句。

【输出】
严格返回纯 JSON，不要任何多余文字：
{
  "chapter": "第__CHAPTER__章",
  "dimensions": {
    "OVERALL_PREFERENCE": {"winner": "甲|乙|TIE", "confidence": 0.0, "evidence": "..."},
    "READING_APPEAL": {"winner": "甲|乙|TIE", "confidence": 0.0, "evidence": "..."},
    "LOW_AUTHOR_EXPLANATION": {"winner": "甲|乙|TIE", "confidence": 0.0, "evidence": "..."},
    "SENTENCE_NATURALNESS": {"winner": "甲|乙|TIE", "confidence": 0.0, "evidence": "..."},
    "SCENE_IMMERSION": {"winner": "甲|乙|TIE", "confidence": 0.0, "evidence": "..."},
    "SUBTEXT": {"winner": "甲|乙|TIE", "confidence": 0.0, "evidence": "..."}
  },
  "rationale": "三到五句话，说明主要判断依据，并指出任何一版的具体硬伤。"
}

==================== 第__CHAPTER__章 版本甲 ====================
__TEXT_JIA__

==================== 第__CHAPTER__章 版本乙 ====================
__TEXT_YI__
"""


def build_prompt(chapter: int, jia: str, yi: str) -> str:
    return (PROMPT.replace("__CHAPTER__", str(chapter))
            .replace("__TEXT_JIA__", jia)
            .replace("__TEXT_YI__", yi))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--chapter", type=int, required=True)
    ap.add_argument("--raw", required=True)
    ap.add_argument("--candidate", required=True)
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()

    raw = Path(args.raw).read_text(encoding="utf-8").strip()
    cand = Path(args.candidate).read_text(encoding="utf-8").strip()
    out_root = Path(args.out_dir)
    out_root.mkdir(parents=True, exist_ok=True)

    # Reversed positions: J1 sees raw first, J2 sees candidate first.
    mappings = {
        "j1_gemini": {"甲": "RAW", "乙": "CANDIDATE"},
        "j2_proxy": {"甲": "CANDIDATE", "乙": "RAW"},
    }
    key_path = out_root / "blind_key.json"
    keys = json.loads(key_path.read_text(encoding="utf-8")) if key_path.exists() else {}
    keys[f"ch{args.chapter:02d}"] = mappings
    key_path.write_text(json.dumps(keys, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    for judge, mapping in mappings.items():
        out_dir = out_root / judge
        out_dir.mkdir(parents=True, exist_ok=True)
        result_path = out_dir / "result.json"
        if result_path.exists() and not args.force:
            print(f"[{judge}] already done; skip")
            continue
        texts = {"RAW": raw, "CANDIDATE": cand}
        prompt = build_prompt(args.chapter, texts[mapping["甲"]], texts[mapping["乙"]])
        (out_dir / "prompt.txt").write_text(prompt, encoding="utf-8")
        print(f"[{judge}] prompt {len(prompt)} chars, mapping {mapping}", flush=True)
        if judge == "j1_gemini":
            response, _ = run_agentapi(prompt, out_dir, f"finalizer-ab-ch{args.chapter:02d}-{judge}",
                                       max_wait=1500)
        else:
            response, _ = run_proxy(prompt, out_dir, f"finalizer-ab-ch{args.chapter:02d}-{judge}",
                                    temperature=0.2, max_tokens=32000)
        (out_dir / "response.txt").write_text(response, encoding="utf-8")
        parsed = parse_json(response)
        (out_dir / "result.json").write_text(
            json.dumps(parsed, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"[{judge}] done", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
