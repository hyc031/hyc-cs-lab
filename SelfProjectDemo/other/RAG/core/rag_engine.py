"""RAG 编排：路由判断 → 查询改写 → 检索 → 带引用生成 → 多轮对话管理。

流程（对应 prompt.txt 的核心功能）：
1. 智能问答：先由 LLM 判断问题是否需要调用知识库
   - 需要 → 检索相关分块，基于资料回答并标注引用 [1][2]...
   - 不需要 → 结合历史对话直接回答
2. 引用来源：返回每条引用的文档名、分块序号、相似度、字符区间与原文
3. 多轮对话：历史记录随会话保留，检索前先做查询改写使问题自包含
"""
from dataclasses import dataclass, field

from .embedder import SiliconFlowEmbedder
from .llm import ChatModel
from .vector_store import FaissVectorStore

ROUTER_SYSTEM_PROMPT = """你是一个问题路由器。判断用户的问题是否需要查询「本地知识库」来回答。

本地知识库中存放的是用户上传的文档（如技术资料、产品文档、规章制度、介绍手册等）。
判断标准：
- 问题涉及具体文档内容、事实、数据、条款、产品细节、公司信息等，或知识库中可能存有相关资料 → 需要知识库 (need_kb=true)
- 明确与文档领域无关的闲聊、与文档无关的通用寒暄、写作建议等 → 不需要知识库 (need_kb=false)
- 拿不准时优先选择 need_kb=true（检索无果时系统会自动兜底说明）。

只输出 JSON，格式：{{"need_kb": true/false, "reason": "一句话理由"}}"""

REWRITE_SYSTEM_PROMPT = """你是一个查询改写器。结合用户最近的对话历史，把用户当前的问题改写成一个独立、完整的检索问题。
要求：保留关键实体与限定词，去除"它、这个、上面"等指代，输出的改写问题只包含问题本身，不要任何解释。
如果当前问题已经独立完整，原样输出即可。"""

ANSWER_SYSTEM_PROMPT = """你是「本地知识库」智能助手，基于提供的知识库资料回答用户问题。

规则：
1. 只依据资料回答，不要编造资料中不存在的信息。
2. 引用资料时在对应句子末尾标注来源编号，如 [1]、[2]，编号必须来自资料列表。
3. 如果资料不足以回答问题，请明确说明"根据知识库资料无法回答"，并尽量给出建议方向。
4. 使用与用户一致的语言（中文/英文）回答，表达简洁、专业。
5. 回答最后不要重复罗列资料原文。"""

DIRECT_SYSTEM_PROMPT = """你是 AI 助手。用户的问题无需查询知识库，请结合对话历史直接回答。
要求：回答简洁、专业、友好。"""


@dataclass
class Citation:
    """一条引用来源。"""

    index: int
    doc_name: str
    chunk_index: int
    score: float
    start: int
    end: int
    text: str

    def to_dict(self) -> dict:
        return self.__dict__.copy()


@dataclass
class AnswerResult:
    answer: str
    used_kb: bool
    route_reason: str
    citations: list[Citation] = field(default_factory=list)
    rewritten_query: str = ""


class RAGEngine:
    """RAG 引擎：组合嵌入模型、向量库与对话模型。"""

    def __init__(
        self,
        embedder: SiliconFlowEmbedder | None = None,
        store: FaissVectorStore | None = None,
        llm: ChatModel | None = None,
    ):
        self.embedder = embedder or SiliconFlowEmbedder()
        self.store = store or FaissVectorStore()
        self.llm = llm or ChatModel()

    # ---------- 1. 路由：是否需要知识库 ----------
    def route(self, question: str, history: list[dict]) -> tuple[bool, str]:
        """判断问题是否需要调用知识库。"""
        context = _history_as_text(history)
        user_prompt = f"对话历史：\n{context or '（无）'}\n\n当前问题：{question}"
        try:
            result = self.llm.chat_json(
                [
                    {"role": "system", "content": ROUTER_SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt},
                ]
            )
            return bool(result.get("need_kb", True)), str(result.get("reason", ""))
        except Exception:  # 路由失败时保守走知识库
            return True, "路由判断失败，默认使用知识库"

    # ---------- 2. 查询改写（多轮对话自包含） ----------
    def rewrite_query(self, question: str, history: list[dict]) -> str:
        if not history:
            return question
        context = _history_as_text(history[-6:])
        try:
            return self.llm.chat(
                [
                    {"role": "system", "content": REWRITE_SYSTEM_PROMPT},
                    {
                        "role": "user",
                        "content": f"对话历史：\n{context}\n\n当前问题：{question}",
                    },
                ],
                temperature=0.0,
                max_tokens=512,
            ).strip()
        except Exception:
            return question

    # ---------- 3. 检索 ----------
    def retrieve(self, query: str, top_k: int = 4, score_threshold: float = 0.0) -> list[dict]:
        vector = self.embedder.embed_query(query)
        results = self.store.search(vector, top_k=top_k)
        if score_threshold > 0:
            results = [r for r in results if r["score"] >= score_threshold]
        return results

    # ---------- 4. 生成（带引用） ----------
    def answer(
        self,
        question: str,
        history: list[dict],
        top_k: int = 4,
        score_threshold: float = 0.3,
        use_kb: bool | None = None,
        temperature: float = 0.3,
        thinking: str = "disabled",
    ) -> AnswerResult:
        """完整 RAG 流程。use_kb=None 时自动路由判断。"""
        if use_kb is None:
            used_kb, reason = self.route(question, history)
        else:
            used_kb, reason = use_kb, "由用户手动指定"

        if not used_kb:
            messages = [{"role": "system", "content": DIRECT_SYSTEM_PROMPT}]
            messages.extend(history[-8:])
            messages.append({"role": "user", "content": question})
            reply = self.llm.chat(messages, temperature=temperature, thinking=thinking)
            return AnswerResult(answer=reply, used_kb=False, route_reason=reason)

        # 查询改写 → 检索 → 组装资料 → 生成
        query = self.rewrite_query(question, history)
        chunks = self.retrieve(query, top_k=top_k, score_threshold=score_threshold)

        if not chunks:
            messages = [{"role": "system", "content": DIRECT_SYSTEM_PROMPT}]
            messages.extend(history[-6:])
            messages.append(
                {
                    "role": "user",
                    "content": f"（知识库中没有找到与以下问题相关的资料，请如实说明）{question}",
                }
            )
            reply = self.llm.chat(messages, temperature=temperature, thinking=thinking)
            return AnswerResult(
                answer=reply,
                used_kb=True,
                route_reason=reason,
                rewritten_query=query,
            )

        citations = [
            Citation(
                index=i,
                doc_name=c["doc_name"],
                chunk_index=c["chunk_index"],
                score=c["score"],
                start=c["start"],
                end=c["end"],
                text=c["text"],
            )
            for i, c in enumerate(chunks, start=1)
        ]

        materials = "\n\n".join(
            f"[{c.index}]（文档：{c.doc_name}｜分块 #{c.chunk_index}｜相似度 {c.score}）\n{c.text}"
            for c in citations
        )
        history_block = ""
        if history:
            history_block = "历史对话：\n" + _history_as_text(history[-6:]) + "\n\n"
        user_content = (
            f"知识库资料：\n{materials}\n\n"
            f"{history_block}"
            f"用户问题：{question}"
        )
        messages = [
            {"role": "system", "content": ANSWER_SYSTEM_PROMPT},
            {"role": "user", "content": user_content},
        ]
        reply = self.llm.chat(messages, temperature=temperature, thinking=thinking)
        return AnswerResult(
            answer=reply,
            used_kb=True,
            route_reason=reason,
            citations=citations,
            rewritten_query=query,
        )


def _history_as_text(history: list[dict]) -> str:
    return "\n".join(f"{m['role']}：{m['content']}" for m in history)
