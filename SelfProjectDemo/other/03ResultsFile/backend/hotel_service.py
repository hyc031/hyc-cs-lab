"""Hotel recommendation over MCP, with an Amap POI fallback.

`tips.txt` points at a hosted `hotel-recommend` SSE endpoint. That endpoint is
not always the hotel service: the URL shipped in the tips is missing its
deployment id, and the ModelScope gateway currently answers it with the Amap
tool set (which then fails with ``INVALID_USER_KEY`` because no Amap key is
attached).

The query therefore degrades gracefully:

1. hotel MCP, if it exposes a hotel-specific tool -> call it;
2. hotel MCP, if it exposes ``maps_text_search``       -> use it;
3. configured Amap MCP (``cfg["amap"]``, with its key) -> POI search for
   "酒店 / 住宿服务".

Every attempt is recorded in ``warnings`` so the UI can explain which source
actually produced the list instead of pretending the hotel endpoint worked.
"""
from __future__ import annotations

import json
import re
from datetime import date as date_cls
from typing import Any, Dict, List, Optional, Tuple

from backend import amap_mcp, mcp_client

# Endpoint from tips.txt. Kept as the default so the feature is visible in the
# config panel; replace it with the real `hotel-recommend` SSE link to use that
# server directly.
DEFAULT_HOTEL_SSE = "https://mcp-.api-inference.modelscope.net/sse"

_HOTEL_HINTS = ("hotel", "酒店", "住宿", "宾馆", "民宿", "recommend", "recommendation")
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _valid_date(value: str) -> bool:
    value = (value or "").strip()
    if not _DATE_RE.match(value):
        return False
    try:
        date_cls.fromisoformat(value)
    except ValueError:
        return False
    return True


def _nights_between(checkin: str, checkout: str) -> int:
    if not (_valid_date(checkin) and _valid_date(checkout)):
        return 1
    delta = (date_cls.fromisoformat(checkout) - date_cls.fromisoformat(checkin)).days
    return max(delta, 1)


def _find_hotel_tool(tools: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    for tool in tools:
        haystack = f"{tool.get('name', '')} {tool.get('description', '')}".lower()
        if any(hint in haystack for hint in _HOTEL_HINTS):
            return tool
    return None


def _map_hotel_args(
    schema: Dict[str, Any], city: str, keyword: str, checkin: str, checkout: str
) -> Dict[str, Any]:
    """Best-effort argument mapping from a tool JSON schema to our query form."""
    props = (schema or {}).get("properties") or {}
    if not isinstance(props, dict):
        return {}

    candidates: Dict[str, Any] = {
        "city": city,
        "location": city,
        "destination": city,
        "place": city,
        "keyword": keyword,
        "keywords": keyword,
        "query": keyword,
        "q": keyword,
        "checkin": checkin,
        "check_in": checkin,
        "checkindate": checkin,
        "start_date": checkin,
        "startdate": checkin,
        "checkout": checkout,
        "check_out": checkout,
        "checkoutdate": checkout,
        "end_date": checkout,
        "enddate": checkout,
        "nights": _nights_between(checkin, checkout),
        "night": _nights_between(checkin, checkout),
        "days": _nights_between(checkin, checkout),
    }

    args: Dict[str, Any] = {}
    for prop_name in props:
        key = str(prop_name).replace("-", "_").lower()
        if key in candidates and candidates[key] not in ("", None):
            args[prop_name] = candidates[key]
    return args


def _parse_amap_pois(text: str) -> List[Dict[str, Any]]:
    """Parse an Amap ``maps_text_search`` JSON payload into hotel rows."""
    text = (text or "").strip()
    if not text.startswith("{"):
        return []
    try:
        payload = json.loads(text)
    except (ValueError, json.JSONDecodeError):
        return []

    items: List[Dict[str, Any]] = []
    for poi in payload.get("pois") or []:
        if not isinstance(poi, dict):
            continue
        photos = poi.get("photos") or {}
        photo = ""
        if isinstance(photos, dict):
            photo = photos.get("url") or ""
        elif isinstance(photos, list) and photos:
            first = photos[0]
            if isinstance(first, dict):
                photo = first.get("url") or ""

        items.append(
            {
                "id": poi.get("id") or "",
                "name": poi.get("name") or "",
                "address": poi.get("address") or "",
                "typecode": poi.get("typecode") or "",
                "photo": photo,
            }
        )
    return items


def _text_failed(text: str) -> bool:
    lowered = (text or "").lower()
    return "failed" in lowered or "invalid_user_key" in lowered or "error" in lowered


def summarize_hotels(data: Dict[str, Any], limit: int = 5) -> str:
    """Render a compact hotel list for the travel-plan prompt."""
    items = data.get("items") or []
    lines: List[str] = []
    for item in items[:limit]:
        name = item.get("name") or "未命名酒店"
        address = item.get("address") or ""
        lines.append(f"{name}（{address}）" if address else name)
    return "\n".join(lines)


async def list_hotel_tools(sse_url: str, api_key: str = "") -> List[Dict[str, Any]]:
    """List tools exposed by the hotel MCP server (for the config test button)."""
    return await mcp_client.list_tools(sse_url, api_key)


async def query_hotels(
    hotel_cfg: Dict[str, Any],
    amap_cfg: Dict[str, Any],
    city: str,
    keyword: str = "",
    checkin: str = "",
    checkout: str = "",
) -> Dict[str, Any]:
    """Query a hotel source and return structured rows plus the raw response."""
    city = (city or "").strip()
    if not city:
        raise ValueError("城市不能为空")
    keyword = (keyword or "").strip() or "酒店"
    # Amap's `types=住宿服务` is not always honored when a landmark keyword is
    # supplied, so fold the word "酒店" into the query when the user only gave
    # a preference such as "外滩" or "亲子".
    if not any(token in keyword for token in ("酒店", "住宿", "宾馆", "民宿")):
        search_keywords = f"{keyword} 酒店"
    else:
        search_keywords = keyword
    checkin = (checkin or "").strip()
    checkout = (checkout or "").strip()
    if checkin and not _valid_date(checkin):
        raise ValueError("入住日期格式应为 yyyy-MM-dd")
    if checkout and not _valid_date(checkout):
        raise ValueError("离店日期格式应为 yyyy-MM-dd")

    warnings: List[str] = []
    hotel_url = (hotel_cfg.get("sse_url") or "").strip()
    hotel_key = (hotel_cfg.get("api_key") or "").strip()

    # ---- 1/2. Try the configured hotel MCP server. -------------------------
    if hotel_url:
        try:
            async with mcp_client.mcp_session(hotel_url, hotel_key) as session:
                resp = await session.list_tools()
                tools = [mcp_client.tool_descriptor(t) for t in resp.tools]
                hotel_tool = _find_hotel_tool(tools)

                if hotel_tool is not None:
                    args = _map_hotel_args(
                        hotel_tool.get("input_schema") or {},
                        city,
                        keyword,
                        checkin,
                        checkout,
                    )
                    required = (hotel_tool.get("input_schema") or {}).get("required") or []
                    missing = [r for r in required if r not in args]
                    if not missing:
                        result = await session.call_tool(hotel_tool["name"], args)
                        text = mcp_client.extract_text(result)
                        if not getattr(result, "isError", False):
                            return {
                                "city": city,
                                "keyword": keyword,
                                "checkin": checkin,
                                "checkout": checkout,
                                "nights": _nights_between(checkin, checkout),
                                "source": "hotel-mcp",
                                "source_tool": hotel_tool["name"],
                                "count": 0,
                                "items": [],
                                "raw": text,
                                "warnings": warnings,
                            }
                        warnings.append(f"酒店工具 {hotel_tool['name']} 调用失败：{text.strip()}")
                    else:
                        warnings.append(
                            f"酒店工具 {hotel_tool['name']} 缺少必要参数：{', '.join(missing)}"
                        )

                search_tool = next(
                    (t for t in tools if t.get("name") == "maps_text_search"), None
                )
                if search_tool is not None:
                    args = {"keywords": search_keywords, "city": city}
                    props = (search_tool.get("input_schema") or {}).get("properties") or {}
                    if "types" in props:
                        args["types"] = "住宿服务"
                    result = await session.call_tool("maps_text_search", args)
                    text = mcp_client.extract_text(result)
                    if not getattr(result, "isError", False) and not _text_failed(text):
                        items = _parse_amap_pois(text)
                        return {
                            "city": city,
                            "keyword": keyword,
                            "checkin": checkin,
                            "checkout": checkout,
                            "nights": _nights_between(checkin, checkout),
                            "source": "hotel-mcp",
                            "source_tool": "maps_text_search",
                            "count": len(items),
                            "items": items,
                            "raw": text,
                            "warnings": warnings,
                        }
                    warnings.append(f"酒店 MCP 的 POI 搜索失败：{text.strip() or '无返回'}")
        except Exception as exc:  # noqa: BLE001 - fall back to Amap
            warnings.append(f"酒店 MCP 连接失败：{exc}")

    # ---- 3. Amap POI fallback ---------------------------------------------
    amap_url = (amap_cfg.get("sse_url") or "").strip()
    amap_key = (amap_cfg.get("api_key") or "").strip()
    if amap_url and (amap_key or "key=" in amap_url):
        try:
            async with amap_mcp.amap_session(amap_url, amap_key) as session:
                result = await session.call_tool(
                    "maps_text_search",
                    {"keywords": search_keywords, "city": city, "types": "住宿服务"},
                )
                text = mcp_client.extract_text(result)
                if getattr(result, "isError", False) or _text_failed(text):
                    warnings.append(f"高德 POI 搜索失败：{text.strip() or '无返回'}")
                else:
                    items = _parse_amap_pois(text)
                    return {
                        "city": city,
                        "keyword": keyword,
                        "checkin": checkin,
                        "checkout": checkout,
                        "nights": _nights_between(checkin, checkout),
                        "source": "amap",
                        "source_tool": "maps_text_search",
                        "count": len(items),
                        "items": items,
                        "raw": text,
                        "warnings": warnings,
                    }
        except Exception as exc:  # noqa: BLE001
            warnings.append(f"高德 MCP 回退失败：{exc}")

    detail = "；".join(warnings) if warnings else "未配置酒店或高德 MCP"
    raise RuntimeError(detail)


def _tool_text(result: Any) -> str:
    return mcp_client.extract_text(result)
