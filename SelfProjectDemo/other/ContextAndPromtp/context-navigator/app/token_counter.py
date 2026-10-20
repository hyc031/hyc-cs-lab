"""本地启发式 Token 估算。

规则（对 Qwen/GLM 系分词器的近似）：
- CJK 字符（含中文标点、全角符号）≈ 1 token / 字
- 其他字符（英文、数字、空格等）≈ 4 字符 / token
- 每条消息额外计算 role/分隔符开销 MSG_OVERHEAD
零依赖、零网络请求，演示场景足够精确。
"""
from __future__ import annotations

import math

MSG_OVERHEAD = 4


def _is_cjk(code: int) -> bool:
    return (
        0x4E00 <= code <= 0x9FFF      # CJK 统一表意文字
        or 0x3400 <= code <= 0x4DBF   # 扩展 A
        or 0x3000 <= code <= 0x303F   # CJK 标点
        or 0xFF00 <= code <= 0xFFEF   # 全角字符
        or 0x2000 <= code <= 0x206F   # 通用标点（含省略号、破折号）
    )


def estimate_tokens(text: str) -> int:
    if not text:
        return 0
    cjk = 0
    other = 0
    for ch in text:
        if _is_cjk(ord(ch)):
            cjk += 1
        else:
            other += 1
    return max(1, cjk + math.ceil(other / 4))


def msg_tokens(text: str) -> int:
    """一条消息在上下文中占用的 token（含消息结构开销）。"""
    return estimate_tokens(text) + MSG_OVERHEAD
