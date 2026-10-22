"""Read/write the project-root config.json.

The config holds two sections:
- llm:  { base_url, api_key, model }
- amap: { sse_url, api_key }

All access is defensive: a missing or corrupt file yields an empty-string
skeleton so callers always get a well-formed structure.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict

# Project root = parent of the backend/ package directory.
PROJECT_ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = PROJECT_ROOT / "config.json"


def empty_config() -> Dict[str, Any]:
    """Return the canonical empty config skeleton (all strings blank)."""
    return {
        "llm": {"base_url": "", "api_key": "", "model": ""},
        "amap": {"sse_url": "", "api_key": ""},
    }


def _merge_into_skeleton(raw: Dict[str, Any]) -> Dict[str, Any]:
    """Overlay a possibly-partial dict onto the empty skeleton."""
    cfg = empty_config()
    if not isinstance(raw, dict):
        return cfg
    llm = raw.get("llm") or {}
    amap = raw.get("amap") or {}
    if isinstance(llm, dict):
        for k in ("base_url", "api_key", "model"):
            if llm.get(k) is not None:
                cfg["llm"][k] = str(llm.get(k))
    if isinstance(amap, dict):
        for k in ("sse_url", "api_key"):
            if amap.get(k) is not None:
                cfg["amap"][k] = str(amap.get(k))
    return cfg


def load_config() -> Dict[str, Any]:
    """Load config.json, returning an empty skeleton on any error."""
    try:
        if not CONFIG_PATH.exists():
            return empty_config()
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            raw = json.load(f)
        return _merge_into_skeleton(raw)
    except (OSError, ValueError, json.JSONDecodeError):
        return empty_config()


def save_config(data: Dict[str, Any]) -> Dict[str, Any]:
    """Persist a config dict (merged into skeleton) to config.json."""
    cfg = _merge_into_skeleton(data)
    tmp_path = str(CONFIG_PATH) + ".tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)
    os.replace(tmp_path, CONFIG_PATH)
    return cfg
