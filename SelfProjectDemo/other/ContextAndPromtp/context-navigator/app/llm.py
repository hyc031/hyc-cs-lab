"""LLM 服务：硅基流动 OpenAI 兼容接口（GLM-5.3-Flash）。"""
from __future__ import annotations

from openai import OpenAI


class LLMError(RuntimeError):
    pass


def _client(settings: dict) -> OpenAI:
    cfg = settings["llm"]
    if not cfg.get("api_key"):
        raise LLMError("未配置 LLM API Key，请在「设置」中填写")
    return OpenAI(api_key=cfg["api_key"], base_url=cfg["base_url"], timeout=60)


def chat(settings: dict, messages: list, tools: list | None = None, max_tokens: int = 700):
    """调用对话模型，返回 choices[0].message。tools 为 OpenAI function-calling 格式。"""
    cfg = settings["llm"]
    kwargs = dict(
        model=cfg["model"],
        messages=messages,
        temperature=float(cfg.get("temperature", 0.7)),
        max_tokens=max_tokens,
    )
    if tools:
        kwargs["tools"] = tools
        kwargs["tool_choice"] = "auto"
    try:
        resp = _client(settings).chat.completions.create(**kwargs)
    except Exception as exc:  # 网络 / 鉴权 / 模型名错误等
        raise LLMError(f"LLM 调用失败：{exc}") from exc
    return resp.choices[0].message


def summarize(settings: dict, text: str) -> str:
    """调用 LLM 将历史对话压缩为要点摘要。"""
    prompt = (
        "请把下面的对话历史压缩成简洁的要点摘要，保留关键事实（人名、数字、结论），"
        "不超过 150 字，直接输出摘要内容：\n\n" + text
    )
    message = chat(
        settings,
        [{"role": "system", "content": "你是对话摘要助手，输出中文要点式摘要。"},
         {"role": "user", "content": prompt}],
        max_tokens=300,
    )
    return (message.content or "").strip()


def test_connection(settings: dict) -> dict:
    """设置面板的「测试连接」：发送一条最小请求。"""
    import time

    start = time.time()
    try:
        message = chat(
            settings,
            [{"role": "user", "content": "ping，请只回复 pong"}],
            max_tokens=8,
        )
        return {
            "ok": True,
            "message": f"连接成功（{(time.time() - start) * 1000:.0f}ms），模型回复：{(message.content or '').strip()[:40]}",
        }
    except Exception as exc:
        return {"ok": False, "message": str(exc)}


def list_models(settings: dict) -> list[str]:
    """拉取 /v1/models 模型列表，供设置面板选择模型名。"""
    try:
        models = _client(settings).models.list()
        return sorted(m.id for m in models.data)[:200]
    except Exception as exc:
        raise LLMError(f"获取模型列表失败：{exc}") from exc
