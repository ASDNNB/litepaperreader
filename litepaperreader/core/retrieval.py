from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from rank_bm25 import BM25Okapi
from litepaperreader.core.purifier import TextChunk


class SemanticEncoder(Protocol):
    def score(self, query: str, texts: list[str], batch_size: int) -> list[float]:
        ...


@dataclass(frozen=True)
class RetrievalHit:
    chunk_id: str
    chunk: TextChunk
    score: float
    bm25_score: float
    semantic_score: float | None


class HybridRetriever:
    def __init__(
        self,
        chunks: list[TextChunk],
        semantic_encoder: SemanticEncoder | None = None,
        semantic_batch_size: int = 32,
        rrf_k: int = 60,
    ) -> None:
        if semantic_batch_size <= 0:
            raise ValueError("semantic_batch_size must be positive")
        self._chunks = chunks
        self._chunk_ids = [f"chunk-{index:04d}" for index in range(len(chunks))]
        self._semantic_encoder = semantic_encoder
        self._semantic_batch_size = semantic_batch_size
        self._rrf_k = rrf_k
        tokenized = [self._tokenize(chunk.text) for chunk in chunks]
        self._bm25 = BM25Okapi(tokenized) if chunks else None

    @property
    def num_chunks(self) -> int:
        return len(self._chunks)

    def search(self, query: str, top_k: int = 5) -> list[RetrievalHit]:
        if top_k <= 0 or not self._chunks:
            return []
        bm25_scores = self._bm25.get_scores(self._tokenize(query)).tolist() if self._bm25 else []
        semantic_scores = self._semantic_scores(query)
        scores = self._fuse_scores(bm25_scores, semantic_scores)
        ordered = sorted(range(len(self._chunks)), key=lambda index: scores[index], reverse=True)
        return [
            RetrievalHit(
                chunk_id=self._chunk_ids[index],
                chunk=self._chunks[index],
                score=scores[index],
                bm25_score=float(bm25_scores[index]),
                semantic_score=None if semantic_scores is None else float(semantic_scores[index]),
            )
            for index in ordered[:top_k]
        ]

    def _semantic_scores(self, query: str) -> list[float] | None:
        if self._semantic_encoder is None:
            return None
        return self._semantic_encoder.score(
            query, [chunk.text for chunk in self._chunks],
            batch_size=self._semantic_batch_size,
        )

    def _fuse_scores(self, bm25_scores, semantic_scores):
        bm25_ranks = self._ranks_desc(bm25_scores)
        semantic_ranks = self._ranks_desc(semantic_scores) if semantic_scores is not None else {}
        fused = []
        for index in range(len(self._chunks)):
            score = 1 / (self._rrf_k + bm25_ranks[index])
            if semantic_scores is not None:
                score += 1 / (self._rrf_k + semantic_ranks[index])
            fused.append(score)
        return fused

    def _ranks_desc(self, scores):
        if scores is None:
            return {}
        ordered = sorted(range(len(scores)), key=lambda index: scores[index], reverse=True)
        return {index: rank + 1 for rank, index in enumerate(ordered)}

    def _tokenize(self, text: str) -> list[str]:
        return text.lower().split()
