"""文档解析：支持 PDF / Word(docx) / TXT / Markdown，统一抽取为纯文本。

每种格式解析后返回 (text, meta)：
- text: 按阅读顺序拼接的全文，段落之间用 \n\n 分隔
- meta: 与格式相关的辅助信息（页数、段落数等）
"""
from pathlib import Path

from .config import settings


def load_document(file_path: str | Path) -> tuple[str, dict]:
    """解析单个文档，返回全文文本与元信息。"""
    path = Path(file_path)
    ext = path.suffix.lower()

    if ext == ".pdf":
        return _load_pdf(path)
    if ext == ".docx":
        return _load_docx(path)
    if ext in {".txt", ".md", ".markdown"}:
        return _load_text(path)
    raise ValueError(f"不支持的文件类型：{ext}（支持 PDF / Word / TXT / Markdown）")


def _load_pdf(path: Path) -> tuple[str, dict]:
    from pypdf import PdfReader

    reader = PdfReader(str(path))
    pages = []
    for i, page in enumerate(reader.pages, start=1):
        text = (page.extract_text() or "").strip()
        if text:
            pages.append(f"【第{i}页】\n{text}")
    return "\n\n".join(pages), {"pages": len(reader.pages)}


def _load_docx(path: Path) -> tuple[str, dict]:
    """Word 解析：段落 + 表格按文档顺序抽取。"""
    import docx
    from docx.table import Table
    from docx.text.paragraph import Paragraph

    document = docx.Document(str(path))
    blocks: list[str] = []
    para_count = table_count = 0

    # 按文档流顺序遍历段落与表格
    for child in document.element.body.iterchildren():
        if child.tag.endswith("}p"):
            para = Paragraph(child, document)
            text = para.text.strip()
            if text:
                blocks.append(text)
                para_count += 1
        elif child.tag.endswith("}tbl"):
            table = Table(child, document)
            rows = []
            for row in table.rows:
                cells = [c.text.strip().replace("\n", " ") for c in row.cells]
                if any(cells):
                    rows.append(" | ".join(cells))
            if rows:
                blocks.append("\n".join(rows))
                table_count += 1

    return "\n\n".join(blocks), {"paragraphs": para_count, "tables": table_count}


def _load_text(path: Path) -> tuple[str, dict]:
    """文本/Markdown：优先 UTF-8，失败回退 GBK（兼容 Windows 中文文档）。"""
    data = path.read_bytes()
    for encoding in ("utf-8", "utf-8-sig", "gbk", "gb18030"):
        try:
            text = data.decode(encoding)
            return text.strip(), {"encoding": encoding}
        except (UnicodeDecodeError, UnicodeError):
            continue
    text = data.decode("utf-8", errors="ignore").strip()
    return text, {"encoding": "utf-8 (ignore errors)"}


def save_parsed(text: str, doc_id: str) -> Path:
    """把解析后的纯文本落盘，便于人工检查解析质量。"""
    path = settings.PARSED_DIR / f"{doc_id}.txt"
    path.write_text(text, encoding="utf-8")
    return path
