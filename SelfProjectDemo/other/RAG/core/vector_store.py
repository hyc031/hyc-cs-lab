"""FAISS 向量库封装：持久化索引 + 分块元数据管理。

磁盘结构（data/vectorstore/）：
- index.faiss   FAISS 索引（内积/余弦）
- vectors.npy   原始向量（用于重建索引与删除文档，无需重新嵌入）
- chunks.json   分块元数据（文档名、序号、字符区间、原文）
"""
import json
import threading
import time
from collections import defaultdict
from pathlib import Path

import faiss
import numpy as np

from .config import settings


class FaissVectorStore:
    def __init__(self, store_dir: Path | str | None = None):
        self.dir = Path(store_dir or settings.VECTOR_DIR)
        self.dir.mkdir(parents=True, exist_ok=True)
        self.index_path = self.dir / "index.faiss"
        self.vectors_path = self.dir / "vectors.npy"
        self.chunks_path = self.dir / "chunks.json"
        self._lock = threading.Lock()
        self._vectors: np.ndarray | None = None
        self._chunks: list[dict] = []
        self._index: faiss.Index | None = None
        self._load()

    # ---------- 持久化 ----------
    def _load(self) -> None:
        if self.vectors_path.exists() and self.chunks_path.exists():
            self._vectors = np.load(self.vectors_path).astype(np.float32)
            self._chunks = json.loads(self.chunks_path.read_text(encoding="utf-8"))
        else:
            self._vectors = np.zeros((0, 0), dtype=np.float32)
            self._chunks = []
        if self.index_path.exists():
            self._index = faiss.read_index(str(self.index_path))
        else:
            self._rebuild_index()

    def _rebuild_index(self) -> None:
        dim = self._vectors.shape[1] if self._vectors.ndim == 2 and self._vectors.shape[0] else 0
        if dim == 0:
            self._index = None
            return
        index = faiss.IndexFlatIP(dim)  # 内积 + 归一化向量 = 余弦相似度
        index.add(self._vectors)
        self._index = index
        faiss.write_index(index, str(self.index_path))

    def _save(self) -> None:
        np.save(self.vectors_path, self._vectors)
        self.chunks_path.write_text(
            json.dumps(self._chunks, ensure_ascii=False, indent=1), encoding="utf-8"
        )
        self._rebuild_index()

    # ---------- 增删查 ----------
    def add(self, doc_id: str, doc_name: str, chunks: list[dict], vectors: np.ndarray) -> None:
        """写入一个文档的全部分块及其向量。"""
        assert len(chunks) == len(vectors), "分块数与向量数不一致"
        with self._lock:
            records = [
                {
                    "id": f"{doc_id}:{c['chunk_index']}",
                    "doc_id": doc_id,
                    "doc_name": doc_name,
                    "chunk_index": c["chunk_index"],
                    "text": c["text"],
                    "start": c["start"],
                    "end": c["end"],
                    "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
                }
                for c in chunks
            ]
            vectors = vectors.astype(np.float32)
            if self._vectors.size == 0:
                self._vectors = vectors
            else:
                self._vectors = np.vstack([self._vectors, vectors])
            self._chunks.extend(records)
            self._save()

    def search(self, query_vector: np.ndarray, top_k: int = 4) -> list[dict]:
        """余弦相似度检索，返回按相似度降序的分块列表。"""
        if self._index is None or self._index.ntotal == 0:
            return []
        query = np.asarray(query_vector, dtype=np.float32).reshape(1, -1)
        scores, ids = self._index.search(query, min(top_k, self._index.ntotal))
        results = []
        for score, idx in zip(scores[0], ids[0]):
            if idx < 0:
                continue
            item = dict(self._chunks[int(idx)])
            item["score"] = round(float(score), 4)
            results.append(item)
        return results

    def delete_document(self, doc_id: str) -> int:
        """删除某个文档的全部分块（重建索引实现）。"""
        with self._lock:
            keep = [c for c in self._chunks if c["doc_id"] != doc_id]
            removed = len(self._chunks) - len(keep)
            if removed == 0:
                return 0
            keep_ids = {c["id"] for c in keep}
            mask = [
                i for i, c in enumerate(self._chunks) if c["id"] in keep_ids
            ]
            self._chunks = keep
            self._vectors = self._vectors[mask] if mask else np.zeros((0, 0), dtype=np.float32)
            self._save()
            return removed

    def clear(self) -> None:
        with self._lock:
            self._chunks = []
            self._vectors = np.zeros((0, 0), dtype=np.float32)
            for path in (self.index_path, self.vectors_path, self.chunks_path):
                if path.exists():
                    path.unlink()
            self._index = None

    # ---------- 统计与浏览 ----------
    def stats(self) -> dict:
        docs: dict[str, dict] = defaultdict(lambda: {"chunks": 0, "chars": 0})
        for c in self._chunks:
            entry = docs[c["doc_name"]]
            entry["doc_id"] = c["doc_id"]
            entry["chunks"] += 1
            entry["chars"] += len(c["text"])
        return {
            "total_chunks": len(self._chunks),
            "total_docs": len(docs),
            "dimensions": int(self._vectors.shape[1]) if self._vectors.ndim == 2 and self._vectors.size else 0,
            "documents": dict(docs),
        }

    def get_chunks(self, doc_id: str | None = None) -> list[dict]:
        if doc_id is None:
            return list(self._chunks)
        return [c for c in self._chunks if c["doc_id"] == doc_id]
