"""Amap (高德) MCP-over-SSE helper utilities.

The Amap MCP server is reached over an SSE endpoint. The API key must be
passed as a `key` query parameter appended to the SSE URL.

This module provides:
- build_amap_url:        construct the authenticated SSE URL defensively
- amap_session:          async context manager yielding an initialized session
- list_amap_tools:       connect + list tool names (for the test endpoint)
- extract_text_from_result: join text content blocks from a call_tool result
- mcp_tools_to_openai:   convert MCP tool descriptors to OpenAI function specs
"""
from __future__ import annotations

import contextlib
from typing import Any, AsyncIterator, Dict, List, Tuple

from mcp import ClientSession
from mcp.client.sse import sse_client


def build_amap_url(sse_url: str, api_key: str) -> str:
    """Build the authenticated Amap SSE URL.

    Defensive rules:
    - If the URL already contains `key=`, assume it is fully formed.
    - Otherwise append `?key=` or `&key=` depending on existing query string.
    """
    sse_url = (sse_url or "").strip()
    api_key = (api_key or "").strip()
    if not sse_url:
        raise ValueError("Amap sse_url 未配置")
    if "key=" in sse_url:
        return sse_url
    if not api_key:
        raise ValueError("Amap api_key 未配置")
    sep = "&" if "?" in sse_url else "?"
    return f"{sse_url}{sep}key={api_key}"


@contextlib.asynccontextmanager
async def amap_session(sse_url: str, api_key: str) -> AsyncIterator[ClientSession]:
    """Open an initialized MCP ClientSession against the Amap SSE endpoint.

    Usage:
        async with amap_session(url, key) as session:
            tools = await session.list_tools()
    """
    url = build_amap_url(sse_url, api_key)
    async with sse_client(url) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            yield session


async def list_amap_tools(sse_url: str, api_key: str) -> List[Dict[str, Any]]:
    """Connect to Amap and return a list of tool descriptors.

    Each descriptor: { "name", "description", "input_schema" }.
    """
    async with amap_session(sse_url, api_key) as session:
        tools_resp = await session.list_tools()
        result: List[Dict[str, Any]] = []
        for t in tools_resp.tools:
            result.append(
                {
                    "name": t.name,
                    "description": getattr(t, "description", "") or "",
                    "input_schema": getattr(t, "inputSchema", None) or {},
                }
            )
        return result


def extract_text_from_result(result: Any) -> str:
    """Join the `.text` of all text-bearing content blocks in a tool result."""
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
        else:
            # Fallback: try to serialize non-text blocks minimally.
            data = getattr(block, "data", None)
            if data is not None:
                parts.append(str(data))
    joined = "\n".join(p for p in parts if p)
    return joined if joined else ""


def mcp_tools_to_openai(tools: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Convert MCP tool descriptors to OpenAI function-calling tool specs."""
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
