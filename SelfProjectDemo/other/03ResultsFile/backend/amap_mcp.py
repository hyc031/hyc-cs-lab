"""Amap (高德) MCP-over-SSE helper utilities.

The Amap MCP server is reached over an SSE endpoint. The API key must be
passed as a `key` query parameter appended to the SSE URL.

This module keeps the Amap-specific public API stable while delegating the
generic MCP plumbing (SSE session, tool descriptors, text extraction) to
``backend.mcp_client``:
- build_amap_url:          construct the authenticated SSE URL defensively
- amap_session:            async context manager yielding an initialized session
- list_amap_tools:         connect + list tools (for the test endpoint)
- extract_text_from_result: join text content blocks from a call_tool result
- mcp_tools_to_openai:     convert MCP tool descriptors to OpenAI function specs
"""
from __future__ import annotations

import contextlib
from typing import Any, AsyncIterator, Dict, List

from mcp import ClientSession

from backend import mcp_client


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
    return mcp_client.build_sse_url(sse_url, api_key)


@contextlib.asynccontextmanager
async def amap_session(sse_url: str, api_key: str) -> AsyncIterator[ClientSession]:
    """Open an initialized MCP ClientSession against the Amap SSE endpoint."""
    async with mcp_client.mcp_session(build_amap_url(sse_url, api_key), "") as session:
        yield session


async def list_amap_tools(sse_url: str, api_key: str) -> List[Dict[str, Any]]:
    """Connect to Amap and return a list of tool descriptors.

    Each descriptor: { "name", "description", "input_schema" }.
    """
    async with amap_session(sse_url, api_key) as session:
        resp = await session.list_tools()
        return [mcp_client.tool_descriptor(t) for t in resp.tools]


def extract_text_from_result(result: Any) -> str:
    """Join the `.text` of all text-bearing content blocks in a tool result."""
    return mcp_client.extract_text(result)


def mcp_tools_to_openai(tools: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Convert MCP tool descriptors to OpenAI function-calling tool specs."""
    return mcp_client.tools_to_openai(tools)
