"""Migrated from V0.6: HybridRetriever tests."""
from litepaperreader.core.purifier import TextChunk
from litepaperreader.core.retrieval import HybridRetriever


def chunk(text, start, end):
    return TextChunk(text=text, source_start=start, source_end=end, fragments=())


class FakeEncoder:
    def score(self, query, texts, batch_size):
        assert batch_size == 2
        return [0.1, 0.9, 0.2][:len(texts)]


def test_bm25_returns_grounded_hits():
    chunks = [
        chunk("alpha beta", 0, 10),
        chunk("gamma delta", 11, 22),
        chunk("epsilon zeta", 23, 35),
    ]
    retriever = HybridRetriever(chunks)
    hits = retriever.search("alpha", top_k=1)
    assert len(hits) == 1
    assert hits[0].chunk_id == "chunk-0000"
    assert hits[0].chunk.source_start == 0
    assert hits[0].bm25_score > 0


def test_semantic_scores_are_batched_and_fused():
    chunks = [chunk("lexical miss", 0, 12), chunk("semantic best", 13, 26), chunk("other", 27, 32)]
    retriever = HybridRetriever(chunks, semantic_encoder=FakeEncoder(), semantic_batch_size=2)
    hits = retriever.search("question", top_k=2)
    assert hits[0].chunk_id == "chunk-0001"
    assert hits[0].semantic_score == 0.9
    assert len(hits) == 2


def test_empty_search():
    retriever = HybridRetriever([])
    hits = retriever.search("anything", top_k=5)
    assert hits == []


def test_num_chunks_property():
    chunks = [chunk("a", 0, 1), chunk("b", 2, 3)]
    retriever = HybridRetriever(chunks)
    assert retriever.num_chunks == 2
