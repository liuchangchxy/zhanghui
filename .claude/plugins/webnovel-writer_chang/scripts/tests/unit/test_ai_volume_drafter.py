import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import pytest

from data_modules.ai_volume_drafter import draft_next_volume
from data_modules.volume_state import VolumeRecord, VolumeStatus, VolumeSource


def test_draft_returns_candidate_from_llm():
    fake_response = "卷名：起势\n核心冲突：宗门考核\n卷末高潮：夺得首席\n"
    cand = draft_next_volume(
        one_line_concept="少年修仙",
        confirmed_volumes=[],
        genre="修仙",
        target_index=1,
        llm_call=lambda prompt: fake_response,
    )
    assert cand.title == "起势"
    assert cand.core_conflict == "宗门考核"
    assert cand.climax == "夺得首席"
    assert cand.source == VolumeSource.AI


def test_draft_prompt_mentions_prior_volumes():
    captured = {}
    def fake_llm(prompt):
        captured["prompt"] = prompt
        return "卷名：V2\n核心冲突：X\n卷末高潮：Y\n"

    prior = [VolumeRecord(
        index=1, title="V1", core_conflict="A", climax="B",
        status=VolumeStatus.CONFIRMED, source=VolumeSource.HUMAN,
    )]
    draft_next_volume(
        one_line_concept="c", confirmed_volumes=prior,
        genre="玄幻", target_index=2, llm_call=fake_llm,
    )
    assert "V1" in captured["prompt"]
    assert "已确认前卷" in captured["prompt"]


def test_draft_raises_on_missing_fields():
    def fake_llm(prompt):
        return "卷名：只有名字"  # 缺核心冲突和卷末高潮

    with pytest.raises(ValueError, match="missing required fields"):
        draft_next_volume(
            one_line_concept="c", confirmed_volumes=[],
            genre="玄幻", target_index=1, llm_call=fake_llm,
        )