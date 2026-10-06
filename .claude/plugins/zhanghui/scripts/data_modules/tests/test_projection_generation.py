from types import SimpleNamespace

import pytest
from threading import Event, Thread

from data_modules.event_projection_router import EventProjectionRouter
from data_modules.projection_generation import (
    ProjectionGeneration, GenerationError,
)
import data_modules.projection_generation as generation_module


def _snapshot(digest="a" * 64, lineage="b" * 64):
    return SimpleNamespace(
        effective_history_digest=digest,
        correction_lineage_digest=lineage,
        base_set_digest="c" * 64,
        activation_record_id=None,
        chapters={},
        dependencies=(),
    )


def _write_all_domains(handle):
    expected = {}
    for domain in EventProjectionRouter.PROJECTION_MANIFEST:
        path = f"{domain}/payload.json"
        data = (f'{{"domain":"{domain}"}}\n').encode()
        handle.write_domain_file(domain, path, data)
        expected.setdefault(domain, {})[path] = handle.digest_bytes(data)
    return {"domains": expected}


def test_publication_is_monotonic_and_reader_pins_complete_generation(tmp_path):
    protocol = ProjectionGeneration(tmp_path)
    snapshot = _snapshot()
    handle = protocol.begin(snapshot)
    expected = _write_all_domains(handle)
    validated = protocol.validate_generation(handle, expected)
    publication = protocol.publish_generation(validated, None, snapshot.correction_lineage_digest)
    pinned = protocol.pin_active_generation()
    assert pinned.publication_record_id == publication.publication_record_id
    assert pinned.generation_id == validated.generation_id
    assert len(pinned.manifest["domains"]) == 7
    assert protocol.pin_active_generation() == pinned


def test_missing_domain_output_never_publishes(tmp_path):
    protocol = ProjectionGeneration(tmp_path)
    handle = protocol.begin(_snapshot())
    expected = _write_all_domains(handle)
    expected["domains"].pop("vector")
    with pytest.raises(GenerationError, match="DOMAIN_SET_MISMATCH"):
        protocol.validate_generation(handle, expected)
    assert protocol.pin_active_generation() is None


def test_semantic_pointer_rollback_is_rejected(tmp_path):
    protocol = ProjectionGeneration(tmp_path)
    first = _snapshot("a" * 64, "b" * 64)
    first_handle = protocol.begin(first)
    first_generation = protocol.validate_generation(first_handle, _write_all_domains(first_handle))
    first_record = protocol.publish_generation(first_generation, None, first.correction_lineage_digest)
    second = _snapshot("d" * 64, "e" * 64)
    second_handle = protocol.begin(second)
    second_generation = protocol.validate_generation(second_handle, _write_all_domains(second_handle))
    protocol.publish_generation(second_generation, first_record.record_sha256, second.correction_lineage_digest)

    rollback = _snapshot("a" * 64, "b" * 64)
    rollback_handle = protocol.begin(rollback)
    rollback_generation = protocol.validate_generation(rollback_handle, _write_all_domains(rollback_handle))
    with pytest.raises(GenerationError, match="SEMANTIC_ROLLBACK_REJECTED"):
        protocol.publish_generation(rollback_generation, protocol.latest_publication().record_sha256,
                                   rollback.correction_lineage_digest)


def test_lock_time_lineage_mismatch_blocks_publication(tmp_path):
    protocol = ProjectionGeneration(tmp_path)
    snapshot = _snapshot()
    handle = protocol.begin(snapshot)
    validated = protocol.validate_generation(handle, _write_all_domains(handle))
    with pytest.raises(GenerationError, match="LINEAGE_CHANGED"):
        protocol.publish_generation(validated, None, "f" * 64)


def test_incomplete_staging_is_not_visible_to_runtime_reader(tmp_path):
    protocol = ProjectionGeneration(tmp_path)
    handle = protocol.begin(_snapshot())
    handle.write_domain_file("events", "events/partial.json", b"partial")
    assert protocol.pin_active_generation() is None


def test_candidate_dependency_change_between_build_and_publish_fails_closed(tmp_path):
    dependency = tmp_path / ".story-system/corrections/request.json"
    dependency.parent.mkdir(parents=True)
    dependency.write_text("original", encoding="utf-8")
    digest = handle_digest(b"original")
    snapshot = _snapshot()
    snapshot.dependencies = ({"path": dependency.relative_to(tmp_path).as_posix(), "sha256": digest},)
    protocol = ProjectionGeneration(tmp_path)
    handle = protocol.begin(snapshot)
    validated = protocol.validate_generation(handle, _write_all_domains(handle))
    dependency.write_text("changed while generation built", encoding="utf-8")
    with pytest.raises(GenerationError, match="LINEAGE_CHANGED"):
        protocol.publish_generation(validated, None, snapshot.correction_lineage_digest)
    assert protocol.pin_active_generation() is None


def test_candidate_namespace_append_between_build_and_publish_fails_closed(tmp_path):
    from data_modules.canon_correction_schema import artifact_sha256

    namespace = tmp_path / ".story-system/corrections/chapter_001/base/corrections"
    namespace.mkdir(parents=True)
    (namespace / "first.json").write_text('{"id":"first"}', encoding="utf-8")
    rows = [{"path": (path.relative_to(tmp_path).as_posix()),
             "sha256": handle_digest(path.read_bytes())}
            for path in sorted(namespace.glob("*.json"))]
    snapshot = _snapshot()
    snapshot.lineage_namespace_checks = ({
        "path": ".story-system/corrections/chapter_001/base",
        "kind": "correction_namespace",
        "sha256": artifact_sha256(rows),
    },)
    protocol = ProjectionGeneration(tmp_path)
    handle = protocol.begin(snapshot)
    validated = protocol.validate_generation(handle, _write_all_domains(handle))
    (namespace / "new-pending-request.json").write_text('{"id":"pending"}', encoding="utf-8")
    with pytest.raises(GenerationError, match="LINEAGE_CHANGED"):
        protocol.publish_generation(validated, None, snapshot.correction_lineage_digest)
    assert protocol.pin_active_generation() is None


def test_manifest_fsync_failure_never_publishes(monkeypatch, tmp_path):
    protocol = ProjectionGeneration(tmp_path)
    handle = protocol.begin(_snapshot())
    expected = _write_all_domains(handle)
    monkeypatch.setattr(generation_module, "_fsync_directory",
                        lambda _path: (_ for _ in ()).throw(OSError("TEST ONLY fsync failure")))
    with pytest.raises(OSError, match="TEST ONLY fsync failure"):
        protocol.validate_generation(handle, expected)
    assert protocol.pin_active_generation() is None


def test_generation_rename_failure_never_publishes(monkeypatch, tmp_path):
    protocol = ProjectionGeneration(tmp_path)
    handle = protocol.begin(_snapshot())
    expected = _write_all_domains(handle)
    original = generation_module.os.replace

    def fail_generation_rename(source, target):
        if str(source).endswith(handle.staging_root.name):
            raise OSError("TEST ONLY generation rename failure")
        return original(source, target)

    monkeypatch.setattr(generation_module.os, "replace", fail_generation_rename)
    with pytest.raises(OSError, match="TEST ONLY generation rename failure"):
        protocol.validate_generation(handle, expected)
    assert protocol.pin_active_generation() is None


def test_publication_waits_for_activation_lock(tmp_path):
    protocol = ProjectionGeneration(tmp_path)
    handle = protocol.begin(_snapshot())
    validated = protocol.validate_generation(handle, _write_all_domains(handle))
    held = generation_module.FileLock(str(protocol.lock_path))
    entered = Event()
    completed = Event()
    outcomes = []

    def publish():
        entered.set()
        try:
            outcomes.append(protocol.publish_generation(
                validated, None, handle.snapshot.correction_lineage_digest))
        except Exception as exc:  # captured for assertion in the main test thread
            outcomes.append(exc)
        finally:
            completed.set()

    with held:
        thread = Thread(target=publish)
        thread.start()
        assert entered.wait(timeout=1)
        assert not completed.wait(timeout=0.05)
    thread.join(timeout=2)
    assert completed.is_set()
    assert len(outcomes) == 1 and not isinstance(outcomes[0], Exception)
    assert protocol.pin_active_generation().publication_record_id == outcomes[0].publication_record_id


def test_publication_record_create_failure_never_changes_active_head(monkeypatch, tmp_path):
    protocol = ProjectionGeneration(tmp_path)
    handle = protocol.begin(_snapshot())
    validated = protocol.validate_generation(handle, _write_all_domains(handle))
    original = generation_module._atomic_create_json

    def fail_publication(path, body):
        if path.name.startswith("publication-"):
            raise GenerationError("TEST ONLY atomic create failure")
        return original(path, body)

    monkeypatch.setattr(generation_module, "_atomic_create_json", fail_publication)
    with pytest.raises(GenerationError, match="TEST ONLY atomic create failure"):
        protocol.publish_generation(validated, None, handle.snapshot.correction_lineage_digest)
    with pytest.raises(GenerationError, match="ENROLLED_PUBLICATION_MISSING"):
        protocol.pin_active_generation()
    # Enrollment is durable before the publication record; retries remain possible.
    monkeypatch.setattr(generation_module, "_atomic_create_json", original)
    retry_handle = protocol.begin(_snapshot())
    retry = protocol.validate_generation(retry_handle, _write_all_domains(retry_handle))
    protocol.publish_generation(retry, None, retry_handle.snapshot.correction_lineage_digest)
    assert protocol.pin_active_generation() is not None


def handle_digest(data):
    import hashlib
    return hashlib.sha256(data).hexdigest()
