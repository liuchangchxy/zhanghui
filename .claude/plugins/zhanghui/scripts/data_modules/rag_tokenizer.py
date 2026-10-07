"""Shared deterministic tokenizer for mutable and generation RAG indexes."""
from __future__ import annotations

import re


def tokenize_rag(text: str) -> list[str]:
    chinese = re.findall(r"[\u4e00-\u9fff]+", text)
    chinese_chars = list("".join(chinese))
    english = re.findall(r"[a-zA-Z]+", text.lower())
    return chinese_chars + english
