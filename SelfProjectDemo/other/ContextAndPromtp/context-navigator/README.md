# Context Navigator（上下文领航员）

一个用于演示和实验大模型 **上下文（Context）管理** 的全栈小系统：

- **KV Cache 命中/未命中** 可视化（⚡ CACHE 绿标 / 🔄 RECALC 橙标）
- **上下文窗口溢出** 与三种处理策略（删除历史 / 摘要压缩 / 智能裁剪）
- **Context 结构透明化**：System Prompt、对话历史、RAG 检索、工具调用分区块展示
- **演示模式**：三阶段分步脚本，完全离线可跑
- **聊天模式**：真实接入 GLM-5.3-Flash（硅基流动）、Qwen3-Embedding-4B RAG（LangChain + FAISS）、高德地图 MCP（SSE）

## 快速开始

```bash
cd context-navigator
pip install -r requirements.txt
python -m uvicorn app.main:app --port 8765
```

或直接双击 `run.bat`。

打开浏览器访问 <http://localhost:8765>

> **最小依赖**：只装 `fastapi uvicorn openai requests` 也能运行——演示模式完全离线；
> 聊天模式可用（RAG 自动降级为本地关键词检索）；MCP 工具调用需要额外 `pip install mcp`；
> 向量检索需要 `langchain langchain-community langchain-openai faiss-cpu`。

## 目录结构

```
context-navigator/
├── app/
│   ├── main.py          # FastAPI 路由与入口
│   ├── state.py         # 核心：上下文条目 / Cache 签名 / 窗口策略
│   ├── demo.py          # 三阶段演示脚本
│   ├── llm.py           # 硅基流动 LLM 调用（OpenAI 兼容）
│   ├── rag.py           # LangChain + FAISS 知识库（含本地降级）
│   ├── mcp_client.py    # 高德地图 MCP SSE 客户端
│   ├── token_counter.py # 本地启发式 Token 估算
│   └── config.py        # 设置持久化（data/settings.json）
├── static/              # 原生 HTML/CSS/JS 前端（Material Design 风格）
├── data/
│   ├── knowledge/       # RAG 知识库文档（.md，可自行增删）
│   └── settings.json    # 运行时生成的设置（含 API Key，勿提交）
└── requirements.txt
```

## 使用说明

### 演示模式（默认）

点击顶部「下一步」逐步推进，共三阶段：

1. **基础缓存能力**：第一轮 Cache Miss，第二轮命中并召回你的名字
2. **窗口溢出处理**：长文本填充 → 绿→橙→红→100% 弹窗 → 依次体验三种策略（每步自动恢复溢出快照，方便对比）
3. **Context 透明化**：提问产品价格触发 RAG 注入；询问北京天气触发 `get_weather` 工具调用

绿色字体的上下文条目 = 已被 KV Cache 复用的前缀。

### 聊天模式

顶部切换到「聊天模式」，直接对话。系统会：

- 自动做 RAG 检索并注入相关知识（右侧 🔍 面板可见）
- 模型需要时自动调用 MCP 工具（右侧 🛠️ 面板可见，默认接入高德地图）
- 窗口占用 80% 变橙、95% 变红闪烁、100% 弹出策略选择框

### 设置

右上角「设置」可配置：

- 大模型 Base URL / API Key / 模型名 / Temperature（含「获取模型列表」与「测试连接」）
- Embedding 模型（默认 `Qwen/Qwen3-Embedding-4B`）
- MCP 服务地址（默认高德地图 SSE）与测试连接
- RAG 开关 / top_k / 上下文窗口大小（默认 2048）

知识库文档放在 `data/knowledge/*.md`，增删后点「重建知识库索引」。

## Cache 判定原理

后端对每轮请求前的完整上下文前缀计算签名（SHA-1）：

- 与上一轮计算过的签名一致 → **Cache Hit**，旧前缀全部复用（绿色），只计算新增部分
- 签名变化（首轮 / 策略执行后 / System 修改 / 设置变更）→ **Cache Miss**，全部重算

这模拟了真实推理引擎的 **前缀 KV Cache** 行为。

## 注意

- `data/settings.json` 包含 API Key，已被 `.gitignore` 排除，请勿提交到公开仓库
- Token 为本地启发式估算（中文 ≈1 token/字，英文 ≈4 字符/token），演示够用
- 高德 MCP 走 modelscope 托管的 SSE 地址，若失效可在设置中更换
