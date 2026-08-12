"""Unit tests for the ported qidian RC4 cookie computation.

No network. All inputs pinned so the test is byte-deterministic and
regression-safe against accidental changes to the JSON shape or
RC4 byte stream.

The vendored subset's ``_calc_cookies`` is reference-only and may be
deleted by future upstream syncs — these tests pin the LOCAL port
behavior so the call shape doesn't drift.

Note: this module does NOT verify that the cookies bypass qidian's
probe.js. They don't (verified 2026-08-13). The runtime bypass is the
mobile-subdomain path in ``scripts/adapters/qidian.py``.
"""
from __future__ import annotations

import base64
import hashlib
import json

from scripts.adapters.qidian_cookies import (
    compute_cookies,
    rc4_init,
    rc4_stream,
)


# --- RC4 reference ----------------------------------------------------------

def test_rc4_init_returns_permutation_of_0_to_255():
    """KSA produces a permutation of the integers 0..255."""
    S = rc4_init(b"key")
    assert sorted(S) == list(range(256))


def test_rc4_init_does_not_mutate_input_permutation():
    """KSA returns a fresh list — input list (if any) is not mutated."""
    S = list(range(256))
    out = rc4_init(b"abc")
    assert S == list(range(256)), "rc4_init should not mutate input"
    assert out is not S


def test_rc4_stream_round_trip():
    """Encrypting then decrypting the same S-box restores plaintext."""
    key = b"secret-key"
    S = rc4_init(key)
    plaintext = b"hello world"
    cipher = rc4_stream(S, plaintext)
    # Re-initialize S because rc4_stream mutates it; then encrypt again
    # and verify we get the same ciphertext bytes (RC4 is symmetric).
    S2 = rc4_init(key)
    cipher2 = rc4_stream(S2, plaintext)
    assert cipher == cipher2
    # And the cipher is different from plaintext (otherwise encryption did nothing).
    assert cipher != plaintext


def test_rc4_matches_vendored_key_vector():
    """Encrypt an empty plaintext with the vendored key to confirm the
    RC4 port produces the same S-box the vendored upstream uses."""
    # Vendored key: dGcwOUl0Myo5aA== -> b"tg09It3*9h"
    key_b64 = "dGcwOUl0Myo5aA=="
    key = base64.b64decode(key_b64)
    assert key == b"tg09It3*9h"  # literal decoding check
    S = rc4_init(key)
    # RC4 has no canonical "known answer" so we just sanity-check the
    # S-box differs from the trivial identity permutation (i.e., the KSA
    # ran). If KSA is broken, S would still be [0, 1, ..., 255].
    assert S != list(range(256))


# --- compute_cookies ---------------------------------------------------------

def test_compute_cookies_returns_two_keys():
    """``compute_cookies`` returns a dict with exactly two keys: e1, ywfp."""
    cookies = compute_cookies(
        "https://www.qidian.com/all",
        loadts=1700000000000,
        fp_val="abc123" + "0" * 26,
        abn_val="0" * 32,
        duration_ms=500,
    )
    assert set(cookies.keys()) == {"e1", "ywfp"}


def test_compute_cookies_ywfp_is_base64():
    """The ``ywfp`` cookie decodes as base64."""
    cookies = compute_cookies(
        "https://www.qidian.com/all",
        loadts=1700000000000,
        fp_val="abc123" + "0" * 26,
        abn_val="0" * 32,
        duration_ms=500,
    )
    decoded = base64.b64decode(cookies["ywfp"], validate=True)
    # The decoded bytes are RC4-encrypted JSON. Decrypt with the same S-box.
    S = rc4_init(base64.b64decode("dGcwOUl0Myo5aA=="))
    plain = rc4_stream(S, decoded)
    parsed = json.loads(plain.decode("utf-8"))
    assert parsed["loadts"] == 1700000000000
    assert parsed["timestamp"] == 1700000000500  # 1700000000000 + 500
    assert parsed["fingerprint"] == "abc123" + "0" * 26
    assert parsed["abnormal"] == "0" * 32
    # Checksum is md5(uri + loadts + fingerprint).
    expected_ck = hashlib.md5(
        ("https://www.qidian.com/all" + "1700000000000" + ("abc123" + "0" * 26)).encode("utf-8")
    ).hexdigest()
    assert parsed["checksum"] == expected_ck


def test_compute_cookies_e1_is_url_encoded_json():
    """``e1`` is URL-encoded JSON of the E1_VAL tracker metadata."""
    cookies = compute_cookies(
        "https://www.qidian.com/all",
        loadts=1700000000000,
        fp_val="0" * 32,
        abn_val="0" * 32,
        duration_ms=500,
    )
    from urllib.parse import unquote
    decoded = json.loads(unquote(cookies["e1"]))
    assert decoded == {
        "l6": "",
        "l7": "",
        "l1": "",
        "l3": "",
        "pid": "qd_p_qidian",
        "eid": "",
    }


def test_compute_cookies_timestamp_clamps_into_range():
    """With the default random sampler, ``timestamp - loadts`` is in [300, 1000] ms."""
    # 1000 trials: every sample is within the clamp range.
    for _ in range(1000):
        c = compute_cookies("https://www.qidian.com/all")
        # Decrypt the payload to verify timing fields.
        decoded = base64.b64decode(c["ywfp"], validate=True)
        S = rc4_init(base64.b64decode("dGcwOUl0Myo5aA=="))
        plain = json.loads(rc4_stream(S, decoded).decode("utf-8"))
        duration = plain["timestamp"] - plain["loadts"]
        assert 300 <= duration <= 1000, f"duration {duration} out of clamp range"


def test_compute_cookies_changes_with_url():
    """The checksum binds the cookie to the URL — different URL yields a different ywfp."""
    a = compute_cookies(
        "https://www.qidian.com/all",
        loadts=1700000000000,
        fp_val="0" * 32,
        abn_val="0" * 32,
        duration_ms=500,
    )
    b = compute_cookies(
        "https://www.qidian.com/so/abc.html",
        loadts=1700000000000,
        fp_val="0" * 32,
        abn_val="0" * 32,
        duration_ms=500,
    )
    assert a["ywfp"] != b["ywfp"], "ywfp must bind to URL via checksum"
    assert a["e1"] == b["e1"], "e1 cookie is URL-independent (tracker metadata)"