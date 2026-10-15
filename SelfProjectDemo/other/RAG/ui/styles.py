"""全局样式：简洁、直观、用户友好的界面风格（品牌蓝主色调）"""

CUSTOM_CSS = """
<style>
    /* 品牌主色 */
    :root {
        --brand-blue: #1D4ED8;
        --brand-blue-light: #EFF6FF;
        --brand-gray: #64748B;
    }
    .stApp { background: #FFFFFF; }

    /* 顶部标题栏 */
    .brand-header {
        background: linear-gradient(90deg, #1D4ED8 0%, #3B82F6 100%);
        color: white;
        padding: 18px 24px;
        border-radius: 12px;
        margin-bottom: 12px;
    }
    .brand-header h1 { margin: 0; font-size: 26px; font-weight: 700; }
    .brand-header p { margin: 4px 0 0 0; font-size: 13px; opacity: .9; }

    /* 卡片 */
    .kb-card {
        border: 1px solid #E2E8F0;
        border-left: 4px solid #1D4ED8;
        border-radius: 8px;
        padding: 12px 16px;
        margin: 6px 0;
        background: #F8FAFC;
    }
    .kb-card h4 { margin: 0 0 4px 0; font-size: 15px; color: #0F172A; }
    .kb-card p  { margin: 0; font-size: 13px; color: #475569; }

    /* 引用来源块 */
    .citation-block {
        border: 1px solid #DBEAFE;
        border-radius: 8px;
        padding: 10px 14px;
        margin: 4px 0;
        background: var(--brand-blue-light);
        font-size: 13px;
    }
    .citation-block .src { font-weight: 600; color: #1D4ED8; }
    .citation-block .body { color: #1E293B; white-space: pre-wrap; }

    /* 路由徽章 */
    .badge {
        display: inline-block; padding: 2px 10px; border-radius: 999px;
        font-size: 12px; font-weight: 600; margin-right: 6px;
    }
    .badge-kb     { background: #DBEAFE; color: #1D4ED8; }
    .badge-direct { background: #F1F5F9; color: #475569; }

    /* 分块示例 */
    .chunk-example {
        font-family: Consolas, "Microsoft YaHei", monospace;
        font-size: 12px;
        background: #0F172A; color: #E2E8F0;
        border-radius: 8px; padding: 12px 14px; margin: 6px 0;
        white-space: pre-wrap; line-height: 1.6;
    }
    .chunk-meta { color: #94A3B8; font-size: 11px; margin-bottom: 4px; }
</style>
"""


def render_header(title: str, subtitle: str = "") -> None:
    import streamlit as st

    sub = f"<p>{subtitle}</p>" if subtitle else ""
    st.markdown(
        f'<div class="brand-header"><h1>{title}</h1>{sub}</div>',
        unsafe_allow_html=True,
    )


def render_citation(citation) -> None:
    """渲染一条引用来源。"""
    import streamlit as st

    st.markdown(
        f"""
        <div class="citation-block">
            <div class="src">[{citation.index}] {citation.doc_name}
                ｜分块 #{citation.chunk_index}｜相似度 {citation.score}
                ｜字符区间 {citation.start}-{citation.end}</div>
            <div class="body">{citation.text[:600]}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
