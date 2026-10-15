"""对话模型封装：调用硅基流动 zai-org/GLM-5.3-Flash。

GLM-5.3-Flash 是推理模型，默认关闭思考模式（thinking: disabled）以降低延迟；
需要更强推理时可在界面上打开。
"""
import json
import re
import time

from openai import OpenAI

from .config import settings


class ChatModel:
    def __init__(self, api_key: str | None = None, model: str | None = None):
        self.api_key = api_key or settings.API_KEY
        self.model = model or settings.CHAT_MODEL
        self.client = OpenAI(api_key=self.api_key, base_url=settings.BASE_URL)

    def chat(
        self,
        messages: list[dict],
        temperature: float = 0.3,
        max_tokens: int = 4096,
        thinking: str = "disabled",
        retries: int = 3,
    ) -> str:
        """普通对话，返回文本内容。"""
        last_error = None
        for attempt in range(retries):
            try:
                resp = self.client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    extra_body={"thinking": {"type": thinking}},
                )
                content = resp.choices[0].message.content
                if content:
                    return content.strip()
                last_error = "模型返回空内容"
            except Exception as exc:  # noqa: BLE001 - 统一重试
                last_error = str(exc)
            time.sleep(1.5 * (attempt + 1))
        raise RuntimeError(f"对话模型调用失败（{self.model}）：{last_error}")

    def chat_json(self, messages: list[dict], retries: int = 3) -> dict:
        """请求 JSON 结果（用于问题路由判断），自动容错解析。"""
        last_error = None
        for attempt in range(retries):
            try:
                text = self.chat(
                    messages,
                    temperature=0.0,
                    max_tokens=1024,
                    thinking="disabled",
                    retries=1,
                )
                return _extract_json(text)
            except Exception as exc:  # noqa: BLE001
                last_error = str(exc)
            time.sleep(1.0 * (attempt + 1))
        raise RuntimeError(f"JSON 模式调用失败：{last_error}")


def _extract_json(text: str) -> dict:
    """从模型输出中提取第一个 JSON 对象（容忍 ```json 包裹与前后废话）。"""
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.S)
    candidate = fenced.group(1) if fenced else None
    if candidate is None:
        brace = re.search(r"\{.*\}", text, re.S)
        if not brace:
            raise ValueError(f"输出中未找到 JSON：{text[:200]}")
        candidate = brace.group(0)
    return json.loads(candidate)
