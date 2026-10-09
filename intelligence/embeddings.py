"""Local embedding providers used by semantic retrieval."""

from __future__ import annotations

import os
from dataclasses import dataclass
from threading import Lock
from typing import Any

from contracts.base import Result
from intelligence.retrieval import EmbeddingService


@dataclass(frozen=True)
class EmbeddingConfig:
    """Configuration for the local Sentence Transformers provider."""

    provider: str = "sentence-transformers"
    model: str = "sentence-transformers/all-MiniLM-L6-v2"
    device: str = "cpu"

    def __post_init__(self) -> None:
        if self.provider != "sentence-transformers":
            raise ValueError(
                "Unsupported RECALL_EMBEDDING_PROVIDER "
                f"{self.provider!r}; supported value: 'sentence-transformers'"
            )
        if not self.model.strip():
            raise ValueError("RECALL_EMBEDDING_MODEL must not be empty")
        if not self.device.strip():
            raise ValueError("RECALL_EMBEDDING_DEVICE must not be empty")

    @classmethod
    def from_env(cls) -> EmbeddingConfig:
        """Read the documented local embedding configuration."""
        return cls(
            provider=os.environ.get(
                "RECALL_EMBEDDING_PROVIDER", "sentence-transformers"
            ),
            model=os.environ.get(
                "RECALL_EMBEDDING_MODEL",
                "sentence-transformers/all-MiniLM-L6-v2",
            ),
            device=os.environ.get("RECALL_EMBEDDING_DEVICE", "cpu"),
        )


class SentenceTransformerEmbeddingService(EmbeddingService):
    """Lazy, local Sentence Transformers implementation of EmbeddingService."""

    def __init__(self, config: EmbeddingConfig) -> None:
        self.config = config
        self._model: Any = None
        self._load_error: str | None = None
        self._load_lock = Lock()

    def generate_embedding(self, text: str) -> Result[list[float]]:
        result = self.generate_embeddings([text])
        if not result.success:
            return Result.err(result.error or "Embedding generation failed")
        return Result.ok((result.value or [[]])[0])

    def generate_embeddings(self, texts: list[str]) -> Result[list[list[float]]]:
        if not texts:
            return Result.ok([])

        model_result = self._get_model()
        if not model_result.success:
            return Result.err(model_result.error or "Embedding model unavailable")
        try:
            vectors = model_result.value.encode(
                texts,
                convert_to_numpy=True,
                normalize_embeddings=True,
            )
            return Result.ok(vectors.tolist())
        except Exception as exc:
            return Result.err(
                f"Sentence Transformers embedding failed for model "
                f"{self.config.model!r} on {self.config.device}: {exc}"
            )

    def _get_model(self) -> Result[Any]:
        if self._model is not None:
            return Result.ok(self._model)
        if self._load_error is not None:
            return Result.err(self._load_error)

        with self._load_lock:
            if self._model is not None:
                return Result.ok(self._model)
            if self._load_error is not None:
                return Result.err(self._load_error)
            try:
                from sentence_transformers import SentenceTransformer

                self._model = SentenceTransformer(
                    self.config.model,
                    device=self.config.device,
                )
                return Result.ok(self._model)
            except Exception as exc:
                self._load_error = (
                    f"Could not load Sentence Transformers model "
                    f"{self.config.model!r} on {self.config.device}: {exc}. "
                    "Install RECALL's semantic extra with "
                    "`python -m pip install -e 'core[semantic]'`, then verify "
                    "the model name and local model cache/network access."
                )
                return Result.err(self._load_error)


class ChromaSentenceTransformerEmbeddingFunction:
    """Chroma embedding-function adapter using the configured local provider."""

    def __init__(
        self,
        service: EmbeddingService,
        config: EmbeddingConfig,
    ) -> None:
        self._service = service
        self._config = config

    def __call__(self, input: list[str]) -> list[list[float]]:
        result = self._service.generate_embeddings(input)
        if not result.success:
            raise RuntimeError(result.error or "Embedding generation failed")
        return result.value or []

    def embed_query(self, input: list[str]) -> list[list[float]]:
        return self(input)

    @staticmethod
    def name() -> str:
        return "recall_sentence_transformers"

    def is_legacy(self) -> bool:
        return False

    def default_space(self) -> str:
        return "cosine"

    def supported_spaces(self) -> list[str]:
        return ["cosine"]

    def get_config(self) -> dict[str, str]:
        return {
            "provider": self._config.provider,
            "model": self._config.model,
            "device": self._config.device,
        }

    @staticmethod
    def build_from_config(config: dict[str, Any]) -> ChromaSentenceTransformerEmbeddingFunction:
        embedding_config = EmbeddingConfig(
            provider=config["provider"],
            model=config["model"],
            device=config["device"],
        )
        return ChromaSentenceTransformerEmbeddingFunction(
            SentenceTransformerEmbeddingService(embedding_config),
            embedding_config,
        )
