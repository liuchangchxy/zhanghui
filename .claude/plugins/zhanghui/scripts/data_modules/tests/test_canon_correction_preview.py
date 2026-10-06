import json
from pathlib import Path

from data_modules.canon_correction_preview import preview_chapter_corrections
from data_modules.canon_correction_schema import base_commit_digest
from data_modules.canon_correction_store import VerifiedCorrectionDecision
from data_modules.story_runtime_sources import load_runtime_sources
from data_modules.tests.test_canon_correction_resolver import edge_fixtures


def write_json(path: Path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, sort_keys=True), encoding="utf-8")


def snapshot(root: Path):
    return {str(path.relative_to(root)): path.read_bytes() for path in root.rglob("*") if path.is_file()}


def test_preview_is_read_only_and_runtime_sources_do_not_change(tmp_path):
    base, correction, request, authorization, verification = edge_fixtures()
    base_path = tmp_path / ".story-system/commits/chapter_003.commit.json"
    write_json(base_path, base)
    digest = base_commit_digest(base)
    target = tmp_path / ".story-system/corrections/chapter_003" / digest
    write_json(target / "requests/r1.request.json", request)
    write_json(target / "authorizations/a1.authorization.json", authorization)
    write_json(target / "corrections/c1.correction.json", correction)
    before = snapshot(tmp_path)
    runtime_before = load_runtime_sources(tmp_path, 3).to_dict()
    unresolved = preview_chapter_corrections(tmp_path, 3, digest)
    assert unresolved.ok is False and "HUMAN_AUTHORITY_UNVERIFIED" in {item.code for item in unresolved.diagnostics}
    preview = preview_chapter_corrections(tmp_path, 3, digest, [verification])
    assert preview.ok is True and preview.applied_correction_ids == ("c1",)
    assert before == snapshot(tmp_path)
    conflict = {**authorization, "authorization_id": "a2", "choice": "REJECT"}
    write_json(target / "authorizations/a2.authorization.json", conflict)
    before_conflict = snapshot(tmp_path)
    conflicted = preview_chapter_corrections(tmp_path, 3, digest, [verification])
    assert conflicted.ok is False
    assert "AUTHORIZATION_CONFLICT" in {item.code for item in conflicted.diagnostics}
    runtime_after = load_runtime_sources(tmp_path, 3).to_dict()
    assert runtime_before == runtime_after
    assert before_conflict == snapshot(tmp_path)


def test_zero_correction_preview_returns_clean_base_without_writes(tmp_path):
    base, *_ = edge_fixtures()
    path = tmp_path / ".story-system/commits/chapter_003.commit.json"
    write_json(path, base)
    digest = base_commit_digest(base)
    before = snapshot(tmp_path)
    result = preview_chapter_corrections(tmp_path, 3, digest)
    assert result.ok is True and result.applied_correction_ids == ()
    assert before == snapshot(tmp_path)


def test_preview_preserves_preexisting_sibling_corrections_and_never_selects_a_winner(tmp_path):
    base, correction, request, authorization, verification = edge_fixtures()
    write_json(tmp_path / ".story-system/commits/chapter_003.commit.json", base)
    digest = base_commit_digest(base)
    target = tmp_path / ".story-system/corrections/chapter_003" / digest
    write_json(target / "requests/r1.request.json", request)
    write_json(target / "authorizations/a1.authorization.json", authorization)
    write_json(target / "corrections/c1.correction.json", correction)
    sibling = {**correction, "correction_id": "c2"}
    write_json(target / "corrections/c2.correction.json", sibling)
    before = snapshot(tmp_path)
    result = preview_chapter_corrections(tmp_path, 3, digest, [verification])
    assert result.ok is False and result.effective_revision_id is None
    assert "LINEAGE_SIBLING_CONFLICT" in {item.code for item in result.diagnostics}
    assert before == snapshot(tmp_path)


def test_normal_runtime_has_no_import_path_to_correction_modules():
    root = Path(__file__).resolve().parents[3]
    blocked = ("canon_correction_store", "canon_correction_resolver", "canon_correction_preview")
    for path in root.rglob("*"):
        if not path.is_file() or path.suffix not in {".py", ".md"}:
            continue
        if "/tests/" in path.as_posix() or "/6.4.0/" in path.as_posix() or "/docs/" in path.as_posix() or path.name.startswith("canon_correction_"):
            continue
        source = path.read_text(encoding="utf-8")
        assert not any(name in source for name in blocked), str(path)
