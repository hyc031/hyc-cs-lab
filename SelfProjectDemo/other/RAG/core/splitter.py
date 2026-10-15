"""固定长度分块（基于 LangChain RecursiveCharacterTextSplitter）。

分块策略：按中文友好的分隔符层级递归切分，在接近 chunk_size 处断开，
相邻块之间保留 overlap 重叠字符，避免语义在边界处被截断。
"""
from langchain_text_splitters import RecursiveCharacterTextSplitter

# 中文友好的分隔符优先级
CHINESE_SEPARATORS = ["\n\n", "\n", "。", "！", "？", "；", "，", ". ", " ", ""]

# 不同分块模式的说明（本地知识库界面展示用）
CHUNK_MODES = {
    "固定长度分块": (
        "按固定字符数切分文本，优先在段落、句子等自然边界断开，"
        "相邻分块保留一定重叠字符。通用性最强，是系统的默认模式。"
    ),
}


def build_splitter(chunk_size: int, chunk_overlap: int) -> RecursiveCharacterTextSplitter:
    return RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        separators=CHINESE_SEPARATORS,
        length_function=len,
        keep_separator=True,
    )


def split_document(
    text: str,
    chunk_size: int = 500,
    chunk_overlap: int = 80,
) -> list[dict]:
    """固定长度分块，返回带字符区间的分块列表。

    每个分块: {chunk_index, text, start, end}
    """
    if not text.strip():
        return []

    splitter = build_splitter(chunk_size, chunk_overlap)
    chunks = []
    search_from = 0
    for index, piece in enumerate(splitter.split_text(text)):
        # 定位该分块在原文中的字符区间，便于引用溯源
        position = text.find(piece, search_from)
        if position == -1:
            position = text.find(piece)
        if position == -1:  # 理论上不会发生，兜底防止丢块
            position = search_from
        start = position
        end = position + len(piece)
        search_from = max(search_from, end - chunk_overlap)
        chunks.append(
            {
                "chunk_index": index,
                "text": piece,
                "start": start,
                "end": end,
            }
        )
    return chunks
