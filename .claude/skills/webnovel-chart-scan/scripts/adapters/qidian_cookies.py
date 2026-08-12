"""起点 (qidian) RC4 cookie construction — ported from vendored subset.

Status: REFERENCE ONLY (verified 2026-08-13).

    The vendored upstream ``vendor/novel-downloader/qidian_subset/searcher.py``
    contains an RC4 cookie computation (``_calc_cookies``) intended to bypass
    qidian.com's probe.js anti-bot challenge. We ported it verbatim into this
    module for traceability, but verification on 2026-08-13 shows that the
    computed cookies do NOT actually bypass modern probe.js — every qidian.com
    URL (with or without these cookies) still returns HTTP 202 + the
    ``/C2WF946J0/probe.js`` script.

    The runtime bypass that DOES work is using the mobile subdomain
    (``m.qidian.com``) with an iPhone User-Agent — see
    ``scripts/adapters/qidian.py``. This module is kept as a faithful port so:

      1. The vendored subset's contract (RC4 + base64 payload format) is
         preserved for future re-use if qidian ever changes anti-bot.
      2. Unit tests can exercise the RC4 helper without network calls.
      3. Reviewers can audit the port vs the vendored source line-by-line.

Vendored reference: vendor/novel-downloader/qidian_subset/searcher.py
    ``QidianSearcher._calc_cookies`` — see git history for the original.

RC4 algorithm:
    Standard RC4 (PRGA) initialized from the key ``dGcwOUl0Myo5aA==``
    (base64-decoded — equals ``tg09It3#9h`` in plain bytes). The encrypted
    cookie payload is a JSON dict of {loadts, timestamp, fingerprint, abnormal,
    checksum}; base64-encoded before being attached as the ``ywfp`` cookie.

Field semantics:
    - loadts:        int(time.time() * 1000) — ms-since-epoch of the request.
    - timestamp:     loadts + duration; duration ~ N(600ms, 150ms) clamped to
                     [300ms, 1000ms]. This pretends to be a "page load
                     duration" before the cookie is computed.
    - fingerprint:   md5(random()) — a fake browser fingerprint.
    - abnormal:      "0" * 32 — zero string (no anti-bot signal).
    - checksum:      md5(uri + loadts + fingerprint) — request-binding hash
                     so the cookie can't be reused for a different URL.

Companion cookie ``e1``:
    A JSON dict ``{"l6": "", "l7": "", "l1": "", "l3": "", "pid": "qd_p_qidian", "eid": ""}``
    passed as a URL-encoded string. ``pid`` is a tracker ID; ``eid`` is empty
    in the vendored subset.
"""
from __future__ import annotations

import base64
import hashlib
import json
import random
import time
from typing import Any


# RC4 stream cipher — pure-Python reference implementation matching the
# vendored subset's ``novel_downloader.libs.crypto.rc4``. We don't import
# from the vendored subset to avoid the heavy transitive dependency on
# novel-downloader's package layout (which references modules we don't
# ship).
def rc4_init(key: bytes) -> list[int]:
    """KSA (Key Scheduling Algorithm) — initialize S-box from a key."""
    S = list(range(256))
    j = 0
    for i in range(256):
        j = (j + S[i] + key[i % len(key)]) % 256
        S[i], S[j] = S[j], S[i]
    return S


def rc4_stream(s_init: list[int], data: bytes) -> bytes:
    """PRGA — encrypt/decrypt ``data`` with the S-box from ``rc4_init``."""
    S = s_init.copy()
    out = bytearray()
    i = j = 0
    for byte in data:
        i = (i + 1) % 256
        j = (j + S[i]) % 256
        S[i], S[j] = S[j], S[i]
        K = S[(S[i] + S[j]) % 256]
        out.append(byte ^ K)
    return bytes(out)


# RC4 key — base64-encoded; decoding yields the raw key bytes used for
# the S-box initialization. Identical to vendored subset.
_RC4_KEY_B64 = "dGcwOUl0Myo5aA=="
_RC4_KEY_BYTES = base64.b64decode(_RC4_KEY_B64)
_S_INIT = rc4_init(_RC4_KEY_BYTES)

# Default companion ``e1`` cookie payload — same shape as vendored subset's
# ``_E1_VAL``. Kept as a frozen literal so the JSON ordering is stable for
# tests.
_E1_VAL: dict[str, str] = {
    "l6": "",
    "l7": "",
    "l1": "",
    "l3": "",
    "pid": "qd_p_qidian",
    "eid": "",
}


def _word_count_for_dummy() -> str:
    """Stand-in for a real fingerprint in tests. The real value comes
    from ``_make_fp_val``. We avoid using ``random`` in the dummy so
    the helper is deterministic."""
    return "0" * 32


def _make_fp_val() -> str:
    """Generate a fake browser fingerprint (md5 of a random float)."""
    return hashlib.md5(str(random.random()).encode("utf-8")).hexdigest()


def _make_duration_ms() -> int:
    """Sample the fake page-load duration: N(600, 150) clamped to [300, 1000].

    Mirrors the vendored subset's duration formula:
        ``max(300, min(1000, int(random.normalvariate(600, 150))))``
    """
    return max(300, min(1000, int(random.normalvariate(600, 150))))


def compute_cookies(
    url: str,
    *,
    loadts: int | None = None,
    fp_val: str | None = None,
    abn_val: str | None = None,
    duration_ms: int | None = None,
) -> dict[str, str]:
    """Compute the RC4-signed cookies for a single qidian.com request.

    Returns a dict suitable to pass as the ``cookies`` argument to
    ``httpx.get``. Two keys:

      - ``e1``: URL-encoded JSON of ``_E1_VAL`` (tracker metadata).
      - ``ywfp``: base64-encoded RC4-encrypted JSON of the timing/fingerprint
        payload. Decodes with the same RC4 key + S-box.

    Parameters are exposed so unit tests can pin the timing/fingerprint
    to deterministic values and assert byte-level output. Production
    callers should leave them as ``None`` to get the random sampling
    behavior.
    """
    now_ms = loadts if loadts is not None else int(time.time() * 1000)
    fp = fp_val if fp_val is not None else _make_fp_val()
    abn = abn_val if abn_val is not None else ("0" * 32)
    duration = duration_ms if duration_ms is not None else _make_duration_ms()
    timestamp = now_ms + duration

    comb = f"{url}{now_ms}{fp}"
    ck_val = hashlib.md5(comb.encode("utf-8")).hexdigest()

    payload: dict[str, Any] = {
        "loadts": now_ms,
        "timestamp": timestamp,
        "fingerprint": fp,
        "abnormal": abn,
        "checksum": ck_val,
    }
    plain = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    cipher = rc4_stream(_S_INIT, plain)

    # NOTE: vendored subset uses ``cls._quote(json.dumps(cls._E1_VAL))``
    # which is a URL-quoted JSON string. We replicate that with
    # ``json.dumps`` (without ``ensure_ascii=False`` for ASCII-only keys)
    # + ``urllib.parse.quote`` so the output matches the upstream
    # contract for test fixtures.
    from urllib.parse import quote
    e1_str = quote(json.dumps(_E1_VAL), safe="")

    return {
        "e1": e1_str,
        "ywfp": base64.b64encode(cipher).decode("utf-8"),
    }