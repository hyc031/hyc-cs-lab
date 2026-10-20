"""演示模式：三阶段分步脚本。

阶段一（缓存能力）→ 阶段二（窗口溢出与三种策略）→ 阶段三（Context 透明化：RAG / 工具调用）。
演示完全离线可跑（脚本化回复 + 本地检索），不依赖外部 API。
"""
from __future__ import annotations

from .token_counter import MSG_OVERHEAD, estimate_tokens

FILLER = "这是一段用于填充上下文窗口的演示文本，用来模拟用户连续输入长内容时上下文迅速膨胀的场景。"

WEATHER_RESULT = (
    '{"city":"北京","forecasts":[{"date":"2026-10-19","dayweather":"晴","nightweather":"多云",'
    '"daytemp":"18","nighttemp":"8","daywind":"南风","daypower":"1-3"},'
    '{"date":"2026-10-20","dayweather":"多云","nightweather":"阴","daytemp":"17","nighttemp":"9",'
    '"daywind":"东风","daypower":"1-3"}]}'
)

PHASE_TITLES = {
    1: "第一阶段 · 基础缓存能力",
    2: "第二阶段 · 窗口溢出处理",
    3: "第三阶段 · Context 透明化",
}


def _fill_text(session, settings, target_percent: float) -> str | None:
    """构造一段能把窗口占用精确填充到 target_percent 的长文本。"""
    window = session.window(settings)
    need = int(window * target_percent) - session.used_tokens()
    chars = need - MSG_OVERHEAD
    if chars <= 10:
        return None
    reps = chars // len(FILLER) + 1
    return (FILLER * reps)[:chars]


class DemoRunner:
    def __init__(self, local_retrieve):
        """local_retrieve: callable(query, k) -> chunks（纯本地，离线可用）。"""
        self.local_retrieve = local_retrieve
        self.index = -1
        self.snapshot: dict | None = None

    def reset(self) -> None:
        self.index = -1
        self.snapshot = None

    def view(self) -> dict:
        idx = min(max(self.index, 0), len(STEPS) - 1)
        step = STEPS[idx]
        return {
            "index": self.index,
            "total": len(STEPS),
            "done": self.index >= len(STEPS) - 1,
            "phase": step["phase"],
            "phase_title": PHASE_TITLES[step["phase"]],
            "title": step["title"],
            "narration": step["narration"],
        }

    def next(self, session, settings, summarizer=None) -> dict:
        if self.index >= len(STEPS) - 1:
            return {**self.view(), "highlight": [], "overflow": False}
        self.index += 1
        step = STEPS[self.index]
        highlight: list[str] = []
        action = step.get("action")

        if action == "send":
            out = step["reply"](session, settings)
            if isinstance(out, tuple):
                reply, rag, tool = out
            else:
                reply, rag, tool = out, None, None
            info = session.demo_turn(step["user"], reply, rag_chunks=rag, tool=tool)
            highlight.append("cache-hit" if info["hit"] else "cache-miss")

        elif action == "fill":
            text = _fill_text(session, settings, step["target"])
            if text:
                session.demo_turn(step["user"], step["reply"])
                session.entries[-2]["content"] = text  # 把占位用户消息替换为填充长文本
                session.entries[-2]["tokens"] = estimate_tokens(text) + MSG_OVERHEAD
            else:
                session.demo_turn(step["user"], step["reply"])

        elif action == "snapshot":
            self.snapshot = session.snapshot()

        elif action == "strategy":
            if self.snapshot:
                session.restore(self.snapshot)
            details = session.apply_strategy(step["strategy"], settings, summarizer=summarizer)
            session.last_strategy = details
            highlight.append("strategy-" + step["strategy"])

        # note：纯讲解，无动作

        view = session.context_view(settings)
        if view["overflow"]:
            highlight.append("overflow")
        highlight += step.get("highlight", [])
        return {**self.view(), "highlight": highlight, "overflow": view["overflow"]}


# ---------------- 脚本化回复 ----------------

def _reply_price(session, settings):
    chunks = DEMO_RETRIEVE("这个产品多少钱？有什么功能？", 3)
    reply = ("根据知识库检索结果：Context Pilot 目前提供免费版与 Pro 版（¥29/月），"
             "核心功能包括上下文可视化、KV Cache 模拟与窗口策略管理。详细内容见右侧 RAG 检索面板。")
    return reply, chunks, None


def _reply_weather(session, settings):
    reply = ("已为你查询北京天气：今天晴，8~18℃，南风1-3级；明天多云转阴，9~17℃。"
             "工具调用 get_weather(city=北京) 的返回结果已注入上下文，见右侧面板。")
    return reply, None, {"name": "get_weather", "args": {"city": "北京"}, "result": WEATHER_RESULT}


DEMO_RETRIEVE = None  # 由 main.py 注入：callable(query, k) -> chunks（纯本地检索）


STEPS: list[dict] = [
    {
        "phase": 1, "title": "欢迎来到 Context Navigator",
        "narration": "点击「下一步」开始演示。我们将依次看到：① KV Cache 命中与未命中；② 上下文窗口溢出的三种处理策略；③ RAG 与工具调用如何进入 Context。全程请关注右侧的 Context 结构面板。",
        "action": "note",
    },
    {
        "phase": 1, "title": "第一轮对话：Cache Miss",
        "narration": "输入「你好，我叫小A」。注意右侧：这是一轮全新对话，没有任何可复用的前缀，所以是 Cache Miss（🔄 RECALC），整段上下文都要重新计算，Token 增加。",
        "action": "send", "user": "你好，我叫小A",
        "reply": lambda s, cfg: "你好，小A！很高兴认识你。我已经记住你的名字了——它现在正躺在右侧面板的「对话历史」里。",
    },
    {
        "phase": 1, "title": "第二轮对话：Cache Hit",
        "narration": "输入「我叫什么名字？」。后端检索到历史，前缀完全一致 → Cache Hit（⚡ CACHE）。模型不需要重新计算旧上下文，直接从 Cache 读取。看，助手气泡亮起了绿色 CACHE 标签。",
        "action": "send", "user": "我叫什么名字？",
        "reply": lambda s, cfg: "你叫小A。这条回复直接命中了 KV Cache——上一轮计算过的上下文前缀被完整复用，只有你的新问题需要重新计算。",
    },
    {
        "phase": 1, "title": "阶段小结",
        "narration": "看到没？模型不需要重新计算，直接从 Cache 读取了上下文。右侧 Cache 状态面板显示命中 1 次、未命中 1 次。绿色字体的条目 = 已被缓存复用的前缀。",
        "action": "note",
    },
    {
        "phase": 2, "title": "填充窗口：绿色安全区",
        "narration": "现在连续输入长文本模拟窗口填充。当前进度条处于绿色安全区（<80%）。继续下一步，观察进度条变化。",
        "action": "fill", "target": 0.45,
        "user": "（粘贴了一大段长文本…）", "reply": "好的，这段内容已进入上下文。",
    },
    {
        "phase": 2, "title": "填充窗口：橙色警告",
        "narration": "进度条超过 80%，变成橙色警告区。此时每再输入一轮，离窗口上限就更近一步。",
        "action": "fill", "target": 0.85,
        "user": "（又粘贴了一大段长文本…）", "reply": "收到，上下文占用已进入橙色警告区。",
    },
    {
        "phase": 2, "title": "填充窗口：红色告急",
        "narration": "进度条达到 95% 以上变红并闪烁；本轮直接触及 100% —— 系统弹出「上下文窗口已满」模态框，必须选择一种处理策略。",
        "action": "fill", "target": 1.0,
        "user": "（继续粘贴长文本，窗口满了！）", "reply": "警告：上下文窗口已满，无法继续追加内容。",
    },
    {
        "phase": 2, "title": "策略演示引导",
        "narration": "系统已保存当前溢出状态的快照。接下来三步会分别演示「删除历史 / 摘要压缩 / 智能裁剪」：每一步先恢复溢出状态，再执行对应策略，方便你对比右侧面板的变化。",
        "action": "snapshot",
    },
    {
        "phase": 2, "title": "策略一：🗑️ 删除历史",
        "narration": "删除最旧的历史消息直到占用降到 70%。优点：立刻释放大量 Token；缺点：被删的信息彻底丢失——右侧「对话历史」开头的条目消失了。",
        "action": "strategy", "strategy": "delete",
    },
    {
        "phase": 2, "title": "策略二：📝 摘要压缩",
        "narration": "把旧历史压缩成一段摘要放进 System 区。优点：保留对话意图与关键事实；缺点：细节丢失，且摘要本身也要占 Token。注意策略执行后下一次请求会 Cache Miss（前缀变了）。",
        "action": "strategy", "strategy": "summarize",
    },
    {
        "phase": 2, "title": "策略三：🎯 智能裁剪",
        "narration": "按「与最新问题的相关度 + 时间新近度」给每条消息打分，从最低分开始裁剪，直到降到 70%。优点：最精准，保留下来的都是高价值信息；缺点：需要额外计算打分。点击「查看裁剪详情」可以看到每条的得分。",
        "action": "strategy", "strategy": "trim",
    },
    {
        "phase": 2, "title": "三种策略对比小结",
        "narration": "删除会丢失信息，摘要保留意图但丢失细节，智能裁剪最精准但计算开销大。实际生产中通常组合使用：先摘要、再按相关度裁剪。",
        "action": "note",
    },
    {
        "phase": 3, "title": "RAG：知识自动注入",
        "narration": "输入「这个产品多少钱？有什么功能？」。右侧 RAG 检索结果自动展开——系统从知识库检索出相关内容并注入 Context，模型据此回答。这就是 RAG 的原理。",
        "action": "send", "user": "这个产品多少钱？有什么功能？",
        "reply": _reply_price,
        "highlight": ["expand-rag"],
    },
    {
        "phase": 3, "title": "工具调用：MCP 进入上下文",
        "narration": "输入「帮我查一下北京的天气」。右侧工具调用记录出现 get_weather(city=北京)，工具返回的天气数据也进入了 Context，模型据此生成最终回复。",
        "action": "send", "user": "帮我查一下北京的天气",
        "reply": _reply_weather,
        "highlight": ["expand-tools"],
    },
    {
        "phase": 3, "title": "演示结束",
        "narration": "回顾一下：Cache 决定「算不算得快」，窗口策略决定「装不下怎么办」，RAG 与工具调用决定「Context 里装什么」。切换到「聊天模式」可以用真实模型体验这一切。",
        "action": "note",
    },
]
