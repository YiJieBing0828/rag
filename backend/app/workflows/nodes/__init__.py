"""RAG 工作流节点。

每个节点 1 个文件，便于后续章节按需扩展。

约定：节点函数接受 RAGState + 必要依赖（session 等），返回需要更新到 state 的
字段字典；由调用方（chat_service）合并回 state。
"""

from app.workflows.nodes.generate import stream_generate
from app.workflows.nodes.load_context import load_context
from app.workflows.nodes.normalize_query import normalize_query
from app.workflows.nodes.retrieve import retrieve

__all__ = [
    "load_context",
    "normalize_query",
    "retrieve",
    "stream_generate",
]
