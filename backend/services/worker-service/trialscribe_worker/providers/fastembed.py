"""Local CPU embeddings through fastembed, never on the event loop."""

import asyncio
from collections.abc import Iterable, Sequence
from time import monotonic
from typing import Protocol

from trialscribe_worker.providers.types import EmbeddingRequest, EmbeddingResult
from trialscribe_worker.utils.exceptions import ProviderConfigError


class SyncEmbedder(Protocol):
    def embed(self, texts: Sequence[str]) -> Iterable[object]: ...


class FastEmbedProvider:
    """Run a blocking ONNX embedder on a worker thread."""

    def __init__(self, embedder: SyncEmbedder, model: str, dimensions: int) -> None:
        self._embedder = embedder
        self._model = model
        self._dimensions = dimensions

    async def embed(self, request: EmbeddingRequest) -> EmbeddingResult:
        """Embed texts off the event loop and reject the wrong width."""

        started = monotonic()
        raw_vectors = await asyncio.to_thread(self._embed, request.texts)
        return EmbeddingResult(
            vectors=raw_vectors,
            model=request.model or self._model,
            dimensions=self._dimensions,
            input_tokens=len(request.texts),
            latency_ms=max(0, int((monotonic() - started) * 1000)),
        )

    def _embed(self, texts: Sequence[str]) -> list[list[float]]:
        vectors: list[list[float]] = []
        for raw in self._embedder.embed(texts):
            vector = [float(value) for value in raw]
            if len(vector) != self._dimensions:
                raise ProviderConfigError
            vectors.append(vector)
        return vectors
