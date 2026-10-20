"""设置管理：内存 + data/settings.json 持久化。"""
from __future__ import annotations

import json
import os
import threading
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
SETTINGS_PATH = DATA_DIR / "settings.json"
KB_DIR = DATA_DIR / "knowledge"

# 默认配置（硅基流动平台），API Key 留空，请在设置页填写或通过环境变量注入
LLM_API_KEY = os.getenv("SILICONFLOW_API_KEY", "")
EMBEDDING_API_KEY = os.getenv("SILICONFLOW_EMBEDDING_API_KEY", LLM_API_KEY)

DEFAULTS: dict = {
    "llm": {
        "base_url": "https://api.siliconflow.cn/v1",
        "api_key": LLM_API_KEY,
        "model": "zai-org/GLM-5.3-Flash",
        "temperature": 0.7,
    },
    "embedding": {
        "base_url": "https://api.siliconflow.cn/v1",
        "api_key": EMBEDDING_API_KEY,
        "model": "Qwen/Qwen3-Embedding-4B",
    },
    "mcp": {
        "enabled": True,
        "url": "https://mcp.api-inference.modelscope.net/903f626fad1b49/sse",
        "api_key": "",
    },
    "rag": {
        "enabled": True,
        "top_k": 3,
        "min_score": 0.0,
    },
    "window": 2048,
}

_lock = threading.Lock()


def _deep_merge(base: dict, override: dict) -> dict:
    out = dict(base)
    for k, v in override.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def load_settings() -> dict:
    with _lock:
        cfg = dict(DEFAULTS)
        if SETTINGS_PATH.exists():
            try:
                stored = json.loads(SETTINGS_PATH.read_text("utf-8"))
                cfg = _deep_merge(cfg, stored)
            except Exception:
                pass
        return cfg


def save_settings(override: dict) -> dict:
    with _lock:
        current = dict(DEFAULTS)
        if SETTINGS_PATH.exists():
            try:
                current = _deep_merge(current, json.loads(SETTINGS_PATH.read_text("utf-8")))
            except Exception:
                pass
        merged = _deep_merge(current, override)
        SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
        SETTINGS_PATH.write_text(json.dumps(merged, ensure_ascii=False, indent=2), "utf-8")
        return merged
