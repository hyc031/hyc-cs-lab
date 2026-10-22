"""AI 智行助手 — FastAPI backend.

Implements the API contract in docs/API_CONTRACT.md:
  - GET/POST /api/config      config.json read/write
  - POST /api/test/llm        LLM connectivity test (openai AsyncOpenAI)
  - POST /api/test/amap       Amap MCP-over-SSE tool listing
  - POST /api/travel/plan     SSE streaming Markdown itinerary
  - POST /api/chat            SSE streaming chat with MCP function-calling
  - GET /                     serves frontend/index.html
  - /static/*                 serves frontend/static

All non-SSE responses use the { success, data, error } envelope. SSE
endpoints emit a `{"type":"error","message":...}` event on failure so the
frontend never hangs.
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, AsyncIterator, Dict, List, Optional

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from backend import amap_mcp, config_store

# --------------------------------------------------------------------------- #
# Paths & app setup
# --------------------------------------------------------------------------- #
PROJECT_ROOT = Path(__file__).resolve().parent.parent
FRONTEND_DIR = PROJECT_ROOT / "frontend"
STATIC_DIR = FRONTEND_DIR / "static"
INDEX_HTML = FRONTEND_DIR / "index.html"

MAX_TOOL_ROUNDS = 5

app = FastAPI(title="AI 智行助手 Backend", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount static assets. Create the directory if missing so boot never fails.
STATIC_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


# --------------------------------------------------------------------------- #
# Response helpers
# --------------------------------------------------------------------------- #
def ok(data: Any) -> JSONResponse:
    return JSONResponse({"success": True, "data": data, "error": None})


def fail(error: str, status_code: int = 200) -> JSONResponse:
    return JSONResponse(
        {"success": False, "data": None, "error": error}, status_code=status_code
    )


def describe_error(exc: BaseException) -> str:
    """Return a readable message, unwrapping ExceptionGroup (anyio/MCP TaskGroup).

    MCP over SSE runs inside an anyio TaskGroup, so failures surface as
    ``unhandled errors in a TaskGroup (1 sub-exception)`` which hides the real
    cause. Drill into the group to report the underlying error instead.
    """
    seen = 0
    while isinstance(exc, BaseExceptionGroup) and exc.exceptions and seen < 5:
        exc = exc.exceptions[0]
        seen += 1
    msg = str(exc).strip()
    return msg or exc.__class__.__name__


def sse_event(obj: Dict[str, Any]) -> str:
    return f"data: {json.dumps(obj, ensure_ascii=False)}\n\n"


# --------------------------------------------------------------------------- #
# Request models
# --------------------------------------------------------------------------- #
class LLMConfig(BaseModel):
    base_url: str = ""
    api_key: str = ""
    model: str = ""


class AmapConfig(BaseModel):
    sse_url: str = ""
    api_key: str = ""


class ConfigBody(BaseModel):
    llm: LLMConfig = LLMConfig()
    amap: AmapConfig = AmapConfig()


class LLMTestBody(BaseModel):
    base_url: str = ""
    api_key: str = ""
    model: str = ""


class AmapTestBody(BaseModel):
    sse_url: str = ""
    api_key: str = ""


class TravelPlanBody(BaseModel):
    origin: str = ""
    destination: str = ""
    days: int = 1
    people: int = 1
    interests: List[str] = []
    transport: str = ""
    extra: str = ""


class ChatMessage(BaseModel):
    role: str
    content: Optional[str] = ""


class ChatBody(BaseModel):
    messages: List[ChatMessage] = []


# --------------------------------------------------------------------------- #
# LLM client helper
# --------------------------------------------------------------------------- #
def _make_llm_client(base_url: str, api_key: str):
    """Construct an AsyncOpenAI client. Import lazily to keep boot resilient."""
    from openai import AsyncOpenAI

    return AsyncOpenAI(base_url=base_url or None, api_key=api_key or "sk-none")


def _llm_ready(cfg: Dict[str, Any]) -> Optional[str]:
    """Return an error string if the LLM config is incomplete, else None."""
    llm = cfg.get("llm", {})
    if not llm.get("api_key"):
        return "LLM 未配置：缺少 api_key，请先在设置中配置。"
    if not llm.get("model"):
        return "LLM 未配置：缺少 model，请先在设置中配置。"
    return None


def _amap_ready(cfg: Dict[str, Any]) -> bool:
    amap = cfg.get("amap", {})
    return bool(amap.get("sse_url") and amap.get("api_key"))


# --------------------------------------------------------------------------- #
# 1. Config endpoints
# --------------------------------------------------------------------------- #
@app.get("/api/config")
async def get_config() -> JSONResponse:
    try:
        return ok(config_store.load_config())
    except Exception as exc:  # noqa: BLE001 - never crash on config read
        return fail(f"读取配置失败：{exc}")


@app.post("/api/config")
async def post_config(body: ConfigBody) -> JSONResponse:
    try:
        config_store.save_config(body.model_dump())
        return ok({"saved": True})
    except Exception as exc:  # noqa: BLE001
        return fail(f"保存配置失败：{exc}")


# --------------------------------------------------------------------------- #
# 2. Connection tests
# --------------------------------------------------------------------------- #
@app.post("/api/test/llm")
async def test_llm(body: LLMTestBody) -> JSONResponse:
    if not body.api_key:
        return fail("缺少 api_key")
    if not body.model:
        return fail("缺少 model")
    try:
        client = _make_llm_client(body.base_url, body.api_key)
        start = time.perf_counter()
        resp = await client.chat.completions.create(
            model=body.model,
            messages=[{"role": "user", "content": "ping"}],
            max_tokens=5,
        )
        latency_ms = int((time.perf_counter() - start) * 1000)
        # Guard against gateways that return an HTML page (e.g. base_url
        # missing the /v1 suffix): a real completion must expose choices.
        if not getattr(resp, "choices", None):
            return fail(
                "LLM 返回了非预期内容（可能不是有效的 API 响应）。"
                "请确认 Base URL 是否需要以 /v1 结尾，例如 https://your-host/v1"
            )
        model_name = getattr(resp, "model", None) or body.model
        return ok(
            {
                "ok": True,
                "message": "连接成功",
                "model": model_name,
                "latency_ms": latency_ms,
            }
        )
    except Exception as exc:  # noqa: BLE001
        return fail(f"LLM 连接失败：{exc}")


@app.post("/api/test/amap")
async def test_amap(body: AmapTestBody) -> JSONResponse:
    if not body.sse_url:
        return fail("缺少 sse_url")
    if not body.api_key and "key=" not in body.sse_url:
        return fail("缺少 api_key")
    try:
        tools = await amap_mcp.list_amap_tools(body.sse_url, body.api_key)
        names = [t["name"] for t in tools]
        return ok(
            {
                "ok": True,
                "message": "连接成功",
                "tool_count": len(names),
                "tools": names,
            }
        )
    except Exception as exc:  # noqa: BLE001
        return fail(f"高德 MCP 连接失败：{describe_error(exc)}")


# --------------------------------------------------------------------------- #
# 3. Travel plan (SSE)
# --------------------------------------------------------------------------- #
def _build_travel_prompt(body: TravelPlanBody) -> str:
    interests = "、".join(body.interests) if body.interests else "不限"
    return (
        "你是一名专业的智能出行规划助手。请根据以下需求，生成一份详细、"
        "美观、可执行的 Markdown 格式旅行行程计划。\n\n"
        f"- 出发地：{body.origin}\n"
        f"- 目的地：{body.destination}\n"
        f"- 天数：{body.days} 天\n"
        f"- 人数：{body.people} 人\n"
        f"- 兴趣偏好：{interests}\n"
        f"- 出行方式：{body.transport or '不限'}\n"
        f"- 其他需求：{body.extra or '无'}\n\n"
        "要求：\n"
        "1. 使用 Markdown 标题、列表、emoji 让排版清晰美观。\n"
        "2. 按天（📅 第N天）拆分行程，每个时间点给出具体活动、地点、交通与建议。\n"
        "3. 结合兴趣偏好推荐景点、餐饮与体验。\n"
        "4. 如提供了天气信息，请在开头简要提示天气与出行建议。\n"
        "5. 只输出 Markdown 正文，不要额外解释。"
    )


async def _maybe_fetch_weather(
    cfg: Dict[str, Any], city: str
) -> Optional[Dict[str, Any]]:
    """Try to fetch weather for a city via Amap. Returns event dict or None."""
    if not city or not _amap_ready(cfg):
        return None
    amap = cfg["amap"]
    try:
        async with amap_mcp.amap_session(amap["sse_url"], amap["api_key"]) as session:
            result = await session.call_tool("maps_weather", {"city": city})
            text = amap_mcp.extract_text_from_result(result)
            return {
                "type": "tool",
                "tool": "maps_weather",
                "args": {"city": city},
                "result": text,
            }
    except Exception:  # noqa: BLE001 - weather is best-effort, never fatal
        return None


def _city_of(place: str) -> str:
    """Extract a coarse city token from a place string like '上海·陆家嘴'."""
    if not place:
        return ""
    for sep in ("·", "-", " ", "，", ","):
        if sep in place:
            return place.split(sep)[0].strip()
    return place.strip()


@app.post("/api/travel/plan")
async def travel_plan(body: TravelPlanBody) -> StreamingResponse:
    cfg = config_store.load_config()

    async def gen() -> AsyncIterator[str]:
        try:
            err = _llm_ready(cfg)
            if err:
                yield sse_event({"type": "error", "message": err})
                return

            # Best-effort weather lookup for the destination city.
            weather_text = ""
            weather_event = await _maybe_fetch_weather(
                cfg, _city_of(body.destination)
            )
            if weather_event is not None:
                weather_text = weather_event.get("result", "")
                yield sse_event(weather_event)

            prompt = _build_travel_prompt(body)
            if weather_text:
                prompt += f"\n\n[目的地天气参考]\n{weather_text}"

            llm = cfg["llm"]
            client = _make_llm_client(llm["base_url"], llm["api_key"])
            collected: List[str] = []

            stream = await client.chat.completions.create(
                model=llm["model"],
                messages=[
                    {
                        "role": "system",
                        "content": "你是专业的智能出行规划助手，输出规范的 Markdown。",
                    },
                    {"role": "user", "content": prompt},
                ],
                stream=True,
            )
            async for chunk in stream:
                if not chunk.choices:
                    continue
                delta = chunk.choices[0].delta
                piece = getattr(delta, "content", None)
                if piece:
                    collected.append(piece)
                    yield sse_event({"type": "content", "delta": piece})

            yield sse_event({"type": "done", "markdown": "".join(collected)})
        except Exception as exc:  # noqa: BLE001
            yield sse_event({"type": "error", "message": f"生成行程失败：{describe_error(exc)}"})

    return StreamingResponse(gen(), media_type="text/event-stream")


# --------------------------------------------------------------------------- #
# 4. Chat (SSE, function-calling)
# --------------------------------------------------------------------------- #
def _accumulate_tool_calls(
    acc: Dict[int, Dict[str, Any]], delta_tool_calls: Any
) -> None:
    """Merge streamed tool_call deltas into an index-keyed accumulator."""
    for tc in delta_tool_calls:
        idx = getattr(tc, "index", 0) or 0
        slot = acc.setdefault(
            idx,
            {"id": None, "type": "function", "function": {"name": "", "arguments": ""}},
        )
        if getattr(tc, "id", None):
            slot["id"] = tc.id
        fn = getattr(tc, "function", None)
        if fn is not None:
            if getattr(fn, "name", None):
                slot["function"]["name"] += fn.name
            if getattr(fn, "arguments", None):
                slot["function"]["arguments"] += fn.arguments


@app.post("/api/chat")
async def chat(body: ChatBody) -> StreamingResponse:
    cfg = config_store.load_config()

    async def gen() -> AsyncIterator[str]:
        try:
            err = _llm_ready(cfg)
            if err:
                yield sse_event({"type": "error", "message": err})
                return

            llm = cfg["llm"]
            client = _make_llm_client(llm["base_url"], llm["api_key"])

            # Build conversation history.
            messages: List[Dict[str, Any]] = [
                {
                    "role": "system",
                    "content": (
                        "你是 AI 智行助手，可以借助高德地图工具查询天气、地点、"
                        "路线等信息，帮助用户解决日常出行相关问题。需要时请调用工具，"
                        "并结合工具返回的真实数据回答。"
                    ),
                }
            ]
            for m in body.messages:
                if m.role in ("user", "assistant") and m.content is not None:
                    messages.append({"role": m.role, "content": m.content})

            # If Amap not configured, run a plain (no-tool) chat.
            if not _amap_ready(cfg):
                async for out in _stream_plain_chat(client, llm["model"], messages):
                    yield out
                return

            amap = cfg["amap"]
            # Keep one MCP session open for the whole request.
            async with amap_mcp.amap_session(
                amap["sse_url"], amap["api_key"]
            ) as session:
                tools_resp = await session.list_tools()
                mcp_tools = [
                    {
                        "name": t.name,
                        "description": getattr(t, "description", "") or "",
                        "input_schema": getattr(t, "inputSchema", None) or {},
                    }
                    for t in tools_resp.tools
                ]
                openai_tools = amap_mcp.mcp_tools_to_openai(mcp_tools)

                for _round in range(MAX_TOOL_ROUNDS):
                    tool_acc: Dict[int, Dict[str, Any]] = {}
                    content_seen = False

                    stream = await client.chat.completions.create(
                        model=llm["model"],
                        messages=messages,
                        tools=openai_tools,
                        tool_choice="auto",
                        stream=True,
                    )
                    async for chunk in stream:
                        if not chunk.choices:
                            continue
                        delta = chunk.choices[0].delta
                        piece = getattr(delta, "content", None)
                        if piece:
                            content_seen = True
                            yield sse_event({"type": "content", "delta": piece})
                        dtc = getattr(delta, "tool_calls", None)
                        if dtc:
                            _accumulate_tool_calls(tool_acc, dtc)

                    # No tool calls this round -> assistant produced final answer.
                    if not tool_acc:
                        yield sse_event({"type": "done"})
                        return

                    # Record the assistant turn that requested the tools.
                    ordered = [tool_acc[i] for i in sorted(tool_acc.keys())]
                    messages.append(
                        {
                            "role": "assistant",
                            "content": None,
                            "tool_calls": [
                                {
                                    "id": tc["id"] or f"call_{i}",
                                    "type": "function",
                                    "function": {
                                        "name": tc["function"]["name"],
                                        "arguments": tc["function"]["arguments"] or "{}",
                                    },
                                }
                                for i, tc in enumerate(ordered)
                            ],
                        }
                    )

                    # Execute each requested tool and stream results.
                    for i, tc in enumerate(ordered):
                        name = tc["function"]["name"]
                        raw_args = tc["function"]["arguments"] or "{}"
                        try:
                            args = json.loads(raw_args) if raw_args.strip() else {}
                        except (ValueError, json.JSONDecodeError):
                            args = {}

                        yield sse_event(
                            {"type": "tool_call", "tool": name, "args": args}
                        )

                        try:
                            result = await session.call_tool(name, args)
                            text = amap_mcp.extract_text_from_result(result)
                        except Exception as tool_exc:  # noqa: BLE001
                            text = f"工具调用失败：{tool_exc}"

                        yield sse_event(
                            {"type": "tool_result", "tool": name, "result": text}
                        )
                        messages.append(
                            {
                                "role": "tool",
                                "tool_call_id": tc["id"] or f"call_{i}",
                                "content": text or "",
                            }
                        )
                    # Loop to let the LLM consume tool results.

                # Reached the round cap: produce a final plain answer.
                async for out in _stream_plain_chat(client, llm["model"], messages):
                    yield out
        except Exception as exc:  # noqa: BLE001
            yield sse_event({"type": "error", "message": f"对话失败：{describe_error(exc)}"})

    return StreamingResponse(gen(), media_type="text/event-stream")


async def _stream_plain_chat(
    client: Any, model: str, messages: List[Dict[str, Any]]
) -> AsyncIterator[str]:
    """Stream a plain (no-tool) completion, emitting content + done."""
    stream = await client.chat.completions.create(
        model=model, messages=messages, stream=True
    )
    async for chunk in stream:
        if not chunk.choices:
            continue
        piece = getattr(chunk.choices[0].delta, "content", None)
        if piece:
            yield sse_event({"type": "content", "delta": piece})
    yield sse_event({"type": "done"})


# --------------------------------------------------------------------------- #
# 5. Frontend serving
# --------------------------------------------------------------------------- #
_PLACEHOLDER_HTML = """<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8">
<title>AI 智行助手</title></head>
<body style="font-family:sans-serif;max-width:720px;margin:80px auto;padding:0 20px">
<h1>AI 智行助手</h1>
<p>后端已启动，但尚未找到前端页面 <code>frontend/index.html</code>。</p>
<p>请将前端文件放入 <code>frontend/</code> 目录后刷新本页。</p>
</body></html>"""


@app.get("/")
async def index() -> Any:
    if INDEX_HTML.exists():
        return FileResponse(str(INDEX_HTML))
    return HTMLResponse(_PLACEHOLDER_HTML)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("backend.main:app", host="0.0.0.0", port=8000, reload=False)
