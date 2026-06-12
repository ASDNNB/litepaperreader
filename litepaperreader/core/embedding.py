from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Literal

logger = logging.getLogger(__name__)


@dataclass
class EncoderConfig:
    provider: Literal["miniLM", "openai", "none"] = "none"
    model_name: str = "all-MiniLM-L6-v2"
    api_key: str | None = None
    api_base: str | None = None
    device: str = "cpu"


class SemanticEncoder:
    def __init__(self, config: EncoderConfig | None = None) -> None:
        self._config = config or EncoderConfig()
        self._model = None

    @property
    def is_available(self) -> bool:
        return self._config.provider != "none"

    def score(self, query: str, texts: list[str], batch_size: int = 32) -> list[float]:
        if self._config.provider == "none":
            raise RuntimeError("SemanticEncoder is configured as none.")
        if self._config.provider == "miniLM":
            return self._score_minilm(query, texts, batch_size)
        elif self._config.provider == "openai":
            return self._score_openai(query, texts, batch_size)
        else:
            raise ValueError(f"Unknown encoder provider: {self._config.provider}")

    def _lazy_load_model(self):
        if self._model is not None:
            return
        if self._config.provider == "miniLM":
            from sentence_transformers import SentenceTransformer
            self._model = SentenceTransformer(self._config.model_name, device=self._config.device)
            logger.info("Loaded MiniLM model: %s on %s", self._config.model_name, self._config.device)

    def _score_minilm(self, query, texts, batch_size):
        self._lazy_load_model()
        import numpy as np
        from sklearn.metrics.pairwise import cosine_similarity
        all_texts = [query] + texts
        embeddings = self._model.encode(all_texts, batch_size=batch_size, show_progress_bar=False)
        query_emb = embeddings[0].reshape(1, -1)
        doc_embs = embeddings[1:]
        similarities = cosine_similarity(query_emb, doc_embs).flatten().tolist()
        return [float(s) for s in similarities]

    def _score_openai(self, query, texts, batch_size):
        import numpy as np
        from openai import OpenAI
        client = OpenAI(api_key=self._config.api_key, base_url=self._config.api_base)
        all_texts = [query] + texts
        resp = client.embeddings.create(
            model=self._config.model_name or "text-embedding-3-small",
            input=all_texts,
        )
        embeddings = [np.array(d.embedding) for d in resp.data]
        query_emb = embeddings[0].reshape(1, -1)
        doc_embs = np.array(embeddings[1:])
        from sklearn.metrics.pairwise import cosine_similarity
        similarities = cosine_similarity(query_emb, doc_embs).flatten().tolist()
        return [float(s) for s in similarities]
