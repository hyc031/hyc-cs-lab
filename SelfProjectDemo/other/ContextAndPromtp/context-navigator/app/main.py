"""Context Navigator - FastAPI 主入口。

启动：python -m uvicorn app.main:app --port 8765
"""
from __future__ import annotations

import asyncio
import threading

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import llm as llm_service
from . import demo as demo_module
from .config import BASE_DIR, KB_DIR, load_settings, save_settings
from .demo import DemoRunner
from .llm import LLMError
from .mcp_client import McpError, mcp_connection
from .rag import KnowledgeBase, embed_test
from .state import DEFAULT_SYSTEM_PROMPT, Session

app = FastAPI(title="Context Navigator")

session = Session()
kb = KnowledgeBase(KB_DIR)
runner = DemoRunner(local_retrieve=lambda q, k: kb._local_retrieve(q, k))
demo_module.DEMO_RETRIEVE = runner.local_retrieve  # 注入演示脚本使用的本地检索器

_kb_lock = threading.Lock()


def get_settings() -> dict:
    return load_settings()


def ensure_kb(settings: dict) -> None:
    with _kb_lock:
        if kb.engine == "none" and not kb.chunks:
            kb.rebuild(settings)


def full_state(highlight: list[str] | None = None, warnings: list[str] | None = None) -> dict:
    s = get_settings()
    ctx = session.context_view(s)
    return {
        "mode": session.mode,
        "demo": runner.view() if session.mode == "demo" else None,
        "chat": session.chat_view(),
        "context": ctx,
        "stats": session.stats,
        "trend": session.trend[-40:],
        "last_turn": session.last_turn_info,
        "last_strategy": session.last_strategy,
        "system_prompt": session.system_prompt,
        "settings": s,
        "kb": {"engine": kb.engine, "chunks": len(kb.chunks), "docs": kb.doc_names, "error": kb.error},
        "mcp_available": True,
        "highlight": highlight or [],
        "warnings": warnings or [],
    }


# ---------------- 页面 ----------------
@app.get("/")
def index():
    return FileResponse(BASE_DIR / "static" / "index.html")


# ---------------- 状态 / 模式 ----------------
@app.get("/api/state")
def api_state():
    return full_state()


class ModeIn(BaseModel):
    mode: str  # demo / chat


@app.post("/api/mode")
def api_mode(payload: ModeIn):
    if payload.mode not in ("demo", "chat"):
        return {"error": "未知模式"}
    session.reset(mode=payload.mode)
    runner.reset()
    return full_state()


@app.post("/api/reset")
def api_reset():
    session.reset()
    runner.reset()
    return full_state()


class SystemIn(BaseModel):
    system_prompt: str


@app.post("/api/system")
def api_system(payload: SystemIn):
    session.system_prompt = payload.system_prompt.strip() or DEFAULT_SYSTEM_PROMPT
    session.last_ctx_key = None  # System 变更 → 前缀失效
    return full_state()


# ---------------- 聊天（实机模式） ----------------
class ChatIn(BaseModel):
    message: str


@app.post("/api/chat")
async def api_chat(payload: ChatIn):
    text = payload.message.strip()
    if not text:
        return {"error": "消息不能为空"}
    s = get_settings()
    ensure_kb(s)

    warnings: list[str] = []
    retriever = None
    if s.get("rag", {}).get("enabled", True):
        def retriever(q, k, _s=s):
            chunks, _engine = kb.retrieve(_s, q, k)
            return chunks

    mcp = None
    if s.get("mcp", {}).get("enabled", True):
        try:
            mcp_cm = mcp_connection(s)
            mcp = await mcp_cm.__aenter__()
        except McpError as exc:
            warnings.append(str(exc))
            mcp = None

    try:
        await session.chat_turn(text, s, retriever=retriever, mcp=mcp)
    except LLMError as exc:
        warnings.append(str(exc))
    finally:
        if mcp is not None:
            try:
                await mcp_cm.__aexit__(None, None, None)
            except Exception:
                pass

    return full_state(warnings=warnings)


# ---------------- 演示模式 ----------------
@app.post("/api/demo/next")
def api_demo_next():
    s = get_settings()
    ensure_kb(s)  # 演示阶段三的 RAG 需要本地知识库就绪

    def summarizer(text: str) -> str:
        return llm_service.summarize(s, text)

    result = runner.next(session, s, summarizer=summarizer)
    return full_state(highlight=result["highlight"], warnings=[])


@app.post("/api/demo/reset")
def api_demo_reset():
    session.reset(mode="demo")
    runner.reset()
    return full_state()


# ---------------- 窗口策略 ----------------
class StrategyIn(BaseModel):
    kind: str  # delete / summarize / trim


@app.post("/api/strategy")
async def api_strategy(payload: StrategyIn):
    if payload.kind not in ("delete", "summarize", "trim"):
        return {"error": "未知策略"}
    s = get_settings()

    summarizer = None
    if payload.kind == "summarize":
        def summarizer(text: str) -> str:
            return llm_service.summarize(s, text)

    try:
        session.apply_strategy(payload.kind, s, summarizer=summarizer)
    except LLMError as exc:
        # LLM 摘要失败时 state 内部已回退为本地提取，这里仅提示
        session.last_strategy["summary_engine"] = f"本地提取（{exc}）"
    return full_state()


# ---------------- 设置 ----------------
@app.get("/api/settings")
def api_settings_get():
    return {"settings": get_settings()}


@app.put("/api/settings")
def api_settings_put(payload: dict):
    merged = save_settings(payload)
    session.last_ctx_key = None
    return {"settings": merged}


@app.post("/api/settings/test")
async def api_settings_test(payload: dict):
    target = payload.get("target")
    s = get_settings()
    if target == "llm":
        return llm_service.test_connection(s)
    if target == "embedding":
        return embed_test(s)
    if target == "mcp":
        try:
            async with mcp_connection(s) as conn:
                tools = await conn.list_tools()
                names = ", ".join(t["name"] for t in tools[:8]) or "（无工具）"
                more = f" 等 {len(tools)} 个工具" if len(tools) > 8 else ""
                return {"ok": True, "message": f"连接成功，可用工具：{names}{more}"}
        except McpError as exc:
            return {"ok": False, "message": str(exc)}
    return {"ok": False, "message": f"未知测试目标：{target}"}


@app.get("/api/settings/models")
def api_settings_models():
    try:
        return {"ok": True, "models": llm_service.list_models(get_settings())}
    except LLMError as exc:
        return {"ok": False, "models": [], "message": str(exc)}


# ---------------- 知识库 ----------------
@app.post("/api/kb/rebuild")
def api_kb_rebuild():
    result = kb.rebuild(get_settings())
    return full_state()


app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
