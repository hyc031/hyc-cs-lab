"""RAG 知识库：主路径 LangChain + FAISS + Qwen3-Embedding-4B。

未安装 langchain/faiss 或向量索引构建失败时，自动降级为
纯本地关键词检索（字符 bigram 重叠度），保证演示不中断。
"""
from __future__ import annotations

import threading
from pathlib import Path

import requests

from .token_counter import estimate_tokens


class KnowledgeBase:
    def __init__(self, kb_dir: Path):
        self.kb_dir = kb_dir
        self.lock = threading.Lock()
        self.engine = "none"       # langchain-faiss / local / none
        self.chunks: list[dict] = []   # 本地降级引擎使用
        self.vectorstore = None
        self.doc_names: list[str] = []
        self.error: str | None = None

    # ---------- 文档 ----------
    def _load_docs(self) -> list[tuple[str, str]]:
        docs = []
        if not self.kb_dir.exists():
            return docs
        for path in sorted(self.kb_dir.glob("*")):
            if path.suffix.lower() in (".md", ".txt", ".markdown"):
                try:
                    text = path.read_text("utf-8")
                except Exception:
                    continue
                if text.strip():
                    docs.append((path.name, text))
        return docs

    @staticmethod
    def _split(text: str, size: int = 400, overlap: int = 60) -> list[str]:
        """按段落优先的简单分块。"""
        paras = [p.strip() for p in text.replace("\r\n", "\n").split("\n\n") if p.strip()]
        chunks: list[str] = []
        buf = ""
        for para in paras:
            if len(buf) + len(para) <= size:
                buf = (buf + "\n" + para).strip()
            else:
                if buf:
                    chunks.append(buf)
                while len(para) > size:
                    chunks.append(para[:size])
                    para = para[size - overlap:]
                buf = para
        if buf:
            chunks.append(buf)
        return chunks

    # ---------- 构建 ----------
    def rebuild(self, settings: dict) -> dict:
        with self.lock:
            docs = self._load_docs()
            self.doc_names = [name for name, _ in docs]
            self.error = None
            self.vectorstore = None
            self.chunks = []
            self.engine = "none"
            if not docs:
                return {"engine": "none", "chunks": 0, "docs": [], "message": "知识库目录为空"}

            all_chunks = []
            for name, text in docs:
                for i, chunk in enumerate(self._split(text)):
                    all_chunks.append({"source": name, "chunk_id": i, "text": chunk})

            # 主路径：LangChain + FAISS
            try:
                self._build_langchain(settings, docs)
                self.chunks = all_chunks  # 保留一份文本，供本地展示
                return {"engine": self.engine, "chunks": len(all_chunks),
                        "docs": self.doc_names, "message": "LangChain + FAISS 索引构建成功"}
            except Exception as exc:
                self.error = str(exc)

            # 降级路径：本地关键词检索
            self.chunks = all_chunks
            self.engine = "local"
            return {"engine": self.engine, "chunks": len(all_chunks), "docs": self.doc_names,
                    "message": f"已降级为本地关键词检索（LangChain/FAISS 不可用：{self.error[:120]}）"}

    def _build_langchain(self, settings: dict, docs: list[tuple[str, str]]) -> None:
        from langchain_community.vectorstores import FAISS
        from langchain_community.vectorstores.utils import DistanceStrategy
        from langchain_core.documents import Document
        from langchain_core.embeddings import Embeddings

        emb_cfg = settings["embedding"]

        class SiliconFlowEmbeddings(Embeddings):
            """LangChain 标准 Embeddings 接口 -> 硅基流动 /v1/embeddings。"""

            def _embed(self, texts: list[str]) -> list[list[float]]:
                import math
                vectors: list[list[float]] = []
                for i in range(0, len(texts), 32):
                    batch = texts[i:i + 32]
                    resp = requests.post(
                        f"{emb_cfg['base_url'].rstrip('/')}/embeddings",
                        headers={
                            "Authorization": f"Bearer {emb_cfg['api_key']}",
                            "Content-Type": "application/json",
                        },
                        json={"input": batch, "model": emb_cfg["model"]},
                        timeout=60,
                    )
                    if resp.status_code != 200:
                        raise RuntimeError(f"embeddings HTTP {resp.status_code}: {resp.text[:200]}")
                    data = sorted(resp.json()["data"], key=lambda d: d["index"])
                    vectors.extend(d["embedding"] for d in data)
                # L2 归一化：配合内积距离等价于余弦相似度，保证相关度分数落在 [0,1]
                return [[v / (math.sqrt(sum(x * x for x in vec)) or 1.0) for v in vec]
                        for vec in vectors]

            def embed_documents(self, texts: list[str]) -> list[list[float]]:
                return self._embed(texts)

            def embed_query(self, text: str) -> list[float]:
                return self._embed([text])[0]

        embeddings = SiliconFlowEmbeddings()
        documents = [Document(page_content=text, metadata={"source": name}) for name, text in docs]
        self.vectorstore = FAISS.from_documents(
            documents, embeddings,
            distance_strategy=DistanceStrategy.MAX_INNER_PRODUCT,
        )
        self.engine = "langchain-faiss"

    # ---------- 检索 ----------
    def retrieve(self, settings: dict, query: str, k: int = 3) -> tuple[list[dict], str]:
        """返回 (chunks, engine)。chunk: {source, text, score}"""
        with self.lock:
            if self.engine == "langchain-faiss" and self.vectorstore is not None:
                try:
                    pairs = self.vectorstore.similarity_search_with_relevance_scores(query, k=k)
                    return ([{"source": d.metadata.get("source", "?"), "text": d.page_content,
                              "score": round(float(score), 4)} for d, score in pairs], self.engine)
                except Exception:
                    pass  # 落回本地检索
            if self.engine in ("local", "langchain-faiss"):
                return self._local_retrieve(query, k), "local" if self.engine == "local" else "local-fallback"
            return [], "none"

    def _local_retrieve(self, query: str, k: int) -> list[dict]:
        if not self.chunks:
            return []
        qgrams = _bigrams(query)
        scored = []
        for chunk in self.chunks:
            grams = _bigrams(chunk["text"])
            if not grams:
                continue
            overlap = len(qgrams & grams) / max(1, min(len(qgrams), len(grams)))
            scored.append((overlap, chunk))
        scored.sort(key=lambda x: -x[0])
        return [{"source": c["source"], "text": c["text"], "score": round(s, 4)}
                for s, c in scored[:k] if s > 0]

    def ensure_ready(self, settings: dict) -> None:
        """首次使用时自动构建索引。"""
        if self.engine == "none" and not self.chunks:
            self.rebuild(settings)


def _bigrams(text: str) -> set[str]:
    s = "".join(ch for ch in text if ch.isalnum())
    return {s[i:i + 2] for i in range(len(s) - 1)} if len(s) > 1 else {s} if s else set()


def embed_test(settings: dict) -> dict:
    """设置面板的 embedding「测试连接」。"""
    cfg = settings["embedding"]
    try:
        resp = requests.post(
            f"{cfg['base_url'].rstrip('/')}/embeddings",
            headers={"Authorization": f"Bearer {cfg['api_key']}", "Content-Type": "application/json"},
            json={"input": "连接测试", "model": cfg["model"]},
            timeout=30,
        )
        data = resp.json()
        if resp.status_code != 200:
            return {"ok": False, "message": f"HTTP {resp.status_code}: {data}"}
        dims = len(data["data"][0]["embedding"])
        return {"ok": True, "message": f"连接成功，模型 {cfg['model']} 输出维度：{dims}"}
    except Exception as exc:
        return {"ok": False, "message": str(exc)}
