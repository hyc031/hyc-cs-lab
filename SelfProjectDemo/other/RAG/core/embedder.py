"""嵌入模型封装：调用硅基流动 Qwen/Qwen3-Embedding-4B 接口。

- 支持批量文本向量化
- 向量 L2 归一化后存入 FAISS（内积即余弦相似度）
- 内置重试与错误信息提示
"""
import time

import numpy as np
import requests

from .config import settings


class EmbeddingError(RuntimeError):
    pass


class SiliconFlowEmbedder:
    def __init__(self, api_key: str | None = None, model: str | None = None):
        self.api_key = api_key or settings.API_KEY
        self.model = model or settings.EMBEDDING_MODEL
        self.endpoint = f"{settings.BASE_URL}/embeddings"

    def _post(self, texts: list[str], retries: int = 3) -> list[list[float]]:
        payload = {"model": self.model, "input": texts}
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        last_error = None
        for attempt in range(retries):
            try:
                resp = requests.post(
                    self.endpoint, json=payload, headers=headers, timeout=120
                )
                if resp.status_code == 200:
                    data = sorted(resp.json()["data"], key=lambda d: d["index"])
                    return [item["embedding"] for item in data]
                last_error = f"HTTP {resp.status_code}: {resp.text[:300]}"
            except requests.RequestException as exc:  # 网络异常重试
                last_error = str(exc)
            time.sleep(1.5 * (attempt + 1))
        raise EmbeddingError(f"嵌入模型调用失败（{self.model}）：{last_error}")

    def embed(self, texts: list[str], batch_size: int = 16) -> np.ndarray:
        """批量向量化，返回归一化后的 float32 矩阵 (n, dim)。"""
        if not texts:
            return np.zeros((0, 0), dtype=np.float32)
        vectors: list[list[float]] = []
        for i in range(0, len(texts), batch_size):
            vectors.extend(self._post(texts[i : i + batch_size]))
        matrix = np.asarray(vectors, dtype=np.float32)
        norms = np.linalg.norm(matrix, axis=1, keepdims=True)
        norms[norms == 0] = 1.0
        return matrix / norms

    def embed_query(self, text: str) -> np.ndarray:
        """查询向量化，返回形状 (dim,) 的归一化向量。"""
        return self.embed([text])[0]
