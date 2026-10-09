from __future__ import annotations

import io
import json

from intelligence.conflict_adapters import OllamaConflictAdapter


def _response(payload: object) -> io.BytesIO:
    return io.BytesIO(json.dumps(payload).encode())


def test_ollama_health_requires_configured_model():
    adapter = OllamaConflictAdapter(
        model="qwen2.5:3b",
        opener=lambda request, timeout: _response({"models": [{"name": "qwen2.5:3b"}]}),
    )

    assert adapter.is_available()


def test_ollama_health_is_false_when_model_is_missing():
    adapter = OllamaConflictAdapter(
        model="qwen2.5:3b",
        opener=lambda request, timeout: _response({"models": [{"name": "other:latest"}]}),
    )

    assert not adapter.is_available()


def test_ollama_health_is_false_when_runtime_cannot_be_reached():
    def raise_connection_error(request, timeout):
        raise OSError("Ollama is not running")

    adapter = OllamaConflictAdapter(opener=raise_connection_error)

    assert not adapter.is_available()
