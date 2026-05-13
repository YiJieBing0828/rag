"""add ingestion_tasks table and documents.version

Revision ID: 971e54efb407
Revises: c4d712a89351
Create Date: 2026-05-13 19:10:00.000000

第 12 章异步任务与增量索引：
- documents 加 version：每次 reindex 成功 +1，用于前端可视化"内容已变更"
- ingestion_tasks：Celery 任务生命周期与进度记录，前端轮询展示
"""

from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "971e54efb407"
down_revision: Union[str, Sequence[str], None] = "c4d712a89351"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "documents",
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
    )
    # server_default 在迁移后撤掉，应用层用 ORM default=1 控制
    op.alter_column("documents", "version", server_default=None)

    op.create_table(
        "ingestion_tasks",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "document_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("documents.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("task_type", sa.String(16), nullable=False),
        sa.Column(
            "status", sa.String(16), nullable=False, server_default="pending"
        ),
        sa.Column(
            "retry_count", sa.Integer(), nullable=False, server_default="0"
        ),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column(
            "progress_total", sa.Integer(), nullable=False, server_default="0"
        ),
        sa.Column(
            "progress_done", sa.Integer(), nullable=False, server_default="0"
        ),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_ingestion_tasks_document_id",
        "ingestion_tasks",
        ["document_id"],
    )
    # 详情页"最近一次任务"查询固定按 document_id + created_at 排序，组合索引避免回表
    op.create_index(
        "ix_ingestion_tasks_document_created",
        "ingestion_tasks",
        ["document_id", sa.text("created_at DESC")],
    )


def downgrade() -> None:
    op.drop_index("ix_ingestion_tasks_document_created", table_name="ingestion_tasks")
    op.drop_index("ix_ingestion_tasks_document_id", table_name="ingestion_tasks")
    op.drop_table("ingestion_tasks")
    op.drop_column("documents", "version")
