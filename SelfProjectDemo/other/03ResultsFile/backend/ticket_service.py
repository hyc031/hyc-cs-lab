"""12306 train ticket query over MCP.

The hosted 12306 MCP exposes ``get-tickets`` with four arguments:

    date            "yyyy-MM-dd"
    fromStation     Chinese city name or station code
    toStation       Chinese city name or station code
    trainFilterFlags  any combination of G D Z T K O F S ("" = no filter)

It returns one block per train::

    G531 北京南(telecode:VNP) -> 上海虹桥(telecode:AOH) 06:08 -> 12:04 历时：05:56
    - 商务座: 无票 1744元
    - 二等座: 剩余2张票 498元

``parse_tickets`` turns that text into structured rows so the frontend can
render a real table; ``raw`` is always kept so nothing is lost if the upstream
format changes.
"""
from __future__ import annotations

import re
from datetime import date as date_cls
from typing import Any, Dict, List

from backend import mcp_client

# Hosted demo endpoint from tips.txt. ModelScope hosted links expire after
# 24 hours, so this is a default, not a guarantee — users can override it in
# the config panel.
DEFAULT_TICKET_SSE = "https://mcp.api-inference.modelscope.net/7875e3ba63354d/sse"

_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_TRAIN_RE = re.compile(
    r"^(?P<train>[A-Z]\d+)\s+"
    r"(?P<from>.+?)\(telecode:(?P<from_code>[A-Z]+)\)\s*->\s*"
    r"(?P<to>.+?)\(telecode:(?P<to_code>[A-Z]+)\)\s+"
    r"(?P<depart>\d{2}:\d{2})\s*->\s*(?P<arrive>\d{2}:\d{2})\s+"
    r"历时[：:]\s*(?P<duration>\d{1,2}:\d{2})\s*$"
)
_SEAT_RE = re.compile(
    r"^-\s*(?P<name>[^:：]+?)\s*[:：]\s*(?P<status>.+?)"
    r"(?:\s+(?P<price>\d+(?:\.\d+)?)元)?\s*$"
)


def validate_date(value: str) -> str:
    """Validate a yyyy-MM-dd string and return it normalized."""
    value = (value or "").strip()
    if not _DATE_RE.match(value):
        raise ValueError("日期格式应为 yyyy-MM-dd，例如 2026-10-25")
    try:
        date_cls.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"日期不合法：{value}") from exc
    return value


def parse_tickets(text: str) -> List[Dict[str, Any]]:
    """Parse the 12306 MCP text table into structured train rows."""
    items: List[Dict[str, Any]] = []
    current: Dict[str, Any] | None = None

    for raw_line in (text or "").splitlines():
        line = raw_line.strip()
        if not line:
            continue

        train = _TRAIN_RE.match(line)
        if train:
            current = {
                "train": train.group("train"),
                "from_station": train.group("from"),
                "from_code": train.group("from_code"),
                "to_station": train.group("to"),
                "to_code": train.group("to_code"),
                "depart": train.group("depart"),
                "arrive": train.group("arrive"),
                "duration": train.group("duration"),
                "seats": [],
            }
            items.append(current)
            continue

        if current is None:
            continue
        seat = _SEAT_RE.match(line)
        if seat:
            status = seat.group("status").strip()
            price = seat.group("price")
            current["seats"].append(
                {
                    "name": seat.group("name").strip(),
                    "status": status,
                    "available": status != "无票",
                    "price": float(price) if price else None,
                }
            )

    return items


def summarize_tickets(data: Dict[str, Any], limit: int = 6) -> str:
    """Render a compact multi-line summary for the travel-plan prompt."""
    items = data.get("items") or []
    if not items:
        return ""
    lines: List[str] = []
    for item in items[:limit]:
        seats = [
            s for s in item.get("seats", []) if s.get("name") in ("二等座", "一等座", "商务座")
        ]
        seat_txt = "；".join(
            f"{s['name']}{'有票' if s['available'] else '无票'}"
            + (f" {int(s['price'])}元" if s.get("price") is not None else "")
            for s in seats
        )
        lines.append(
            f"{item['train']} {item['from_station']}→{item['to_station']} "
            f"{item['depart']}-{item['arrive']} 历时{item['duration']}"
            + (f"｜{seat_txt}" if seat_txt else "")
        )
    return "\n".join(lines)


async def list_ticket_tools(sse_url: str, api_key: str = "") -> List[Dict[str, Any]]:
    """List tools exposed by the 12306 MCP server (for the config test button)."""
    return await mcp_client.list_tools(sse_url, api_key)


async def query_tickets(
    sse_url: str,
    api_key: str,
    date: str,
    from_station: str,
    to_station: str,
    train_flags: str = "",
) -> Dict[str, Any]:
    """Query 12306 via MCP and return structured + raw results."""
    date = validate_date(date)
    from_station = (from_station or "").strip()
    to_station = (to_station or "").strip()
    if not from_station or not to_station:
        raise ValueError("出发城市和到达城市都不能为空")

    flags = "".join(ch for ch in (train_flags or "").upper() if ch in "GDZTKOFS")

    async with mcp_client.mcp_session(sse_url, api_key) as session:
        tools = await session.list_tools()
        names = {t.name for t in tools.tools}
        if "get-tickets" not in names:
            raise RuntimeError(
                "12306 MCP 未提供 get-tickets 工具，当前工具："
                + ", ".join(sorted(names))
            )
        result = await session.call_tool(
            "get-tickets",
            {
                "date": date,
                "fromStation": from_station,
                "toStation": to_station,
                "trainFilterFlags": flags,
            },
        )

    text = mcp_client.extract_text(result)
    if getattr(result, "isError", False):
        raise RuntimeError(text.strip() or "12306 返回错误")

    items = parse_tickets(text)
    if not items and text.strip().lower().startswith("error"):
        raise RuntimeError(text.strip())
    return {
        "date": date,
        "from_station": from_station,
        "to_station": to_station,
        "train_flags": flags,
        "count": len(items),
        "items": items,
        "raw": text,
    }
