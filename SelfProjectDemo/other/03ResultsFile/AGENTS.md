# AI 智行助手：项目协作约定

本文件适用于 `SelfProjectDemo/other/03ResultsFile/` 及其子目录。以下相对路径均以该目录为项目根目录。修改前同时检查上级目录和目标子目录是否有适用的指令；用户当前任务决定本次工作范围。

## 项目与事实依据

这是基于 FastAPI、原生 HTML/CSS/JavaScript、OpenAI 兼容接口和高德 MCP over SSE 的智能出行演示项目。

- 旅游模式：收集出行需求，流式生成 Markdown 行程，支持复制和下载；配置高德后可尝试查询目的地天气，开启参考开关后可附带 12306 车票与酒店。
- 车票查询：通过 12306 MCP 查询车次、余票与票价。
- 酒店查询：优先酒店 MCP，失败时回退到已配置的高德 POI 搜索。
- 日常聊天：流式回复；配置 MCP 后，通过模型的 function calling 调用地图、车票或酒店工具，并显示调用参数及返回内容。
- 配置面板：保存 LLM、高德、12306、酒店配置，分别提供连接测试。
- 阅读顺序：先看 `README.md` 了解目标，再看 `docs/API_CONTRACT.md` 和任务涉及的实现。文档与代码不一致时说明差异，不把未实现功能当作已有能力。
- 当前目录没有 `run.py`、`requirements.txt`、`pyproject.toml`、`package.json` 或自动化测试套件。README 中的部分启动说明尚未与目录同步；不要声称这些文件或测试已存在，也不要直接套用同级项目的环境。

## 代码导航

| 路径 | 职责 |
| --- | --- |
| `backend/main.py` | FastAPI 应用、请求模型、JSON/SSE 响应、行程生成、聊天工具循环及静态资源托管 |
| `backend/config_store.py` | 配置默认结构、读取、字段合并及原子写入 |
| `backend/mcp_client.py` | 通用 MCP over SSE 会话、工具 schema 读取、结果文本提取及 OpenAI 工具转换 |
| `backend/amap_mcp.py` | 高德认证 URL 与会话适配层 |
| `backend/ticket_service.py` | 12306 车票查询、文本解析与摘要 |
| `backend/hotel_service.py` | 酒店 MCP 查询、参数映射与高德 POI 回退 |
| `frontend/index.html` | 中文界面、DOM 标识及脚本加载顺序 |
| `frontend/static/css/style.css` | 色彩变量、深色渐变主题、布局及交互状态 |
| `frontend/static/js/api.js` | 同源 JSON 请求、POST SSE 读取及事件分发 |
| `frontend/static/js/config.js` | 配置回填、保存和连接测试 |
| `frontend/static/js/travel.js` | 行程表单、流式展示、Markdown 复制及下载 |
| `frontend/static/js/chat.js` | 内存会话历史、聊天流及工具调用卡片 |
| `frontend/static/js/ticket.js` | 车票查询表单与结果表格 |
| `frontend/static/js/hotel.js` | 酒店查询表单与结果列表 |
| `frontend/static/js/markdown.js` | 轻量 Markdown 渲染及 HTML 转义 |
| `frontend/static/js/app.js` | 模式切换、Toast 及各模块初始化 |
| `docs/API_CONTRACT.md` | 前后端接口及事件契约 |

## 修改约定

- 优先沿用现有模块完成任务，保持演示项目的简单结构。新增框架、数据库、构建链或大型依赖应有任务需求支撑。
- 后端沿用异步 FastAPI、Pydantic 请求模型和现有响应辅助函数；网络与 MCP 操作保持异步，正确关闭会话资源。
- 前端沿用 IIFE 模块及 `window` 上的现有接口，不擅自改成需要打包的模块系统。修改 HTML 的 ID、类名或脚本接口时同步检查所有引用。
- 保持脚本顺序：`markdown.js` → `api.js` → `config.js` → `travel.js` → `chat.js` → `ticket.js` → `hotel.js` → `app.js`。
- 样式优先复用 CSS 变量和已有组件；保持中文界面、双模式切换、加载状态、错误反馈及键盘操作可用。
- 用户文本和工具结果优先通过 `textContent` 显示；Markdown 统一走 `MiniMarkdown`。调整渲染器时检查转义和链接协议，避免直接把不可信字符串插入 HTML。

## 接口与流式处理

- 现有业务 JSON 响应采用 `{ "success": true, "data": ..., "error": null }` 或对应失败结构。修改时保留前端对 `success` 的判断。
- 保留 `/api/config` 的 GET/POST、`/api/test/llm`、`/api/test/amap`、`/api/test/ticket`、`/api/test/hotel`、`/api/ticket/query`、`/api/hotel/query`、`/api/travel/plan`、`/api/chat`，以及 `/`、`/static/*` 的职责。
- LLM 配置字段为 `base_url`、`api_key`、`model`；高德、12306、酒店配置字段均为 `sse_url`、`api_key`，分别位于 `amap`、`ticket`、`hotel` 中。
- 行程字段为 `origin`、`destination`、`days`、`people`、`interests`、`transport`、`extra`、`start_date`、`include_refs`；车票字段为 `date`、`from_station`、`to_station`、`train_flags`；酒店字段为 `city`、`keyword`、`checkin`、`checkout`；聊天请求使用 `messages`。改变契约时同步更新后端模型、前端调用、契约文档和相关验证。
- SSE 使用 `text/event-stream`，单个事件为 `data: <JSON>\n\n`。前端使用 `fetch` + `ReadableStream` 发送 POST 并读取数据，不能直接用只支持 GET 的 `EventSource` 替换。
- 行程事件为 `tool`、`content`、`done`、`error`；`content.delta` 是文本增量，`done.markdown` 是完整行程。
- 聊天事件为 `tool_call`、`tool_result`、`content`、`done`、`error`。工具名称、参数和实际返回内容需要在界面中可见。
- SSE 解析必须保留跨数据块的残片，并处理一个数据块含多个事件的情况。区分协议中的 `type=done` 与读取结束回调 `onDone`；出错或中断后恢复按钮状态，不覆盖错误提示或制造成功结果。

## 模型、MCP 与配置

- LLM 使用可配置的 OpenAI 兼容 `base_url` 和 `model`，不要在业务代码中固定服务商或真实密钥。
- 通用 MCP 会话与工具 schema 读取集中在 `mcp_client.py`；高德适配保留在 `amap_mcp.py`，12306 与酒店逻辑分别在 `ticket_service.py`、`hotel_service.py`。工具名称及参数以服务器返回的描述为依据，不虚构工具、车票、酒店或路线数据。
- 聊天工具名使用 `<server>__<tool>` 命名空间（如 `ticket__get-tickets`），按前缀路由到对应会话，避免不同 MCP 服务器的同名工具冲突。
- 保持流式工具调用片段的累计、assistant/tool 消息配对，以及多轮工具调用的有限上限；当前 `MAX_TOOL_ROUNDS` 为 5。
- 未配置任何 MCP 时保留普通聊天；旅游模式中的天气、车票、酒店查询都是可选增强，查询失败不应阻止 LLM 生成行程。酒店查询按“酒店 MCP → 高德 POI”顺序回退。
- `config.json` 位于项目根目录，当前不随目录提供；缺失或读取失败时返回默认结构，保存由配置面板触发。`ticket` / `hotel` 默认使用 `tips.txt` 中的演示 SSE 地址，可在面板覆盖或清空。保持 `config.json.tmp` 写入后替换目标文件的机制。
- 真实密钥、含密钥的 SSE URL、运行配置和缓存不得写入提交、日志、示例或回答。示例使用空值或明确的占位符，验证配置写入时使用临时位置，避免覆盖用户配置。
- 当前接口会回填密钥，CORS 为开发配置；本地启动使用回环地址。若任务涉及对外部署，需要同时处理鉴权、敏感字段返回和跨域策略，不能把演示默认值当作生产配置。

## 本地运行与检查

以下命令均在本项目根目录执行。

1. 先运行 `python --version`。按当前实现使用 Python 3.11 或更新版本，因为异常处理使用内置 `BaseExceptionGroup`；代码还使用 Pydantic v2 的 `model_dump()`。
2. 从源码可见的主要运行依赖为 `fastapi`、`uvicorn`、`pydantic`、`openai`、`mcp`。当前没有依赖锁定文件，搭建环境时核对实际版本；确需补充依赖文件时再创建，不宣称环境已可复现。
3. 在满足依赖的环境中启动服务：

   ```powershell
   python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
   ```

   然后访问 `http://127.0.0.1:8000`，通过配置面板设置服务参数。不要使用当前不存在的 `python run.py`。

修改 Python 后，可先做不导入业务模块的语法检查：

```powershell
python -c "import ast,pathlib; files=pathlib.Path('backend').rglob('*.py'); [ast.parse(p.read_text(encoding='utf-8-sig'), filename=str(p)) for p in files]; print('Python syntax OK')"
```

修改 JavaScript 后，在有 Node.js 的环境中检查语法；Node.js 仅用于此检查，不是前端运行时依赖：

```powershell
Get-ChildItem ./frontend/static/js/*.js | ForEach-Object {
    node --check $_.FullName
    if ($LASTEXITCODE -ne 0) { throw "JavaScript syntax check failed: $($_.Name)" }
}
```

- 语法检查不等于功能测试。根据改动验证页面和静态资源、配置读写、行程增量与下载、聊天历史和工具卡片，以及失败后的界面恢复。
- 涉及协议或业务逻辑时，优先补充针对变更的测试：模拟 LLM/MCP，覆盖 SSE 分块、缺少配置、外部服务失败和工具调用边界；当前没有可直接运行的现成测试命令。
- 纯文档或低影响样式修改做对应核对即可，不为形式添加测试。真实 LLM/MCP 联调使用用户已授权的服务配置，不把离线模拟或静态检查表述为线上调用通过。
- 环境或凭据不足时继续完成可执行的检查，并在交付中说明未验证项。

## 工作范围与交付

- 默认用中文沟通，保留代码中的 API 名称和标识符。开始先明确任务涉及的文件，完成后简要说明修改、验证结果和必要限制。
- 仓库内有多个独立演示项目。除非任务涉及它们，不修改、搬移或合并同级目录；不要复制其他项目的真实配置。
- 修改前查看 `git status`，保留用户已有改动。提交时逐项核对范围，不用整个仓库的批量暂存把其他项目带入提交。
- Git 提交、推送、发布及是否包含 Markdown/提示词文件，按当前任务的明确要求执行；编写本文件本身不授权执行这些操作。
- 项目结构、接口或运行方式变化后同步更新相关文档。本文件维护共享约定，`CLAUDE.md` 通过导入复用它，避免维护两份相互冲突的规则。
