# AI 智行助手 · 端云协同智能出行

AI + MCP 打造的智能出行演示项目：生成 Markdown 旅行行程、查询 12306 高铁票、查找酒店，并在日常聊天中自动调用高德地图 / 12306 / 酒店 MCP 工具。

## 技术架构

- 前端：HTML + CSS + 原生 JavaScript（IIFE 模块）
- 后端：FastAPI + SSE 流式
- AI：可配置的 OpenAI 兼容接口
- 工具：高德地图、12306、酒店推荐，均为 MCP over SSE

## 快速开始

```bash
pip install fastapi uvicorn pydantic openai mcp
python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
```

打开 <http://127.0.0.1:8000>，点击右上角 ⚙️ 配置：

1. **LLM**：Base URL、API Key、模型名，点「连接测试」。
2. **高德地图**：SSE 服务 URL、API Key，点「连接测试」。
3. **12306 车票**：SSE 服务 URL（可选 API Key）。
4. **酒店推荐**：SSE 服务 URL（可选 API Key）。
5. 保存配置。

`config.json` 由配置面板写入项目根目录，不要提交真实密钥。

## 功能

- **旅游模式**：填写出发地、目的地、日期、天数、人数、出行方式、兴趣偏好与额外需求，生成可下载的 Markdown 行程。开启「同时查询高铁票与酒店」后，会把真实车次与酒店作为参考注入提示词。
- **车票查询**：按出发城市、到达城市、日期和车型调用 12306 MCP，展示车次、时间、历时、余票与票价，并保留原始返回。
- **酒店查询**：按城市、偏好关键词、入住/离店日期查询酒店。优先使用酒店 MCP；不可用时自动回退到已配置的高德 POI 搜索。
- **日常聊天**：LLM 自动选择高德、12306 或酒店工具，界面展示工具名、来源、参数与真实返回内容。

## 接口

完整字段见 [`docs/API_CONTRACT.md`](docs/API_CONTRACT.md)。

- `GET/POST /api/config`
- `POST /api/test/llm`、`/api/test/amap`、`/api/test/ticket`、`/api/test/hotel`
- `POST /api/ticket/query`
- `POST /api/hotel/query`
- `POST /api/travel/plan`（SSE）
- `POST /api/chat`（SSE）

## 项目结构

```
backend/
  main.py             FastAPI 应用、请求模型、JSON/SSE 接口
  config_store.py     配置默认结构、读取、字段合并与原子写入
  mcp_client.py       通用 MCP over SSE 会话、工具 schema、结果提取
  amap_mcp.py         高德 MCP 适配层
  ticket_service.py   12306 车票查询与文本解析
  hotel_service.py    酒店 MCP 查询与高德 POI 回退
frontend/
  index.html          页面、DOM 标识与脚本顺序
  static/css/style.css
  static/js/          api / config / travel / chat / ticket / hotel / app
docs/API_CONTRACT.md  前后端接口契约
tips.txt              MCP 配置参考（不提交）
```

## 验证结果

本轮回归测试（Python 语法检查、后端导入、前端 JS 语法检查、HTML 结构检查、接口级联调与假 LLM/MCP 对话流测试）全部通过，无明显缺陷：

- Python 语法检查 ✅；后端导入 ✅（16 条路由）；前端 `node --check` ✅；HTML 未闭合/错误/重复 ID 均通过。
- 页面 `GET /`、新增静态资源、配置接口 ✅；`POST /api/ticket/query` 成功解析车次（如 G531 北京南→上海虹桥 06:08）✅。
- 酒店接口在未配置 Key 时按预期返回「酒店 MCP 的 POI 搜索失败：INVALID_USER_KEY」，回退链路行为正确 ✅。
- 假 LLM 聊天 SSE 事件顺序为 `[tool_call, tool_result, content, done]`，`tool_call.source` 正确标注来源 ✅；旅行计划事件为 `[tool, content, done]`，且提示词注入「[高铁票参考（12306）]」✅。

## 注意事项

- 魔搭托管 MCP 的 SSE 地址通常 **24 小时过期**，失效后需在配置面板更新。
- `tips.txt` 中的酒店地址缺少部署 ID，实际连接可能返回高德工具集；此时酒店查询会记录警告并回退到高德 POI 搜索。
- 当前仓库没有自动化测试套件；修改后可执行 Python 语法检查、`node --check` 和接口级联调。真实 LLM / MCP 联调使用用户后续填写的真实密钥，尚未在本轮完成。
- 当前未验证项：真实大模型 Key 下的完整聊天回复、真实酒店数据源的实际返回内容。
