import hashlib

import pytest


@pytest.fixture(autouse=True)
def deterministic_generation_embeddings(monkeypatch):
    """Inject a repeatable provider for tests; production always calls the configured embed API."""
    from data_modules.vector_projection_writer import VectorProjectionWriter

    def embed(_writer, chunks):
        vectors = []
        for chunk in chunks:
            raw = hashlib.sha256(str(chunk.get("content") or "").encode("utf-8")).digest()
            vectors.append([((value / 255.0) * 2.0) - 1.0 for value in raw[:16]])
        return vectors

    monkeypatch.setattr(VectorProjectionWriter, "_generation_embeddings", embed)
