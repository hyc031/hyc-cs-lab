# AI 智行助手 — 前后端 API 契约

> 前端与后端都必须严格遵循本文件。任何字段名、类型、路径都不得擅自更改。
> 后端使用 FastAPI，端口 **8000**。前端为纯静态页面，由 FastAPI 直接托管在 `/`。

## 0. 总体约定

- 所有请求/响应均为 `application/json`（除 SSE 流式接口）。
- 所有响应统一结构：
  ```json
  { "success": true, "data": { ... }, "error": null }
  ```
  失败时：
  ```json
  { "success": false, "data": null, "error": "错误描述" }
  ```
- 后端读取项目根目录下的 `config.json` 作为运行配置（由 `/api/config` 写入）。
- CORS 全开（开发环境）。

## 1. 配置管理

### GET `/api/config`
获取当前保存的配置（敏感字段照常返回，供前端回填）。

响应 `data`:
```json
{
  "llm": {
    "base_url": "https://api.openai.com/v1",
    "api_key": "sk-xxx",
    "model": "gpt-4o"
  },
  "amap": {
    "sse_url": "https://mcp.amap.com/sse",
    "api_key": "高德key"
  },
  "ticket": {
    "sse_url": "https://mcp.api-inference.modelscope.net/<id>/sse",
    "api_key": ""
  },
  "hotel": {
    "sse_url": "https://mcp.api-inference.modelscope.net/<id>/sse",
    "api_key": ""
  }
}
```
- `ticket` 为 12306 MCP，`hotel` 为酒店推荐 MCP；两者都只有 `sse_url`、`api_key` 两个字段。
- 从未配置时，`llm` / `amap` 返回空字符串；`ticket` / `hotel` 返回 `tips.txt` 中的演示 SSE 地址，可在配置面板覆盖或清空。
- 魔搭托管的 SSE 地址通常 24 小时过期。

### POST `/api/config`
保存配置。请求体结构与上面 `data` 一致；四个配置节均可省略，省略的节保持现有值。
响应 `data`: `{ "saved": true }`

## 2. 连接测试

### POST `/api/test/llm`
请求体：
```json
{ "base_url": "...", "api_key": "...", "model": "..." }
```
后端用该配置向 LLM 发一条极简 chat 请求。
响应 `data`:
```json
{ "ok": true, "message": "连接成功", "model": "gpt-4o", "latency_ms": 320 }
```
失败时 `success=false`，`error` 为原因。

### POST `/api/test/amap`
请求体：
```json
{ "sse_url": "...", "api_key": "..." }
```
后端通过 MCP SSE 连接高德服务器并列出可用工具。
响应 `data`:
```json
{ "ok": true, "message": "连接成功", "tool_count": 12, "tools": ["maps_geo", "maps_weather", ...] }
```

### POST `/api/test/ticket`
请求体：
```json
{ "sse_url": "...", "api_key": "" }
```
连接 12306 MCP 并列出工具。响应结构同 `/api/test/amap`。

### POST `/api/test/hotel`
请求体：
```json
{ "sse_url": "...", "api_key": "" }
```
连接酒店 MCP 并列出工具。响应结构同 `/api/test/amap`。

## 3. 车票与酒店查询

### POST `/api/ticket/query`
请求体：
```json
{
  "date": "2026-10-25",
  "from_station": "北京",
  "to_station": "上海",
  "train_flags": "G"
}
```
- `date` 必须是 `yyyy-MM-dd`。
- `from_station` / `to_station` 接受中文城市名或 12306 车站码。
- `train_flags` 为 `G/D/Z/T/K/O/F/S` 的任意组合，空字符串表示不限。

响应 `data`:
```json
{
  "date": "2026-10-25",
  "from_station": "北京",
  "to_station": "上海",
  "train_flags": "G",
  "count": 2,
  "items": [
    {
      "train": "G531",
      "from_station": "北京南",
      "from_code": "VNP",
      "to_station": "上海虹桥",
      "to_code": "AOH",
      "depart": "06:08",
      "arrive": "12:04",
      "duration": "05:56",
      "seats": [
        { "name": "二等座", "status": "有票", "available": true, "price": 553.0 }
      ]
    }
  ],
  "raw": "12306 原始文本"
}
```
- `items` 解析失败时为空数组，前端仍展示 `raw`。
- 12306 返回错误文本时接口返回 `success=false`。

### POST `/api/hotel/query`
请求体：
```json
{
  "city": "上海",
  "keyword": "外滩",
  "checkin": "2026-10-25",
  "checkout": "2026-10-26"
}
```
`keyword` / `checkin` / `checkout` 均可省略。

响应 `data`:
```json
{
  "city": "上海",
  "keyword": "外滩",
  "checkin": "2026-10-25",
  "checkout": "2026-10-26",
  "nights": 1,
  "source": "amap",
  "source_tool": "maps_text_search",
  "count": 20,
  "items": [
    { "id": "...", "name": "全季大观上海外滩酒店", "address": "...", "typecode": "100105", "photo": "..." }
  ],
  "raw": "上游原始返回",
  "warnings": ["酒店 MCP 的 POI 搜索失败：Text Search failed: INVALID_USER_KEY"]
}
```
- 查询顺序：酒店 MCP 的酒店工具 → 酒店 MCP 的 `maps_text_search` → 已配置高德 MCP 的 `maps_text_search`。
- `source` 为 `hotel-mcp` 或 `amap`；`warnings` 记录被跳过的失败尝试。
- 两个 MCP 都未配置或全部失败时返回 `success=false`。

## 4. 旅游模式（生成 Markdown 计划）

### POST `/api/travel/plan`  （SSE 流式）
请求体：
```json
{
  "origin": "北京·中关村",
  "destination": "上海·陆家嘴",
  "days": 2,
  "people": 2,
  "interests": ["人文历史", "美食体验"],
  "transport": "新能源自驾",
  "extra": "需要中途充电、优先高速、避开拥堵",
  "start_date": "2026-10-25",
  "include_refs": true
}
```
- `interests` 可多选，取值范围：`人文历史 / 美食体验 / 自然风光 / 现代都市 / 休闲度假 / 文艺体验`。
- `start_date` 可选；提供时才会查询 12306 车票。
- `include_refs` 默认 `true`；开启时尽力查询高铁票与酒店并注入提示词，失败不影响行程生成。
- 后端调用 LLM（可结合高德天气、12306 车票、酒店参考）流式生成 Markdown 行程。

响应：`text/event-stream`，每个事件为一行 JSON：
```
data: {"type":"tool","tool":"maps_weather","args":{...},"result":"..."}
data: {"type":"tool","tool":"ticket__get-tickets","args":{...},"result":"..."}
data: {"type":"tool","tool":"hotel__maps_text_search","args":{...},"result":"..."}
data: {"type":"content","delta":"# 第1天..."}
data: {"type":"done","markdown":"完整markdown全文"}
data: {"type":"error","message":"..."}
```
- `type=tool`：调用了某个工具（车票/酒店查询为尽力而为，失败时不发送该事件）。
- `type=content`：Markdown 文本增量，前端逐步渲染。
- `type=done`：结束，附完整 markdown。

## 5. 日常聊天模式（带 MCP 工具调用）

### POST `/api/chat`  （SSE 流式）
请求体：
```json
{
  "messages": [
    { "role": "user", "content": "深圳今天天气怎么样？" }
  ]
}
```
`messages` 为完整历史（role: user/assistant）。后端把已配置的高德、12306、酒店 MCP 工具统一暴露给 LLM，允许多轮工具调用。

工具名使用 `<server>__<tool>` 命名空间，避免不同服务器同名工具冲突：
- `amap__maps_weather`
- `ticket__get-tickets`
- `hotel__maps_text_search`

响应：`text/event-stream`，事件格式同上：
```
data: {"type":"tool_call","tool":"ticket__get-tickets","source":"12306 车票","args":{"date":"2026-10-25","fromStation":"北京","toStation":"上海","trainFilterFlags":"G"}}
data: {"type":"tool_result","tool":"ticket__get-tickets","source":"12306 车票","result":"G531 ..."}
data: {"type":"content","delta":"北京到上海"}
data: {"type":"done"}
data: {"type":"error","message":"..."}
```
- `type=tool_call`：LLM 决定调用工具，`source` 为工具所属服务器，前端展示调用卡片。
- `type=tool_result`：工具返回内容，前端展示在聊天流中（**必须显示获取到的内容**）。
- `type=content`：助手回复文本增量。
- `type=done`：本轮结束。
- 某个 MCP 服务器连接失败时会被跳过，其余服务器仍可正常使用。

## 6. 静态资源

- `GET /` → 返回 `frontend/index.html`
- `GET /static/*` → 前端静态资源（css/js）

## 7. 前端 SSE 解析约定

前端用 `fetch` + `ReadableStream` 读取，按 `\n\n` 分割事件，去掉 `data: ` 前缀后 `JSON.parse`。
