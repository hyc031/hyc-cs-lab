"""AI 智行助手 — FastAPI backend.

Implements the API contract in docs/API_CONTRACT.md:
  - GET/POST /api/config      config.json read/write
  - POST /api/test/llm        LLM connectivity test (openai AsyncOpenAI)
  - POST /api/test/amap       Amap MCP-over-SSE tool listing
  - POST /api/test/ticket     12306 MCP-over-SSE tool listing
  - POST /api/test/hotel      hotel MCP-over-SSE tool listing
  - POST /api/ticket/query    12306 train ticket query
  - POST /api/hotel/query     hotel recommendation query
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
from contextlib import AsyncExitStack
from datetime import date as date_cls
from pathlib import Path
from typing import Any, AsyncIterator, Dict, List, Optional

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from backend import amap_mcp, config_store, hotel_service, mcp_client, ticket_service

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


class MCPServerConfig(BaseModel):
    sse_url: str = ""
    api_key: str = ""


class ConfigBody(BaseModel):
    # Optional so an older client that only knows llm/amap cannot wipe the
    # ticket/hotel defaults by sending an empty section.
    llm: Optional[LLMConfig] = None
    amap: Optional[MCPServerConfig] = None
    ticket: Optional[MCPServerConfig] = None
    hotel: Optional[MCPServerConfig] = None


class LLMTestBody(BaseModel):
    base_url: str = ""
    api_key: str = ""
    model: str = ""


class MCPTestBody(BaseModel):
    sse_url: str = ""
    api_key: str = ""


class TicketQueryBody(BaseModel):
    date: str = ""
    from_station: str = ""
    to_station: str = ""
    train_flags: str = ""


class HotelQueryBody(BaseModel):
    city: str = ""
    keyword: str = ""
    checkin: str = ""
    checkout: str = ""


class TravelPlanBody(BaseModel):
    origin: str = ""
    destination: str = ""
    days: int = 1
    people: int = 1
    interests: List[str] = []
    transport: str = ""
    extra: str = ""
    start_date: str = ""
    include_refs: bool = True


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


def _mcp_ready(section: Dict[str, Any]) -> bool:
    """MCP servers without an api_key (12306 / hotel) only need an SSE URL."""
    return bool((section or {}).get("sse_url"))


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
        config_store.save_config(body.model_dump(exclude_none=True))
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
async def test_amap(body: MCPTestBody) -> JSONResponse:
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


@app.post("/api/test/ticket")
async def test_ticket(body: MCPTestBody) -> JSONResponse:
    if not body.sse_url:
        return fail("缺少 sse_url")
    try:
        tools = await ticket_service.list_ticket_tools(body.sse_url, body.api_key)
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
        return fail(f"12306 MCP 连接失败：{describe_error(exc)}")


@app.post("/api/test/hotel")
async def test_hotel(body: MCPTestBody) -> JSONResponse:
    if not body.sse_url:
        return fail("缺少 sse_url")
    try:
        tools = await hotel_service.list_hotel_tools(body.sse_url, body.api_key)
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
        return fail(f"酒店 MCP 连接失败：{describe_error(exc)}")


# --------------------------------------------------------------------------- #
# 2b. Direct ticket / hotel queries
# --------------------------------------------------------------------------- #
@app.post("/api/ticket/query")
async def ticket_query(body: TicketQueryBody) -> JSONResponse:
    cfg = config_store.load_config()
    ticket = cfg.get("ticket") or {}
    if not _mcp_ready(ticket):
        return fail("12306 未配置：请先在设置中填写 SSE 服务 URL。")
    try:
        data = await ticket_service.query_tickets(
            ticket["sse_url"],
            ticket.get("api_key", ""),
            body.date,
            body.from_station,
            body.to_station,
            body.train_flags,
        )
        return ok(data)
    except ValueError as exc:
        return fail(str(exc))
    except Exception as exc:  # noqa: BLE001
        return fail(f"车票查询失败：{describe_error(exc)}")


@app.post("/api/hotel/query")
async def hotel_query(body: HotelQueryBody) -> JSONResponse:
    cfg = config_store.load_config()
    hotel = cfg.get("hotel") or {}
    amap = cfg.get("amap") or {}
    amap_ready = bool(amap.get("sse_url") and (amap.get("api_key") or "key=" in amap.get("sse_url", "")))
    if not _mcp_ready(hotel) and not amap_ready:
        return fail("酒店与高德 MCP 均未配置：请先在设置中填写 SSE 服务 URL。")
    try:
        data = await hotel_service.query_hotels(
            hotel,
            amap,
            body.city,
            body.keyword,
            body.checkin,
            body.checkout,
        )
        return ok(data)
    except ValueError as exc:
        return fail(str(exc))
    except Exception as exc:  # noqa: BLE001
        return fail(f"酒店查询失败：{describe_error(exc)}")


# --------------------------------------------------------------------------- #
# 3. Travel plan (SSE)
# --------------------------------------------------------------------------- #
def _build_travel_prompt(body: TravelPlanBody) -> str:
    interests = "、".join(body.interests) if body.interests else "不限"
    date_line = f"- 出发日期：{body.start_date}\n" if body.start_date else ""
    return (
        "你是一名专业的智能出行规划助手。请根据以下需求，生成一份详细、"
        "美观、可执行的 Markdown 格式旅行行程计划。\n\n"
        f"- 出发地：{body.origin}\n"
        f"- 目的地：{body.destination}\n"
        f"{date_line}"
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
        "5. 如提供了高铁票或酒店参考，请结合真实车次、时间与酒店名称安排交通和住宿，"
        "不要编造未提供的车次或酒店。\n"
        "6. 只输出 Markdown 正文，不要额外解释。"
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


async def _maybe_fetch_tickets(
    cfg: Dict[str, Any], body: TravelPlanBody
) -> Optional[Dict[str, Any]]:
    """Best-effort 12306 lookup for the travel prompt. Never fatal."""
    ticket = cfg.get("ticket") or {}
    if not body.start_date or not _mcp_ready(ticket):
        return None
    from_city = _city_of(body.origin)
    to_city = _city_of(body.destination)
    if not from_city or not to_city:
        return None
    try:
        data = await ticket_service.query_tickets(
            ticket["sse_url"],
            ticket.get("api_key", ""),
            body.start_date,
            from_city,
            to_city,
            "G",
        )
        text = ticket_service.summarize_tickets(data) or (data.get("raw") or "")
        if not text:
            return None
        return {
            "type": "tool",
            "tool": "ticket__get-tickets",
            "args": {
                "date": body.start_date,
                "fromStation": from_city,
                "toStation": to_city,
                "trainFilterFlags": "G",
            },
            "result": text,
        }
    except Exception:  # noqa: BLE001 - optional enrichment
        return None


async def _maybe_fetch_hotels(
    cfg: Dict[str, Any], body: TravelPlanBody
) -> Optional[Dict[str, Any]]:
    """Best-effort hotel lookup for the destination. Never fatal."""
    hotel = cfg.get("hotel") or {}
    amap = cfg.get("amap") or {}
    amap_ready = bool(
        amap.get("sse_url")
        and (amap.get("api_key") or "key=" in amap.get("sse_url", ""))
    )
    if not _mcp_ready(hotel) and not amap_ready:
        return None
    city = _city_of(body.destination)
    if not city:
        return None
    try:
        data = await hotel_service.query_hotels(
            hotel,
            amap,
            city,
            "酒店",
            body.start_date,
            "",
        )
        text = hotel_service.summarize_hotels(data) or (data.get("raw") or "")
        if not text:
            return None
        return {
            "type": "tool",
            "tool": "hotel__maps_text_search",
            "args": {"city": city, "keywords": "酒店", "source": data.get("source")},
            "result": text[:1500],
        }
    except Exception:  # noqa: BLE001 - optional enrichment
        return None


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

            # Optional ticket / hotel references (checked by default).
            ticket_text = ""
            hotel_text = ""
            if body.include_refs:
                ticket_event = await _maybe_fetch_tickets(cfg, body)
                if ticket_event is not None:
                    ticket_text = ticket_event.get("result", "")
                    yield sse_event(ticket_event)

                hotel_event = await _maybe_fetch_hotels(cfg, body)
                if hotel_event is not None:
                    hotel_text = hotel_event.get("result", "")
                    yield sse_event(hotel_event)

            prompt = _build_travel_prompt(body)
            if weather_text:
                prompt += f"\n\n[目的地天气参考]\n{weather_text}"
            if ticket_text:
                prompt += f"\n\n[高铁票参考（12306）]\n{ticket_text}"
            if hotel_text:
                prompt += f"\n\n[酒店参考]\n{hotel_text}"

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
                        "你是 AI 智行助手，可以借助工具查询高德地图（天气、地点、路线）、"
                        "12306 火车票和酒店推荐。今天是 "
                        f"{date_cls.today().isoformat()}。需要时请调用工具，"
                        "并结合工具返回的真实数据回答；不要编造车次、余票或酒店。"
                    ),
                }
            ]
            for m in body.messages:
                if m.role in ("user", "assistant") and m.content is not None:
                    messages.append({"role": m.role, "content": m.content})

            server_specs = [
                ("amap", "高德地图", cfg.get("amap") or {}),
                ("ticket", "12306 车票", cfg.get("ticket") or {}),
                ("hotel", "酒店推荐", cfg.get("hotel") or {}),
            ]

            openai_tools: List[Dict[str, Any]] = []
            # exposed tool name -> (server key, label, raw tool name, session)
            routes: Dict[str, Any] = {}

            # Keep one session per configured MCP server for the whole request.
            # A server that fails to connect is skipped; the others still work.
            async with AsyncExitStack() as stack:
                for key, label, section in server_specs:
                    if not _mcp_ready(section):
                        continue
                    try:
                        session = await stack.enter_async_context(
                            mcp_client.mcp_session(
                                section["sse_url"], section.get("api_key", "")
                            )
                        )
                        tools_resp = await session.list_tools()
                    except Exception:  # noqa: BLE001 - one bad server must not break chat
                        continue

                    for tool in tools_resp.tools:
                        desc = mcp_client.tool_descriptor(tool)
                        if not desc["name"]:
                            continue
                        # Namespace so Amap/hotel tools with the same name can
                        # coexist and the router knows which session to call.
                        exposed = f"{key}__{desc['name']}"[:64]
                        if exposed in routes:
                            continue
                        routes[exposed] = (key, label, desc["name"], session)
                        openai_tools.extend(
                            mcp_client.tools_to_openai(
                                [
                                    {
                                        "name": exposed,
                                        "description": f"[{label}] {desc['description']}",
                                        "input_schema": desc["input_schema"],
                                    }
                                ]
                            )
                        )

                if not openai_tools:
                    async for out in _stream_plain_chat(client, llm["model"], messages):
                        yield out
                    return

                for _round in range(MAX_TOOL_ROUNDS):
                    tool_acc: Dict[int, Dict[str, Any]] = {}

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

                        route = routes.get(name)
                        call_event: Dict[str, Any] = {
                            "type": "tool_call",
                            "tool": name,
                            "args": args,
                        }
                        if route is not None:
                            call_event["source"] = route[1]
                        yield sse_event(call_event)

                        if route is None:
                            text = f"未知工具：{name}"
                        else:
                            _key, _label, raw_name, session = route
                            try:
                                result = await session.call_tool(raw_name, args)
                                text = mcp_client.extract_text(result)
                                if getattr(result, "isError", False):
                                    text = text or "工具返回错误"
                            except Exception as tool_exc:  # noqa: BLE001
                                text = f"工具调用失败：{describe_error(tool_exc)}"

                        result_event: Dict[str, Any] = {
                            "type": "tool_result",
                            "tool": name,
                            "result": text,
                        }
                        if route is not None:
                            result_event["source"] = route[1]
                        yield sse_event(result_event)
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
