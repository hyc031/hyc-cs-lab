"""本地知识库 RAG 系统 — Streamlit 入口。

运行方式：conda activate dt && streamlit run app.py

功能对应 prompt.txt：
- 文档上传（PDF / Word / TXT / Markdown）与自动解析
- 固定长度分块（可视化分块模式与分块示例）
- 智能问答（LLM 自动判断是否调用知识库）
- 引用来源（文档名 + 分块序号 + 相似度 + 字符区间 + 原文）
- 多轮对话（历史保留 + 检索前查询改写）
"""
import hashlib
import time
from types import SimpleNamespace

import streamlit as st

from core.config import settings
from core.document_loader import load_document, save_parsed
from core.embedder import SiliconFlowEmbedder
from core.rag_engine import RAGEngine
from core.splitter import CHUNK_MODES, split_document
from core.vector_store import FaissVectorStore
from ui.styles import CUSTOM_CSS, render_citation, render_header

st.set_page_config(
    page_title="RAG系统案例",
    page_icon="📚",
    layout="wide",
    initial_sidebar_state="expanded",
)
st.markdown(CUSTOM_CSS, unsafe_allow_html=True)


# --------------------------------------------------------------------------- #
# 会话状态与引擎初始化
# --------------------------------------------------------------------------- #
@st.cache_resource(show_spinner=False)
def get_engine() -> RAGEngine:
    return RAGEngine(
        embedder=SiliconFlowEmbedder(),
        store=FaissVectorStore(),
    )


def init_state() -> None:
    if "messages" not in st.session_state:
        st.session_state.messages = []  # 多轮对话历史
    if "last_result" not in st.session_state:
        st.session_state.last_result = None  # 最近一次问答结果（含引用）


def history_for_llm() -> list[dict]:
    """把界面消息转成 OpenAI 格式的历史（不含引用等附加信息）。"""
    return [
        {"role": m["role"], "content": m["content"]}
        for m in st.session_state.messages
        if m["role"] in ("user", "assistant")
    ]


def find_question(messages: list[dict], assistant_message: dict) -> str:
    """找到某条助手回答对应的问题文本。"""
    idx = messages.index(assistant_message)
    for m in reversed(messages[:idx]):
        if m["role"] == "user":
            text = m["content"]
            return text[:60] + ("…" if len(text) > 60 else "")
    return "（未知问题）"


def ingest_files(files, chunk_size: int, chunk_overlap: int) -> None:
    """解析 → 分块 → 向量化 → 入库。files 为 [(文件名, 字节内容)] 列表。"""
    embedder = engine.embedder
    progress = st.progress(0.0, text="开始处理…")
    total = len(files)

    for i, (name, data) in enumerate(files):
        try:
            save_path = settings.UPLOAD_DIR / f"{int(time.time())}_{name}"
            save_path.write_bytes(data)

            progress.progress(i / total, text=f"📄 正在解析：{name}")
            text, meta = load_document(save_path)
            if not text.strip():
                st.warning(f"⚠️《{name}》未解析到任何文本内容，请检查文件。")
                continue
            doc_id = hashlib.md5(f"{name}:{time.time()}".encode()).hexdigest()[:10]
            save_parsed(text, doc_id)

            progress.progress((i + 0.3) / total, text=f"✂️ 正在分块：{name}")
            chunks = split_document(text, chunk_size, chunk_overlap)

            # 分块示例：展示前 2 个分块（本地知识库界面要求）
            with st.expander(f"👀 分块示例：{name}（共 {len(chunks)} 块，展示前 2 块）", expanded=True):
                for c in chunks[:2]:
                    st.markdown(
                        f'<div class="chunk-meta">分块 #{c["chunk_index"]} '
                        f'｜字符区间 {c["start"]}-{c["end"]}｜{len(c["text"])} 字符</div>'
                        f'<div class="chunk-example">{c["text"]}</div>',
                        unsafe_allow_html=True,
                    )

            progress.progress((i + 0.6) / total, text=f"🔢 正在向量化：{name}")
            vectors = embedder.embed([c["text"] for c in chunks])
            engine.store.add(doc_id, name, chunks, vectors)
            st.success(f"✅《{name}》入库完成：{len(chunks)} 个分块（解析元信息：{meta}）")
        except Exception as exc:  # noqa: BLE001
            st.error(f"❌ 处理《{name}》失败：{exc}")

    progress.progress(1.0, text="全部完成")
    time.sleep(0.5)
    progress.empty()


init_state()

if not settings.API_KEY:
    st.error(
        "未检测到 API Key：请在项目根目录创建 `.env` 文件，"
        "写入 `SILICONFLOW_API_KEY=sk-xxx` 后重启应用。"
    )
    st.stop()

engine = get_engine()


# --------------------------------------------------------------------------- #
# 侧边栏导航
# --------------------------------------------------------------------------- #
with st.sidebar:
    st.markdown("### 📖 导航")
    page = st.radio(
        "选择页面",
        ["🏠 首页", "📚 本地知识库", "💬 智能问答", "🔍 引用来源"],
        label_visibility="collapsed",
    )
    st.divider()
    st.markdown("### ⚙️ 检索参数")
    top_k = st.slider("Top-K 检索条数", 1, 10, settings.TOP_K)
    score_threshold = st.slider(
        "相似度阈值", 0.0, 1.0, float(settings.SCORE_THRESHOLD), 0.05
    )
    temperature = st.slider("回答随机性 Temperature", 0.0, 1.0, 0.3, 0.1)
    thinking = st.toggle("GLM 深度思考模式", value=False, help="开启后回答更深入但更慢")
    st.divider()
    stats = engine.store.stats()
    st.markdown(
        f"**索引状态**：{stats['total_docs']} 个文档 / {stats['total_chunks']} 个分块"
        + (f"｜向量维度 {stats['dimensions']}" if stats["dimensions"] else "")
    )
    if st.button("🗑️ 清空对话", use_container_width=True):
        st.session_state.messages = []
        st.session_state.last_result = None
        st.rerun()


# --------------------------------------------------------------------------- #
# 首页
# --------------------------------------------------------------------------- #
if page == "🏠 首页":
    render_header("RAG系统案例", "上传文档 → 自动解析分块 → 向量化入库 → 智能问答（带引用来源）")

    col1, col2 = st.columns(2)
    with col1:
        st.markdown(
            '<div class="kb-card"><h4>📚 本地知识库</h4>'
            "<p>上传 PDF / Word / TXT / Markdown 文档，选择固定长度分块参数，"
            "实时查看分块模式说明与分块示例，一键向量化入库。</p></div>",
            unsafe_allow_html=True,
        )
        st.markdown(
            '<div class="kb-card"><h4>💬 智能问答</h4>'
            "<p>系统先由 GLM-5.3-Flash 判断问题是否需要知识库：需要则检索并引用资料回答，"
            "不需要则直接对话。支持多轮上下文。</p></div>",
            unsafe_allow_html=True,
        )
    with col2:
        st.markdown(
            '<div class="kb-card"><h4>🔍 引用来源</h4>'
            "<p>每次基于知识库的回答都附带引用：文档名、分块序号、相似度、"
            "字符区间与原文段落，点击即可核对。</p></div>",
            unsafe_allow_html=True,
        )
        st.markdown(
            '<div class="kb-card"><h4>🛠 技术栈</h4>'
            "<p>Streamlit + LangChain 分块 + FAISS 向量检索 + "
            "Qwen3-Embedding-4B（嵌入）+ GLM-5.3-Flash（对话），全部运行在本地。</p></div>",
            unsafe_allow_html=True,
        )

    st.divider()
    st.markdown(
        "**快速开始**：① 左侧进入「📚 本地知识库」上传文档并入库 → "
        "② 进入「💬 智能问答」提问，例如 *“公司的使命是什么？”* → "
        "③ 在回答下方或「🔍 引用来源」页核对引用段落。"
    )
    if not stats["total_docs"]:
        st.info("💡 知识库还是空的，先去「本地知识库」上传文档吧（也可一键导入内置的品牌手册演示文档）。")


# --------------------------------------------------------------------------- #
# 本地知识库
# --------------------------------------------------------------------------- #
elif page == "📚 本地知识库":
    render_header("本地知识库", "文档上传 · 解析 · 固定长度分块 · 向量化入库")

    tab_upload, tab_docs = st.tabs(["📤 文档上传与分块", "🗂 已入库文档"])

    with tab_upload:
        # 一键导入品牌手册演示文档
        demo_file = settings.UPLOAD_DIR.parent / "演示文档" / "主流大模型（LLM）介绍.docx"
        if demo_file.exists():
            if st.button("📘 一键导入内置演示文档：主流大模型（LLM）介绍.docx"):
                ingest_files(
                    [(demo_file.name, demo_file.read_bytes())],
                    settings.CHUNK_SIZE,
                    settings.CHUNK_OVERLAP,
                )
                st.rerun()

        st.markdown("#### 分块模式")
        mode_name = list(CHUNK_MODES)[0]
        st.info(f"**{mode_name}**：{CHUNK_MODES[mode_name]}")

        col_a, col_b = st.columns(2)
        with col_a:
            chunk_size = st.number_input("分块大小（字符数）", 100, 2000, settings.CHUNK_SIZE, 50)
        with col_b:
            max_overlap = max(0, int(chunk_size) - 1)
            default_overlap = min(settings.CHUNK_OVERLAP, max_overlap)
            chunk_overlap = st.number_input("重叠字符数", 0, max_overlap, default_overlap, 10)
        if chunk_overlap >= chunk_size:
            st.warning("重叠字符数必须小于分块大小。")
            chunk_overlap = max(0, int(chunk_size * 0.6))

        uploaded_files = st.file_uploader(
            "支持 PDF、Word(.docx)、TXT、Markdown，可多选",
            type=["pdf", "docx", "txt", "md", "markdown"],
            accept_multiple_files=True,
        )

        if uploaded_files and st.button("🚀 解析并入库", type="primary", use_container_width=True):
            ingest_files(
                [(f.name, f.getvalue()) for f in uploaded_files],
                int(chunk_size),
                int(chunk_overlap),
            )
            st.rerun()

    with tab_docs:
        stats = engine.store.stats()
        if not stats["documents"]:
            st.info("暂无已入库文档。")
        for doc_name, info in stats["documents"].items():
            c1, c2, c3 = st.columns([6, 2, 1])
            c1.markdown(
                f'<div class="kb-card"><h4>📄 {doc_name}</h4>'
                f"<p>{info['chunks']} 个分块 ｜ {info['chars']} 字符</p></div>",
                unsafe_allow_html=True,
            )
            if c3.button("删除", key=f"del_{info['doc_id']}"):
                removed = engine.store.delete_document(info["doc_id"])
                st.toast(f"已删除 {removed} 个分块")
                st.rerun()


# --------------------------------------------------------------------------- #
# 智能问答（多轮对话）
# --------------------------------------------------------------------------- #
elif page == "💬 智能问答":
    render_header("智能问答", "自动判断是否调用知识库 · 回答附带引用来源 · 支持多轮对话")

    auto_route = st.toggle(
        "自动判断是否调用知识库",
        value=True,
        help="开启后由 GLM 判断当前问题是否需要检索；关闭后每次都检索知识库",
    )

    for message in st.session_state.messages:
        with st.chat_message(message["role"], avatar="🧑" if message["role"] == "user" else "🤖"):
            if message["role"] == "assistant":
                badge = (
                    '<span class="badge badge-kb">已调用知识库</span>'
                    if message.get("used_kb")
                    else '<span class="badge badge-direct">直接回答</span>'
                )
                st.markdown(badge, unsafe_allow_html=True)
                st.markdown(message["content"])
                if message.get("citations"):
                    with st.expander(f"📎 引用来源（{len(message['citations'])} 条）"):
                        for c in message["citations"]:
                            render_citation(SimpleNamespace(**c))
            else:
                st.markdown(message["content"])

    question = st.chat_input("向知识库提问，例如：公司的核心价值观是什么？")
    if question:
        st.session_state.messages.append({"role": "user", "content": question})
        with st.chat_message("user", avatar="🧑"):
            st.markdown(question)

        with st.chat_message("assistant", avatar="🤖"):
            with st.spinner("正在检索知识库并生成回答…"):
                try:
                    result = engine.answer(
                        question=question,
                        history=history_for_llm()[:-1],  # 去掉刚追加的当前问题
                        top_k=int(top_k),
                        score_threshold=float(score_threshold),
                        use_kb=False if not auto_route else None,
                        temperature=float(temperature),
                        thinking="enabled" if thinking else "disabled",
                    )
                except Exception as exc:  # noqa: BLE001
                    st.error(f"回答失败：{exc}")
                    result = None

            if result is not None:
                badge = (
                    '<span class="badge badge-kb">已调用知识库</span>'
                    if result.used_kb
                    else '<span class="badge badge-direct">直接回答（无需知识库）</span>'
                )
                st.markdown(badge, unsafe_allow_html=True)
                if result.route_reason:
                    st.caption(f"路由判断：{result.route_reason}")
                if result.rewritten_query and result.rewritten_query != question:
                    st.caption(f"查询改写：{result.rewritten_query}")
                st.markdown(result.answer)

                if result.citations:
                    with st.expander(f"📎 引用来源（{len(result.citations)} 条）", expanded=True):
                        for c in result.citations:
                            render_citation(c)

                st.session_state.messages.append(
                    {
                        "role": "assistant",
                        "content": result.answer,
                        "used_kb": result.used_kb,
                        "route_reason": result.route_reason,
                        "citations": [c.to_dict() for c in result.citations],
                    }
                )
                st.session_state.last_result = result


# --------------------------------------------------------------------------- #
# 引用来源
# --------------------------------------------------------------------------- #
elif page == "🔍 引用来源":
    render_header("引用来源", "核对回答引用的段落 · 浏览知识库全部分块")

    tab_recent, tab_browse = st.tabs(["📎 最近回答的引用", "🗂 知识库分块浏览"])

    with tab_recent:
        assistant_msgs = [
            m for m in st.session_state.messages
            if m["role"] == "assistant" and m.get("citations")
        ]
        if not assistant_msgs:
            st.info("还没有产生带引用的回答，去「智能问答」提个问题吧。")
        for i, m in enumerate(reversed(assistant_msgs), start=1):
            question_text = find_question(st.session_state.messages, m)
            with st.expander(f"💬 问题：{question_text}", expanded=(i == 1)):
                st.markdown(f"**回答**：{m['content'][:500]}")
                st.markdown("**引用段落**：")
                for c in m["citations"]:
                    render_citation(SimpleNamespace(**c))

    with tab_browse:
        stats = engine.store.stats()
        if not stats["documents"]:
            st.info("知识库为空，请先在「本地知识库」上传文档。")
        else:
            selected = st.selectbox("选择文档", list(stats["documents"].keys()))
            doc_id = stats["documents"][selected]["doc_id"]
            chunks = engine.store.get_chunks(doc_id)
            page_size = 5
            total_pages = max(1, (len(chunks) + page_size - 1) // page_size)
            page_no = st.number_input("页码", 1, total_pages, 1)
            start = (page_no - 1) * page_size
            for c in chunks[start : start + page_size]:
                st.markdown(
                    f'<div class="citation-block"><div class="src">分块 #{c["chunk_index"]}'
                    f'｜字符区间 {c["start"]}-{c["end"]}</div>'
                    f'<div class="body">{c["text"][:800]}</div></div>',
                    unsafe_allow_html=True,
                )
