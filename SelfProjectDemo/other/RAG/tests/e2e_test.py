"""端到端测试（不启动界面）：解析 → 分块 → 向量化入库 → 检索 → 带引用问答。

用法：conda activate dt && python tests/e2e_test.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.config import settings
from core.document_loader import load_document
from core.embedder import SiliconFlowEmbedder
from core.rag_engine import RAGEngine
from core.splitter import split_document
from core.vector_store import FaissVectorStore


def main() -> None:
    demo = settings.UPLOAD_DIR.parent / "演示文档" / "主流大模型（LLM）介绍.docx"
    print(f"1) 解析文档：{demo.name}")
    text, meta = load_document(demo)
    print(f"   全文 {len(text)} 字符，元信息 {meta}")

    print("2) 固定长度分块")
    chunks = split_document(text, settings.CHUNK_SIZE, settings.CHUNK_OVERLAP)
    print(f"   共 {len(chunks)} 块；首块预览：{chunks[0]['text'][:80]}…")

    store = FaissVectorStore()
    store.clear()
    embedder = SiliconFlowEmbedder()
    print(f"3) 向量化入库（模型 {embedder.model}）")
    vectors = embedder.embed([c["text"] for c in chunks])
    store.add("demo001", demo.name, chunks, vectors)
    stats = store.stats()
    print(f"   完成：{stats['total_docs']} 文档 / {stats['total_chunks']} 分块 / 维度 {stats['dimensions']}")

    engine = RAGEngine(embedder=embedder, store=store)

    print("4) 智能问答（带引用 + 路由判断）")
    result = engine.answer(
        question="文档中提到的国内主流大模型有哪些？它们各自的代表模型是什么？",
        history=[],
        top_k=settings.TOP_K,
        score_threshold=0.2,
    )
    print(f"   路由：used_kb={result.used_kb}，理由：{result.route_reason}")
    print(f"   回答：{result.answer[:300]}")
    print(f"   引用 {len(result.citations)} 条：")
    for c in result.citations:
        print(f"     [{c.index}] {c.doc_name} 分块#{c.chunk_index} 相似度{c.score} 区间{c.start}-{c.end}")

    print("5) 无需知识库的问题（路由测试）")
    result2 = engine.answer(question="你好，简单介绍一下你自己", history=[])
    print(f"   路由：used_kb={result2.used_kb}，理由：{result2.route_reason}")
    print(f"   回答：{result2.answer[:150]}")

    print("\n✅ 端到端测试通过")


if __name__ == "__main__":
    main()
