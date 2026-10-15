# RAG 系统案例

基于 `prompt.txt` 需求开发的本地知识库问答系统：上传文档 → 自动解析分块 → 向量化入库（FAISS）→ 智能问答（带引用来源，支持多轮对话）。

## 技术栈

| 模块 | 技术 |
| --- | --- |
| 前端 + 后端 | Streamlit（全栈） |
| 文档解析 | pypdf（PDF）、python-docx（Word）、原生解码（TXT/Markdown） |
| 分块 | LangChain `RecursiveCharacterTextSplitter`（固定长度分块，中文分隔符优先） |
| 向量数据库 | FAISS（IndexFlatIP + 向量归一化 = 余弦相似度，持久化到本地） |
| 嵌入模型 | 硅基流动 `Qwen/Qwen3-Embedding-4B`（2560 维） |
| 对话模型 | 硅基流动 `zai-org/GLM-5.3-Flash`（支持开关深度思考） |

## 快速开始

```bash
conda activate dt
cd E:\GitCode\hyc-Note\SelfProjectDemo\other\RAG
streamlit run app.py
```

API Key 已配置在 `.env`（已加入 `.gitignore`，不会提交到 git）。

## 使用说明

1. **📚 本地知识库**：上传 PDF / Word / TXT / Markdown（可多选），调整分块大小与重叠字符数，
   点击"解析并入库"后可看到分块模式说明和分块示例；已入库文档可单个删除。
   也可一键导入内置演示文档《主流大模型（LLM）介绍.docx》。
2. **💬 智能问答**：输入问题后系统先由 GLM 判断是否需要知识库——需要则检索并以 `[1][2]` 标注引用，
   不需要则直接回答（可关闭"自动判断"强制检索）。多轮对话历史自动保留，检索前会做查询改写。
3. **🔍 引用来源**：查看每次回答引用的文档名、分块序号、相似度、字符区间与原文段落；也可按文档浏览全部分块。
4. **侧边栏参数**：Top-K、相似度阈值、Temperature、GLM 深度思考开关，以及索引状态统计。

## 目录结构

```
RAG/
├── app.py                  # Streamlit 主界面（首页/知识库/问答/引用来源）
├── core/
│   ├── config.py           # .env 配置与路径
│   ├── document_loader.py  # PDF/Word/TXT/MD 解析
│   ├── splitter.py         # 固定长度分块（LangChain）
│   ├── embedder.py         # Qwen3-Embedding-4B 嵌入封装
│   ├── vector_store.py     # FAISS 向量库（持久化/删除/统计）
│   ├── llm.py              # GLM-5.3-Flash 封装（含 JSON 路由解析）
│   └── rag_engine.py       # 路由 → 改写 → 检索 → 引用生成 编排
├── ui/styles.py            # 品牌风格 CSS
├── tests/e2e_test.py       # 无界面端到端测试
├── data/
│   ├── uploaded/           # 上传的原始文档
│   ├── parsed/             # 解析后的纯文本（人工核对解析质量）
│   ├── vectorstore/        # index.faiss + vectors.npy + chunks.json
│   └── 演示文档/            # 内置演示文档（主流大模型介绍，可用 scripts/make_demo_doc.py 重新生成）
└── .env                    # API Key（不入库）
```

## 端到端自测

```bash
conda activate dt
python tests/e2e_test.py
```
