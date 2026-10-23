"""Generic MCP-over-SSE helpers shared by every MCP server.

The project talks to three MCP servers:

- Amap (高德地图)      — requires an ``api_key`` appended as ``?key=``
- 12306 (火车票)       — bare SSE URL, no key
- hotel-recommend     — bare SSE URL, no key

They all speak the same MCP protocol, so the connection / tool-description /
result-extraction logic lives here instead of being duplicated per server.

Note on tool schemas: the MCP Python SDK exposes the JSON schema as the
snake_case field ``input_schema`` (the camelCase ``inputSchema`` is only an
input alias). Reading the camelCase attribute therefore yields ``None`` and
silently strips every tool parameter, so both names are tried defensively.
"""
from __future__ import annotations

import contextlib
from typing import Any, AsyncIterator, Dict, List

from mcp import ClientSession
from mcp.client.sse import sse_client


def build_sse_url(sse_url: str, api_key: str = "") -> str:
    """Return the effective SSE URL, appending ``?key=`` only when needed.

    Rules:
    - Empty URL is always an error.
    - No key configured -> use the URL as-is (12306 / hotel style endpoints).
    - URL already contains ``key=`` -> trust it as fully formed.
    """
    sse_url = (sse_url or "").strip()
    api_key = (api_key or "").strip()
    if not sse_url:
        raise ValueError("MCP sse_url 未配置")
    if not api_key or "key=" in sse_url:
        return sse_url
    sep = "&" if "?" in sse_url else "?"
    return f"{sse_url}{sep}key={api_key}"


@contextlib.asynccontextmanager
async def mcp_session(sse_url: str, api_key: str = "") -> AsyncIterator[ClientSession]:
    """Open an initialized MCP ClientSession over SSE.

    Usage:
        async with mcp_session(url, key) as session:
            tools = await session.list_tools()
    """
    url = build_sse_url(sse_url, api_key)
    async with sse_client(url) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            yield session


def tool_input_schema(tool: Any) -> Dict[str, Any]:
    """Read a tool's JSON input schema from either field spelling."""
    schema = getattr(tool, "input_schema", None)
    if schema is None:
        schema = getattr(tool, "inputSchema", None)
    return schema if isinstance(schema, dict) else {}


def tool_descriptor(tool: Any) -> Dict[str, Any]:
    """Normalize an MCP tool object into a plain descriptor dict."""
    return {
        "name": getattr(tool, "name", "") or "",
        "description": getattr(tool, "description", "") or "",
        "input_schema": tool_input_schema(tool),
    }


async def list_tools(sse_url: str, api_key: str = "") -> List[Dict[str, Any]]:
    """Connect to an MCP server and return normalized tool descriptors."""
    async with mcp_session(sse_url, api_key) as session:
        resp = await session.list_tools()
        return [tool_descriptor(t) for t in resp.tools]


def extract_text(result: Any) -> str:
    """Join the ``.text`` of all text-bearing content blocks in a tool result."""
    if result is None:
        return ""
    content = getattr(result, "content", None)
    if content is None:
        return str(result)
    parts: List[str] = []
    for block in content:
        text = getattr(block, "text", None)
        if text is not None:
            parts.append(str(text))
            continue
        data = getattr(block, "data", None)
        if data is not None:
            parts.append(str(data))
    return "\n".join(p for p in parts if p)


def tools_to_openai(tools: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Convert normalized MCP tool descriptors to OpenAI function specs."""
    openai_tools: List[Dict[str, Any]] = []
    for t in tools:
        schema = t.get("input_schema") or {"type": "object", "properties": {}}
        # OpenAI requires an object schema with a properties key.
        if not isinstance(schema, dict) or schema.get("type") != "object":
            schema = {"type": "object", "properties": {}}
        if "properties" not in schema:
            schema = {**schema, "properties": {}}
        openai_tools.append(
            {
                "type": "function",
                "function": {
                    "name": t["name"],
                    "description": t.get("description", "") or "",
                    "parameters": schema,
                },
            }
        )
    return openai_tools
