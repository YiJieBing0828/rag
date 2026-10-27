"""引用编号一致性检查（纯函数：不调 LLM、不碰 DB、不依赖 FastAPI）。

【为什么需要它】
`citations` 里的 `ordinal` 是后端按位置赋号的（`enumerate(chunks, start=1)`），
但正文里的 `[N]` 是**模型自己写的**。模型完全可能把"依据在片段 1"的结论标成 `[2]`
—— 结果是**答案正确、依据错位**，比编造更隐蔽（看起来有据可查，点开却是另一段）。

而现有的 `answer_verifier` 是把校验交给同一个 LLM 的：提示词里虽然写了
"核对 N 号片段是否支撑这条结论"，实测会被降级成"这些片段里有没有这句话"
—— 只要那句话在**任意**一段里出现过就判通过，编号错位被放过。

【本模块的定位】
用**代码**做一道不依赖模型判断的硬检查：把"标了 [N] 的那一句"抽成硬 token，
再看这些 token 在不在**第 N 段**的原文里。

- 只抽两类硬 token：①数字＋单位 ②英文/型号标识符
- **不做分词、不做语义、不做同义词** —— 宁可漏报，不要误报
- 只返回 issue，**由调用方决定记日志还是拦截**；本模块不改任何行为

【已知边界（故意不做）】
- 中文专名（"浮充区间"这类）没有分词就抽不出来 ⇒ 靠数字/型号兜住主要场景
- 一句话里同时引用多段时，只做"整体是否在这段里出现过"的判断
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterator

from app.core.logging import get_logger
from app.retrieval.vector_retriever import RetrievedChunk

logger = get_logger(__name__)

# 硬 token 一：数字 + 单位。要求「数字紧邻单位」，避免把纯序号（如"第 3 章"）也算进来
_NUMBER_UNIT = re.compile(
    r"\d+(?:\.\d+)?\s*"
    r"(?:分钟|小时|毫秒|秒钟|秒|天|周|个月|月|年|%|mm|cm|km|kg|Wh|mAh|W|V|A|℃)"
)
# 硬 token 二：英文 / 型号标识符（Aster-7、HyDE、RRF、JSONB）
_IDENT = re.compile(r"[A-Za-z][A-Za-z0-9\-]{2,}")
# 英文虚词不算证据
_STOPWORDS = frozenset(
    {"the", "and", "for", "with", "that", "this", "from", "http", "https", "www", "com"}
)

# 只在句末切句：顿号、逗号、分号都不断开（否则"…约需 78 分钟；充满后…[2]"会被切碎，
# 引用编号跟数字分到两个句子去，检查直接失效）
_SENTENCE_END = re.compile(r"(?<=[。！？!?\n])")
_CITATION = re.compile(r"\[(\d{1,2})\]")


@dataclass(frozen=True)
class CitationIssue:
    """单条不一致记录。

    ordinal  —— 正文里标的编号（1 起）
    sentence —— 带这个编号的那一句（便于人肉复核）
    tokens   —— 从这句里抽到的硬 token
    missing  —— 其中在「第 ordinal 段」原文里找不到的那些
    reason   —— mismatch（内容对不上）／out_of_range（编号越界）
    """

    ordinal: int
    sentence: str
    tokens: tuple[str, ...]
    missing: tuple[str, ...]
    reason: str = "mismatch"


def _norm(text: str) -> str:
    """比对前统一：去空白 + 转小写（"78 分钟" 与 "78分钟" 视为同一个）。"""
    return re.sub(r"\s+", "", text).lower()


def _iter_sentences(answer: str) -> Iterator[str]:
    for piece in _SENTENCE_END.split(answer):
        sentence = piece.strip()
        if sentence:
            yield sentence


def _extract_hard_tokens(sentence: str) -> tuple[str, ...]:
    """抽硬 token，按出现顺序去重。抽不到就返回空元组（该句不做判断）。"""
    found: list[str] = []
    for match in _NUMBER_UNIT.finditer(sentence):
        found.append(match.group(0))
    for match in _IDENT.finditer(sentence):
        token = match.group(0)
        if token.lower() in _STOPWORDS:
            continue
        found.append(token)

    seen: set[str] = set()
    ordered: list[str] = []
    for token in found:
        key = _norm(token)
        if key not in seen:
            seen.add(key)
            ordered.append(token)
    return tuple(ordered)


def check_citation_alignment(
    answer: str,
    chunks: list[RetrievedChunk],
) -> list[CitationIssue]:
    """把"标了 [N] 的那一句"和"第 N 段原文"对一遍。

    返回空列表 = 没发现问题（注意：**没发现问题 ≠ 校验通过**，只代表硬 token 都对得上）。
    """
    if not answer or not chunks:
        return []

    issues: list[CitationIssue] = []
    for sentence in _iter_sentences(answer):
        ordinals = [int(m) for m in _CITATION.findall(sentence)]
        if not ordinals:
            continue

        tokens = _extract_hard_tokens(sentence)
        if not tokens:
            # 抽不到硬 token 就不判断：这是"宁可漏报"的那一侧
            continue

        for ordinal in ordinals:
            if ordinal < 1 or ordinal > len(chunks):
                issues.append(
                    CitationIssue(
                        ordinal=ordinal,
                        sentence=sentence,
                        tokens=tokens,
                        missing=tokens,
                        reason="out_of_range",
                    )
                )
                continue

            target = _norm(chunks[ordinal - 1].content or "")
            missing = tuple(t for t in tokens if _norm(t) not in target)
            if missing:
                issues.append(
                    CitationIssue(
                        ordinal=ordinal,
                        sentence=sentence,
                        tokens=tokens,
                        missing=missing,
                        reason="mismatch",
                    )
                )
    return issues


def log_citation_issues(
    issues: list[CitationIssue],
    *,
    question: str,
    trace_id: str | None = None,
) -> None:
    """把 issue 写进日志。**只记日志，不改拒答、不改正文** —— 先观测再决定要不要动手。"""
    if not issues:
        logger.debug("引用编号一致性检查通过：question=%r", question)
        return
    for issue in issues:
        logger.warning(
            "引用编号与片段内容不一致：ordinal=%s reason=%s missing=%s sentence=%r "
            "question=%r trace_id=%s",
            issue.ordinal,
            issue.reason,
            issue.missing,
            issue.sentence,
            question,
            trace_id,
        )
