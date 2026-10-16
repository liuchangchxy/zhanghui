#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Semantic Judge request-anchored binding (independent-acceptance follow-up, issue 2).

`judge-bind` used to *stamp* the current prose's hashes onto whatever raw answer it was given,
so an answer produced for prose A could be declared the verdict for prose B — the answer's own
hashes were ignored. These tests pin the corrected contract:

* a verdict is associated with the original `judge-request`;
* a raw answer whose declared hashes/`request_id` disagree with that request is refused;
* an old raw verdict cannot be re-bound to different prose;
* a verdict bound to a different request cannot be replayed.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[2] / ".claude" / "plugins" / "zhanghui" / "scripts"
for path in (SCRIPTS, SCRIPTS.parent):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))


BEFORE = "他把记录本合上，一共七行。"
AFTER = "他合上记录本，一共七行。"
OTHER_AFTER = "他合上记录本，一共八行。"


def _request(before: str = BEFORE, after: str = AFTER, chapter: int = 2) -> dict:
    from data_modules.prose_judge_host import build_judge_request

    return build_judge_request(before, after, chapter=chapter)


def _answer(request: dict, outcome: str = "STYLE_ONLY_SAFE", **overrides) -> dict:
    payload = {
        "outcome": outcome,
        "changes": [],
        "request_id": request["request_id"],
        "before_sha256": request["before_sha256"],
        "after_sha256": request["after_sha256"],
    }
    payload.update(overrides)
    return payload


# --------------------------------------------------------------------------- #
# happy path
# --------------------------------------------------------------------------- #


def test_bound_answer_is_accepted_and_carries_the_request_id():
    from data_modules.prose_judge_host import bind_judge_response

    request = _request()
    verdict = bind_judge_response(_answer(request), BEFORE, AFTER, chapter=2, request=request)

    assert verdict["outcome"] == "STYLE_ONLY_SAFE"
    assert verdict["request_id"] == request["request_id"]
    assert verdict["association"] == "request"
    assert verdict["before_sha256"] == request["before_sha256"]


def test_answer_declaring_only_the_request_id_is_enough():
    from data_modules.prose_judge_host import bind_judge_response

    request = _request()
    answer = {"outcome": "STYLE_ONLY_SAFE", "changes": [], "request_id": request["request_id"]}
    verdict = bind_judge_response(answer, BEFORE, AFTER, chapter=2, request=request)
    assert verdict["association"] == "request"


# --------------------------------------------------------------------------- #
# negative: an old answer must not be re-bound to other prose
# --------------------------------------------------------------------------- #


def test_old_answer_cannot_be_rebound_to_different_prose():
    """issue 2 的核心负向用例：为 A 产出的裁决不得被绑定到 B。"""
    from data_modules.prose_judge_host import JudgeBindingError, bind_judge_response

    old_request = _request(BEFORE, AFTER)
    old_answer = _answer(old_request)  # produced for BEFORE -> AFTER

    # try to bind it to a *different* after text, using the old request as evidence
    with pytest.raises(JudgeBindingError) as excinfo:
        bind_judge_response(old_answer, BEFORE, OTHER_AFTER, chapter=2, request=old_request)
    assert "different" in str(excinfo.value)

    # ... and without a request, the answer's own declared hash still blocks it
    with pytest.raises(JudgeBindingError):
        bind_judge_response(old_answer, BEFORE, OTHER_AFTER, chapter=2)


def test_answer_from_a_different_request_is_refused():
    from data_modules.prose_judge_host import JudgeBindingError, bind_judge_response

    # same prose pair, different chapter → same hashes but a different request id
    request_a = _request(BEFORE, AFTER, chapter=2)
    request_b = _request(BEFORE, AFTER, chapter=3)
    assert request_a["request_id"] != request_b["request_id"]
    assert request_a["before_sha256"] == request_b["before_sha256"]

    with pytest.raises(JudgeBindingError) as excinfo:
        bind_judge_response(_answer(request_a), BEFORE, AFTER, chapter=2, request=request_b)
    assert "different judge request" in str(excinfo.value)


def test_declared_hash_that_disagrees_with_the_request_is_refused():
    from data_modules.prose_judge_host import JudgeBindingError, bind_judge_response

    request = _request()
    tampered = _answer(request, after_sha256="f" * 64)
    with pytest.raises(JudgeBindingError) as excinfo:
        bind_judge_response(tampered, BEFORE, AFTER, chapter=2, request=request)
    assert "after text" in str(excinfo.value)


def test_request_forged_for_other_prose_is_refused():
    from data_modules.prose_judge_host import JudgeBindingError, bind_judge_response

    request = _request(BEFORE, OTHER_AFTER)          # request describes a different edit
    answer = _answer(request)
    with pytest.raises(JudgeBindingError) as excinfo:
        bind_judge_response(answer, BEFORE, AFTER, chapter=2, request=request)
    assert "does not describe this prose" in str(excinfo.value)


def test_answer_with_no_binding_at_all_is_refused_when_a_request_is_supplied():
    """不能因为「回答里没写哈希」就顺手用当前正文的哈希补上。"""
    from data_modules.prose_judge_host import JudgeBindingError, bind_judge_response

    request = _request()
    with pytest.raises(JudgeBindingError) as excinfo:
        bind_judge_response({"outcome": "STYLE_ONLY_SAFE", "changes": []}, BEFORE, AFTER, request=request)
    assert "declares no binding" in str(excinfo.value)


def test_not_a_request_payload_is_refused():
    from data_modules.prose_judge_host import JudgeBindingError, bind_judge_response

    with pytest.raises(JudgeBindingError):
        bind_judge_response({"outcome": "STYLE_ONLY_SAFE"}, BEFORE, AFTER, request={"kind": "verdict"})


# --------------------------------------------------------------------------- #
# negative: a stale *verdict* cannot be replayed
# --------------------------------------------------------------------------- #


def test_stale_verdict_request_id_does_not_match_other_prose():
    from data_modules.prose_judge_host import JudgeBindingError, validate_binding

    request = _request(BEFORE, AFTER)
    verdict = {
        "kind": "verdict",
        "outcome": "STYLE_ONLY_SAFE",
        "changes": [],
        "before_sha256": request["before_sha256"],
        "after_sha256": request["after_sha256"],
        "request_id": request["request_id"],
    }
    validate_binding(verdict, BEFORE, AFTER, chapter=2)  # matches → fine

    with pytest.raises(JudgeBindingError):
        validate_binding(verdict, BEFORE, OTHER_AFTER, chapter=2)


def test_verdict_is_still_fail_closed_through_the_diff_layer():
    from data_modules.prose_judge_host import make_bound_judge_callable
    from data_modules.prose_semantic_diff import compare_semantic_facts

    request = _request(BEFORE, AFTER)
    from data_modules.prose_judge_host import bind_judge_response

    verdict = bind_judge_response(_answer(request), BEFORE, AFTER, chapter=2, request=request)
    judge = make_bound_judge_callable(verdict, BEFORE, AFTER, chapter=2)
    assert compare_semantic_facts(BEFORE, AFTER, semantic_judge=judge).outcome.value == "STYLE_ONLY_SAFE"

    stale_judge = make_bound_judge_callable(verdict, BEFORE, OTHER_AFTER, chapter=2)
    result = compare_semantic_facts(BEFORE, OTHER_AFTER, semantic_judge=stale_judge)
    assert result.outcome.value == "UNCERTAIN"
    assert result.safe is False


def test_judge_cli_bind_requires_agreement_with_the_request(tmp_path: Path):
    """CLI 层：judge-bind --request-file 必须校验关联，而不是重新绑定。"""
    import os
    import subprocess

    request = _request()
    request_file = tmp_path / "request.json"
    request_file.write_text(json.dumps(request, ensure_ascii=False), encoding="utf-8")

    before_file = tmp_path / "before.md"
    after_file = tmp_path / "after.md"
    before_file.write_text(BEFORE, encoding="utf-8")
    after_file.write_text(AFTER, encoding="utf-8")

    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join([str(SCRIPTS), str(SCRIPTS.parent), env.get("PYTHONPATH", "")])

    def run(*argv: str):
        return subprocess.run(
            [sys.executable, "-X", "utf8", str(SCRIPTS / "webnovel.py"), *argv],
            capture_output=True, text=True, encoding="utf-8", env=env,
        )

    # a raw answer that declares no binding cannot be associated with the request
    raw = tmp_path / "raw.json"
    raw.write_text(json.dumps({"outcome": "STYLE_ONLY_SAFE", "changes": []}), encoding="utf-8")
    refused = run(
        "prose", "judge-bind",
        "--before-file", str(before_file), "--after-file", str(after_file),
        "--response-file", str(raw), "--request-file", str(request_file),
    )
    assert refused.returncode == 1
    assert "declares no binding" in refused.stderr

    # the matching answer binds
    good = tmp_path / "good.json"
    good.write_text(json.dumps(_answer(request)), encoding="utf-8")
    ok = run(
        "prose", "judge-bind",
        "--before-file", str(before_file), "--after-file", str(after_file),
        "--response-file", str(good), "--request-file", str(request_file),
    )
    assert ok.returncode == 0, ok.stderr
    verdict = json.loads(ok.stdout)
    assert verdict["request_id"] == request["request_id"]
    assert verdict["association"] == "request"

    # the same answer cannot be bound to different prose
    other_after = tmp_path / "other_after.md"
    other_after.write_text(OTHER_AFTER, encoding="utf-8")
    rebound = run(
        "prose", "judge-bind",
        "--before-file", str(before_file), "--after-file", str(other_after),
        "--response-file", str(good), "--request-file", str(request_file),
    )
    assert rebound.returncode == 1
    assert "does not describe this prose" in rebound.stderr
