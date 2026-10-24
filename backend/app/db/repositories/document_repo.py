"""documents 表访问层。

约定：repository 不负责 commit，事务边界由 service 层控制。
"""

from datetime import datetime
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import ColumnElement

from app.db.models import Document, DocumentStatus, IngestionTask, IngestionTaskStatus
from app.db.repositories.chunk_repo import _permission_where


class DocumentRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_id(
        self,
        document_id: UUID,
        *,
        permission_tags: list[str] | None = None,
    ) -> Document | None:
        """按 id 查文档；非 None permission_tags 时叠加可见性过滤。"""
        if permission_tags is None:
            return await self.session.get(Document, document_id)
        perm_where = _permission_where(permission_tags)
        stmt = select(Document).where(Document.id == document_id)
        if perm_where is not None:
            stmt = stmt.where(perm_where)
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def get_by_hash(self, file_hash: str) -> Document | None:
        stmt = select(Document).where(Document.file_hash == file_hash)
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def add(self, document: Document) -> Document:
        self.session.add(document)
        await self.session.flush()
        return document

    async def update_status(
        self,
        document_id: UUID,
        status: DocumentStatus,
        *,
        error_message: str | None = None,
    ) -> None:
        doc = await self.session.get(Document, document_id)
        if doc is None:
            return
        doc.status = status
        # 仅在显式传入时覆盖；保留 None 语义供成功状态清空之前的错误信息
        if error_message is not None or status != DocumentStatus.FAILED:
            doc.error_message = error_message

    async def list_paginated(
        self,
        page: int,
        page_size: int,
        *,
        status: DocumentStatus | None = None,
        permission_tags: list[str] | None = None,
    ) -> tuple[list[Document], int]:
        """文档列表分页。

        permission_tags：None / 含 "*" 不限；其他按 documents.permission_tags 可见性过滤。
        """
        offset = (page - 1) * page_size
        items_stmt = (
            select(Document)
            .order_by(Document.created_at.desc())
            .offset(offset)
            .limit(page_size)
        )
        count_stmt = select(func.count()).select_from(Document)
        if status is not None:
            items_stmt = items_stmt.where(Document.status == status)
            count_stmt = count_stmt.where(Document.status == status)
        perm_where: ColumnElement[bool] | None = _permission_where(permission_tags)
        if perm_where is not None:
            items_stmt = items_stmt.where(perm_where)
            count_stmt = count_stmt.where(perm_where)
        items = (await self.session.execute(items_stmt)).scalars().all()
        total = (await self.session.execute(count_stmt)).scalar_one()
        return list(items), int(total)

    async def delete(self, document: Document) -> None:
        """删除文档。chunks 走 ORM 级联删除（Document.chunks 配了 delete-orphan）。"""
        await self.session.delete(document)

    async def count(
        self,
        *,
        permission_tags: list[str] | None = None,
        only_ready: bool = False,
    ) -> int:
        """统计可见文档数。

        only_ready=False（默认）：全部状态，回答"库里登记了几篇"。
        only_ready=True：只算 status='ready'，回答"有几篇能被检索到"。

        ⚠ 必须允许调用方显式选择：早期只提供全量计数，而 chunk_count 只算
        ready 文档的切片 ⇒ 一旦库里有"解析中／失败"的文档，两个数字就不在
        同一把尺子上（文档 15 篇、切片却只来自 14 篇），外部 Agent 无法解释。
        """
        stmt = select(func.count()).select_from(Document)
        if only_ready:
            stmt = stmt.where(Document.status == DocumentStatus.READY)
        perm_where = _permission_where(permission_tags)
        if perm_where is not None:
            stmt = stmt.where(perm_where)
        return int((await self.session.execute(stmt)).scalar_one())

    async def get_last_indexed_at(
        self,
        *,
        permission_tags: list[str] | None = None,
    ) -> datetime | None:
        """最近一次"入库任务成功完成"的时间。

        ⚠ 曾经用 `max(Document.updated_at)`，那是错的：`Document.updated_at`
        带 `onupdate=func.now()`，**改个标签、改个备注都会刷新它** ⇒ 这个字段
        的真实语义是"最近一次改动"，不是"最近一次入库"。改成取
        `ingestion_tasks.finished_at`（只算 status='success' 的 ingest/reindex），
        才是外部 Agent 问"知识库里最近有东西进来是什么时候"的答案。
        """
        stmt = (
            select(func.max(IngestionTask.finished_at))
            .select_from(IngestionTask)
            .join(Document, Document.id == IngestionTask.document_id)
            .where(IngestionTask.status == IngestionTaskStatus.SUCCESS)
        )
        perm_where = _permission_where(permission_tags)
        if perm_where is not None:
            stmt = stmt.where(perm_where)
        return (await self.session.execute(stmt)).scalar_one_or_none()
