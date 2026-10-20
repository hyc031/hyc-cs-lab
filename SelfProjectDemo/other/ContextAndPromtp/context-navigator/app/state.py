"""会话状态与上下文管理核心。

职责：
- 维护上下文条目（System / 摘要 / 对话历史 / RAG / 工具调用）
- KV Cache 命中判定（增量前缀签名比对）
- Token 统计与窗口溢出检测
- 三种窗口策略：删除历史 / 摘要压缩 / 智能裁剪
"""
from __future__ import annotations

import asyncio
import copy
import hashlib
import json
import time

from . import llm as llm_service
from .llm import LLMError
from .token_counter import MSG_OVERHEAD, estimate_tokens

DEFAULT_SYSTEM_PROMPT = (
    "你是 Context Pilot（上下文领航员）演示助手。"
    "请用简洁友好的中文回答问题，并记住用户在对话中告诉你的个人信息。"
)

OVERFLOW_TARGET = 0.70  # 策略执行后把窗口占用压到 70%


def _bigrams(text: str) -> set[str]:
    s = "".join(ch for ch in text if ch.isalnum())
    return {s[i:i + 2] for i in range(len(s) - 1)} if len(s) > 1 else ({s} if s else set())


class Session:
    def __init__(self):
        self.mode = "demo"                # demo / chat
        self.system_prompt = DEFAULT_SYSTEM_PROMPT
        self.entries: list[dict] = []     # 有序上下文条目（system 之外）
        self.stats = {"hit": 0, "miss": 0}
        self.trend: list[int] = []        # 每轮结束时的已用 token
        self.last_ctx_key: str | None = None
        self.last_hit: bool = False
        self.last_turn_info: dict | None = None
        self.last_strategy: dict | None = None
        self.turn_seq = 0
        self.round_seq = 0
        self.turn_hits: dict[int, bool] = {}

    # ---------------- 基础 ----------------
    def reset(self, mode: str | None = None, system_prompt: str | None = None):
        if mode:
            self.mode = mode
        if system_prompt:
            self.system_prompt = system_prompt
        self.entries = []
        self.stats = {"hit": 0, "miss": 0}
        self.trend = []
        self.last_ctx_key = None
        self.last_hit = False
        self.last_turn_info = None
        self.last_strategy = None
        self.turn_seq = 0
        self.round_seq = 0
        self.turn_hits = {}

    def window(self, settings: dict) -> int:
        return int(settings.get("window", 2048))

    def used_tokens(self) -> int:
        total = estimate_tokens(self.system_prompt) + MSG_OVERHEAD
        return total + sum(e["tokens"] for e in self.entries)

    def _next_round(self) -> int:
        self.round_seq += 1
        return self.round_seq

    # ---------------- Cache 签名 ----------------
    _SIG_FIELDS = ("kind", "role", "content", "query", "chunks", "name", "args", "result", "round", "text")

    def _signature(self) -> str:
        payload = {
            "system": self.system_prompt,
            "entries": [{k: e.get(k) for k in self._SIG_FIELDS} for e in self.entries],
        }
        raw = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
        return hashlib.sha1(raw).hexdigest()

    def _mark_cache(self, hit: bool, n_old: int) -> None:
        """hit：旧条目全部命中（绿色），本轮新增条目为重算；miss：全部重算。"""
        for i, e in enumerate(self.entries):
            e["cached"] = bool(hit and i < n_old)

    # ---------------- 条目构造 ----------------
    def _entry_id(self) -> str:
        return f"e{self.turn_seq}-{len(self.entries)}"

    def add_msg(self, role: str, content: str) -> dict:
        e = {
            "id": self._entry_id(), "kind": "msg", "role": role, "content": content,
            "tokens": estimate_tokens(content) + MSG_OVERHEAD,
            "cached": False, "turn": self.turn_seq,
        }
        self.entries.append(e)
        return e

    def add_summary(self, text: str, engine: str) -> dict:
        e = {
            "id": self._entry_id(), "kind": "summary", "text": text, "engine": engine,
            "tokens": estimate_tokens(text) + MSG_OVERHEAD,
            "cached": False, "turn": self.turn_seq,
        }
        self.entries.append(e)
        return e

    def add_rag(self, query: str, chunks: list[dict]) -> dict:
        body = "\n".join(f"[{c['source']}] {c['text']}" for c in chunks)
        e = {
            "id": self._entry_id(), "kind": "rag", "query": query, "chunks": chunks,
            "tokens": estimate_tokens(body) + MSG_OVERHEAD + 2,
            "cached": False, "turn": self.turn_seq,
        }
        self.entries.append(e)
        return e

    def add_tool(self, name: str, args: dict, result: str, round_idx: int) -> dict:
        body = json.dumps(args, ensure_ascii=False) + str(result)
        e = {
            "id": self._entry_id(), "kind": "tool", "name": name, "args": args,
            "result": result, "round": round_idx,
            "tokens": estimate_tokens(body) + MSG_OVERHEAD + 3,
            "cached": False, "turn": self.turn_seq,
        }
        self.entries.append(e)
        return e

    # ---------------- LLM 消息重建 ----------------
    def to_llm_messages(self, new_user: str | None = None) -> list[dict]:
        sys_parts = [self.system_prompt]
        for e in self.entries:
            if e["kind"] == "summary":
                sys_parts.append(f"[历史对话摘要]\n{e['text']}")
        messages = [{"role": "system", "content": "\n\n".join(sys_parts)}]

        emitted_rounds: set[int] = set()
        for e in self.entries:
            if e["kind"] == "msg":
                messages.append({"role": e["role"], "content": e["content"]})
            elif e["kind"] == "rag":
                body = "\n".join(f"[{c['source']}] {c['text']}" for c in e["chunks"])
                messages.append({"role": "system",
                                 "content": f"[知识库检索结果 · 供参考]\n{body}"})
            elif e["kind"] == "tool":
                r = e["round"]
                if r in emitted_rounds:
                    continue
                group = [x for x in self.entries if x["kind"] == "tool" and x["round"] == r]
                messages.append({
                    "role": "assistant", "content": None,
                    "tool_calls": [{
                        "id": x["id"], "type": "function",
                        "function": {"name": x["name"],
                                     "arguments": json.dumps(x["args"], ensure_ascii=False)},
                    } for x in group],
                })
                for x in group:
                    messages.append({"role": "tool", "tool_call_id": x["id"],
                                     "content": x["result"]})
                emitted_rounds.add(r)
        if new_user:
            messages.append({"role": "user", "content": new_user})
        return messages

    # ---------------- 回合执行 ----------------
    def _finish_turn(self, hit: bool, n_old: int) -> dict:
        """统一收尾：标记缓存、统计、趋势、更新签名。"""
        self._mark_cache(hit, n_old)
        self.stats["hit" if hit else "miss"] += 1
        self.last_hit = hit
        self.turn_hits[self.turn_seq] = hit
        used = self.used_tokens()
        self.trend.append(used)
        self.last_ctx_key = self._signature()
        reuse = sum(e["tokens"] for e in self.entries[:n_old]) if hit else 0
        self.last_turn_info = {"hit": hit, "reuse_tokens": reuse, "recalc_tokens": used - reuse,
                               "used": used}
        return self.last_turn_info

    async def chat_turn(self, user_text: str, settings: dict,
                        retriever=None, mcp=None) -> dict:
        """实机聊天回合。retriever: callable(query,k)->chunks；mcp: McpConn|None。"""
        self.turn_seq += 1
        n_old = len(self.entries)
        prefix_key = self._signature()
        hit = prefix_key == self.last_ctx_key

        warnings: list[str] = []

        # 1) RAG 检索
        rag_cfg = settings.get("rag", {})
        if retriever and rag_cfg.get("enabled", True):
            try:
                chunks = retriever(user_text, int(rag_cfg.get("top_k", 3)))
                if chunks:
                    self.add_rag(user_text, chunks)
            except Exception as exc:
                warnings.append(f"RAG 检索失败：{exc}")

        # 2) 工具循环
        tools_schema = None
        if mcp is not None:
            try:
                tools_schema = to_openai_safe(await mcp.list_tools())
            except Exception as exc:
                warnings.append(f"获取 MCP 工具列表失败：{exc}")
                mcp = None

        reply_text = ""
        max_rounds = 5
        for round_idx in range(max_rounds):
            messages = self.to_llm_messages(new_user=user_text)
            message = await asyncio.to_thread(llm_service.chat, settings, messages, tools_schema)
            tool_calls = getattr(message, "tool_calls", None)
            if tool_calls:
                rid = self._next_round()
                for tc in tool_calls:
                    fn = tc.function
                    try:
                        args = json.loads(fn.arguments or "{}")
                    except Exception:
                        args = {"_raw": fn.arguments}
                    if mcp is None:
                        result = "（MCP 不可用，工具未执行）"
                    else:
                        try:
                            result = await mcp.call_tool(fn.name, args)
                        except Exception as exc:
                            result = f"工具执行失败：{exc}"
                    self.add_tool(fn.name, args, result, rid)
                continue
            reply_text = message.content or "（模型返回空回复）"
            break
        else:
            reply_text = "（工具调用轮次过多，已终止）"

        # 3) 写入历史
        self.add_msg("user", user_text)
        self.add_msg("assistant", reply_text)

        # 4) 收尾
        info = self._finish_turn(hit, n_old)
        info["reply"] = reply_text
        info["warnings"] = warnings
        return info

    def demo_turn(self, user_text: str, reply_text: str,
                  rag_chunks: list[dict] | None = None, tool: dict | None = None) -> dict:
        """演示模式回合：脚本化回复，缓存/统计逻辑与实机完全一致。"""
        self.turn_seq += 1
        n_old = len(self.entries)
        prefix_key = self._signature()
        hit = prefix_key == self.last_ctx_key

        if rag_chunks:
            self.add_rag(user_text, rag_chunks)
        if tool:
            self.add_tool(tool["name"], tool["args"], tool["result"], self._next_round())
        self.add_msg("user", user_text)
        self.add_msg("assistant", reply_text)

        info = self._finish_turn(hit, n_old)
        info["reply"] = reply_text
        info["warnings"] = []
        return info

    # ---------------- 窗口策略 ----------------
    def _droppable(self) -> list[int]:
        return [i for i, e in enumerate(self.entries) if e["kind"] in ("msg", "rag", "tool")]

    def _label(self, e: dict) -> str:
        if e["kind"] == "msg":
            return "用户消息" if e["role"] == "user" else "助手回复"
        if e["kind"] == "rag":
            return "RAG 检索"
        if e["kind"] == "tool":
            return f"工具调用 {e['name']}"
        return e["kind"]

    def _preview(self, e: dict) -> str:
        if e["kind"] == "msg":
            text = e["content"]
        elif e["kind"] == "rag":
            text = e["query"]
        elif e["kind"] == "tool":
            text = json.dumps(e["args"], ensure_ascii=False)
        else:
            text = e.get("text", "")
        text = text.strip().replace("\n", " ")
        return text[:60] + ("…" if len(text) > 60 else "")

    def apply_strategy(self, kind: str, settings: dict, summarizer=None) -> dict:
        """kind: delete / summarize / trim。返回详情供前端展示。"""
        window = self.window(settings)
        target = int(window * OVERFLOW_TARGET)
        before = self.used_tokens()
        details: dict = {
            "kind": kind, "time": time.strftime("%H:%M:%S"),
            "window": window, "before_tokens": before,
            "dropped": [], "kept_scores": [], "summary_engine": None, "summary_text": None,
        }

        if kind == "delete":
            while self.used_tokens() > target and len(self._droppable()) > 2:
                idx = self._droppable()[0]
                e = self.entries.pop(idx)
                details["dropped"].append({
                    "label": self._label(e), "preview": self._preview(e),
                    "tokens": e["tokens"], "score": None,
                })

        elif kind == "summarize":
            msg_idx = [i for i, e in enumerate(self.entries) if e["kind"] == "msg"]
            if len(msg_idx) > 4:
                cut = msg_idx[-4]  # 保留最近 2 轮（4 条消息）
                dropped_entries = [self.entries[i] for i in self._droppable() if i < cut]
                drop_ids = {id(e) for e in dropped_entries}
                self.entries = [e for e in self.entries if id(e) not in drop_ids]
                for e in dropped_entries:
                    details["dropped"].append({
                        "label": self._label(e), "preview": self._preview(e),
                        "tokens": e["tokens"], "score": None,
                    })
                convo = "\n".join(
                    f"{'用户' if e['role'] == 'user' else '助手'}：{e['content'][:120]}"
                    for e in dropped_entries if e["kind"] == "msg"
                )
                summary_text, engine = None, "LLM 摘要"
                if summarizer is not None:
                    try:
                        summary_text = summarizer(convo)
                    except Exception as exc:
                        summary_text = None
                        engine = f"本地提取（LLM 摘要失败：{str(exc)[:60]}）"
                if not summary_text:
                    if summarizer is None:
                        engine = "本地提取（未调用 LLM）"
                    summary_text = "；".join(
                        self._preview(e) for e in dropped_entries if e["kind"] == "msg"
                    )[:150]
                # 与既有摘要合并
                old = [e for e in self.entries if e["kind"] == "summary"]
                for e in old:
                    self.entries.remove(e)
                    summary_text = e["text"] + "\n" + summary_text
                self.add_summary(summary_text, engine)
                details["summary_engine"] = engine
                details["summary_text"] = summary_text

        elif kind == "trim":
            last_user = next((e["content"] for e in reversed(self.entries)
                              if e["kind"] == "msg" and e["role"] == "user"), "")
            qgrams = _bigrams(last_user)
            droppable = self._droppable()
            n = len(self.entries)
            scores: dict[int, float] = {}
            for i in droppable:
                e = self.entries[i]
                grams = _bigrams(self._preview(e) + (e.get("content", "") if e["kind"] == "msg" else ""))
                rel = len(qgrams & grams) / max(1, min(len(qgrams), len(grams))) if qgrams else 0.0
                rec = (i + 1) / n  # 越新越高
                scores[i] = round(0.65 * rel + 0.35 * rec, 4)
            # 以 id 收集待裁条目（避免边删边位移导致删错），直到释放足够或只剩最后 1 条
            need_free = self.used_tokens() - target
            droppable = self._droppable()
            score_by_id = {id(self.entries[i]): scores[i] for i in droppable}
            drop_ids: set[int] = set()

            def drop_pass(candidates: list[int], freed_now: int) -> int:
                for i in sorted(candidates, key=lambda x: scores[x]):
                    e = self.entries[i]
                    if id(e) in drop_ids:
                        continue
                    if freed_now >= need_free:
                        break
                    drop_ids.add(id(e))
                    freed_now += e["tokens"]
                    details["dropped"].append({
                        "label": self._label(e), "preview": self._preview(e),
                        "tokens": e["tokens"], "score": scores.get(i),
                    })
                return freed_now

            freed_now = drop_pass(droppable[:-2], 0)  # 优先保留最新 2 条
            if freed_now < need_free:  # 仍溢出 → 兜底：裁到只剩最新 1 条
                freed_now = drop_pass(droppable[-2:-1], freed_now)
            self.entries = [e for e in self.entries if id(e) not in drop_ids]
            details["kept_scores"] = [
                {"label": self._label(e), "preview": self._preview(e),
                 "score": score_by_id.get(id(e))}
                for e in self.entries if e["kind"] in ("msg", "rag", "tool")
            ]

        else:
            raise ValueError(f"未知策略：{kind}")

        details["after_tokens"] = self.used_tokens()
        details["freed"] = before - details["after_tokens"]
        details["percent_after"] = round(details["after_tokens"] / window * 100, 1)
        # 策略改变了上下文 → 下一次请求必然 Cache Miss（前缀失效重算）
        self.last_ctx_key = None
        self.last_strategy = details
        return details

    # ---------------- 快照（演示模式策略对比用） ----------------
    def snapshot(self) -> dict:
        return {
            "system_prompt": self.system_prompt,
            "entries": copy.deepcopy(self.entries),
            "stats": dict(self.stats),
            "trend": list(self.trend),
            "last_ctx_key": self.last_ctx_key,
            "last_hit": self.last_hit,
            "turn_seq": self.turn_seq,
            "round_seq": self.round_seq,
            "turn_hits": dict(self.turn_hits),
        }

    def restore(self, snap: dict) -> None:
        self.system_prompt = snap["system_prompt"]
        self.entries = copy.deepcopy(snap["entries"])
        self.stats = dict(snap["stats"])
        self.trend = list(snap["trend"])
        self.last_ctx_key = snap["last_ctx_key"]
        self.last_hit = snap["last_hit"]
        self.turn_seq = snap["turn_seq"]
        self.round_seq = snap["round_seq"]
        self.turn_hits = dict(snap.get("turn_hits", {}))
        self.last_turn_info = None

    # ---------------- 视图 ----------------
    def context_view(self, settings: dict) -> dict:
        window = self.window(settings)
        used = self.used_tokens()
        sections = [
            {"key": "system", "title": "System Prompt", "icon": "🔧", "fixed": True,
             "items": [{
                 "id": "system", "label": "系统提示词", "content": self.system_prompt,
                 "preview": self.system_prompt[:80], "tokens": estimate_tokens(self.system_prompt) + MSG_OVERHEAD,
                 "cached": self.last_hit,
             }]},
        ]
        groups = {"summary": [], "msg": [], "rag": [], "tool": []}
        for e in self.entries:
            groups.setdefault(e["kind"], []).append(e)

        if groups["summary"]:
            sections.append({"key": "summary", "title": "历史摘要", "icon": "📋", "fixed": False,
                             "items": [{
                                 "id": s["id"], "label": f"摘要（{s['engine']}）", "content": s["text"],
                                 "preview": s["text"][:80], "tokens": s["tokens"], "cached": s["cached"],
                             } for s in groups["summary"]]})

        sections.append({"key": "history", "title": "对话历史", "icon": "💬", "fixed": False,
                         "items": [{
                             "id": e["id"],
                             "label": "用户" if e["role"] == "user" else "助手",
                             "content": e["content"], "preview": self._preview(e),
                             "tokens": e["tokens"], "cached": e["cached"],
                         } for e in groups["msg"]]})

        sections.append({"key": "rag", "title": "RAG 检索结果", "icon": "🔍", "fixed": False,
                         "items": [{
                             "id": e["id"], "label": f"查询：{self._preview(e)}",
                             "content": "\n".join(f"[{c['source']}·相关度{c['score']}] {c['text']}"
                                                  for c in e["chunks"]),
                             "preview": f"{len(e['chunks'])} 条 · {self._preview(e)}",
                             "tokens": e["tokens"], "cached": e["cached"],
                         } for e in groups["rag"]]})

        sections.append({"key": "tools", "title": "工具调用记录", "icon": "🛠️", "fixed": False,
                         "items": [{
                             "id": e["id"],
                             "label": f"{e['name']}({json.dumps(e['args'], ensure_ascii=False)})",
                             "content": e["result"], "preview": self._preview(e),
                             "tokens": e["tokens"], "cached": e["cached"],
                         } for e in groups["tool"]]})

        for sec in sections:
            sec["tokens"] = sum(i["tokens"] for i in sec["items"])
            sec["percent"] = round(sec["tokens"] / max(1, used) * 100, 1)

        return {
            "sections": sections,
            "used": used,
            "window": window,
            "percent": round(used / window * 100, 1),
            "overflow": used >= window,
            "last_turn": self.last_turn_info,
        }

    def chat_view(self) -> list[dict]:
        return [{
            "id": e["id"], "role": e["role"], "content": e["content"],
            "tokens": e["tokens"], "cached": e["cached"], "turn": e["turn"],
            "cache_tag": ("hit" if self.turn_hits.get(e["turn"]) else "miss")
                          if e["role"] == "assistant" else None,
        } for e in self.entries if e["kind"] == "msg"]


def to_openai_safe(tools: list[dict]) -> list[dict]:
    from .mcp_client import to_openai_tools
    return to_openai_tools(tools)
