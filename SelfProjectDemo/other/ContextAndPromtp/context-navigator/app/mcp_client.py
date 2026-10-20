"""高德地图 MCP 客户端（SSE 传输）。

参考高德地图 MCP 服务说明：SSE 地址形如
https://mcp.api-inference.modelscope.net/<token>/sse
每次使用建立一条连接（初始化 -> list_tools / call_tool），简单可靠。
"""
from __future__ import annotations

import json
from contextlib import asynccontextmanager

try:
    from mcp import ClientSession
    from mcp.client.sse import sse_client
    MCP_AVAILABLE = True
except ImportError:  # 未安装 mcp 包时其余功能不受影响
    MCP_AVAILABLE = False


class McpError(RuntimeError):
    pass


class McpConn:
    """一条已初始化的 MCP 连接的薄封装。"""

    def __init__(self, session: "ClientSession"):
        self._session = session

    async def list_tools(self) -> list[dict]:
        result = await self._session.list_tools()
        tools = []
        for t in result.tools:
            # 兼容不同版本 SDK：input_schema（snake_case）或 inputSchema（camelCase）
            schema = getattr(t, "input_schema", None) or getattr(t, "inputSchema", None)
            tools.append({
                "name": t.name,
                "description": (t.description or "").strip(),
                "schema": schema or {"type": "object", "properties": {}},
            })
        return tools

    async def call_tool(self, name: str, args: dict) -> str:
        result = await self._session.call_tool(name, args)
        parts = []
        for item in result.content or []:
            text = getattr(item, "text", None)
            if text:
                parts.append(text)
        if not parts:
            return json.dumps({"error": "工具返回空内容"}, ensure_ascii=False)
        return "\n".join(parts)


@asynccontextmanager
async def mcp_connection(settings: dict):
    """打开一条 MCP SSE 连接，yield McpConn。"""
    if not MCP_AVAILABLE:
        raise McpError("未安装 mcp 包（pip install mcp），工具调用不可用")
    cfg = settings.get("mcp", {})
    url = (cfg.get("url") or "").strip()
    if not url:
        raise McpError("未配置 MCP 服务地址")
    headers = {}
    if cfg.get("api_key"):
        headers["Authorization"] = f"Bearer {cfg['api_key']}"
    try:
        async with sse_client(url, headers=headers or None, timeout=15) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                yield McpConn(session)
    except McpError:
        raise
    except BaseExceptionGroup as eg:  # anyio TaskGroup，拆出真实子异常
        detail = "；".join(
            f"{type(x).__name__}: {x}" for x in _flatten_exc(eg)[:3]
        )
        raise McpError(f"MCP 连接失败：{detail or eg}") from eg
    except Exception as exc:
        raise McpError(f"MCP 连接失败：{exc}") from exc


def _flatten_exc(group) -> list:
    out = []
    for x in getattr(group, "exceptions", []):
        if isinstance(x, BaseExceptionGroup):
            out.extend(_flatten_exc(x))
        else:
            out.append(x)
    return out


def to_openai_tools(tools: list[dict]) -> list[dict]:
    """MCP 工具 schema -> OpenAI function-calling 格式。"""
    out = []
    for t in tools:
        out.append({
            "type": "function",
            "function": {
                "name": t["name"],
                "description": t.get("description") or t["name"],
                "parameters": t.get("schema") or {"type": "object", "properties": {}},
            },
        })
    return out
