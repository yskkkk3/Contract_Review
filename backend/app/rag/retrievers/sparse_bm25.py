"""Sparse (BM25) retriever: rank-bm25 with jieba tokenization (Chinese)."""
import pickle
from pathlib import Path

import jieba
from rank_bm25 import BM25Okapi

from app.rag.ingest.chunker import Chunk


def tokenize(text: str) -> list[str]:
    """jieba 分词 + 英文小写 token 归一。"""
    tokens = [t.strip().lower() for t in jieba.cut(text) if t.strip()]
    return tokens


class BM25Index:
    """BM25Okapi 索引：支持增量构建/持久化/查询。

    简历点：知识库规模下内存索引毫秒级召回；sparse 路径不依赖向量库，
    与 dense 路径形成语义+词汇双路召回，RRF 融合。
    """

    def __init__(self) -> None:
        self._chunks: list[Chunk] = []
        self._corpus: list[list[str]] = []
        self._bm25: BM25Okapi | None = None

    def add_chunks(self, chunks: list[Chunk]) -> None:
        self._chunks.extend(chunks)
        self._corpus.extend(tokenize(c.text) for c in chunks)
        self._bm25 = BM25Okapi(self._corpus)

    def search(self, query: str, top_k: int = 30, doc_type: str | None = None) -> list[tuple[Chunk, float]]:
        if not self._bm25:
            return []
        q_tokens = tokenize(query)
        scores = self._bm25.get_scores(q_tokens)
        ranked = sorted(enumerate(scores), key=lambda x: x[1], reverse=True)
        out: list[tuple[Chunk, float]] = []
        for idx, score in ranked:
            if score <= 0:
                continue
            chunk = self._chunks[idx]
            if doc_type and chunk.doc_type != doc_type:
                continue
            out.append((chunk, float(score)))
            if len(out) >= top_k:
                break
        return out

    def save(self, path: str | Path) -> None:
        with open(path, "wb") as f:
            pickle.dump({"chunks": self._chunks, "corpus": self._corpus}, f)

    @classmethod
    def load(cls, path: str | Path) -> "BM25Index":
        with open(path, "rb") as f:
            data = pickle.load(f)
        idx = cls()
        idx._chunks = data["chunks"]
        idx._corpus = data["corpus"]
        idx._bm25 = BM25Okapi(idx._corpus)
        return idx
