"""add auth tables and permission tags

Revision ID: c4d712a89351
Revises: b8a3d5f10e44
Create Date: 2026-05-13 15:30:00.000000

第 11 章认证、权限与安全检索：
- users / roles / user_roles：JWT + RBAC 基础三表
- documents 加 permission_tags / created_by
- conversations 加 user_id
- permission_tags 走 GIN 索引，支持 && 数组重叠查询
"""

from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "c4d712a89351"
down_revision: Union[str, Sequence[str], None] = "b8a3d5f10e44"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("username", sa.String(64), nullable=False, unique=True),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("display_name", sa.String(128), nullable=False),
        sa.Column(
            "status",
            sa.String(16),
            nullable=False,
            server_default="active",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )

    op.create_table(
        "roles",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(64), nullable=False, unique=True),
        sa.Column("description", sa.String(256), nullable=False, server_default=""),
        # 角色直接持有权限标签数组；运行时合并出当前用户的有效标签集
        sa.Column(
            "permission_tags",
            postgresql.ARRAY(sa.String()),
            nullable=False,
            server_default="{}",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )

    op.create_table(
        "user_roles",
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "role_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("roles.id", ondelete="CASCADE"),
            primary_key=True,
        ),
    )

    # documents 加权限标签 + 上传者
    op.add_column(
        "documents",
        sa.Column(
            "permission_tags",
            postgresql.ARRAY(sa.String()),
            nullable=False,
            server_default="{}",
        ),
    )
    op.add_column(
        "documents",
        sa.Column(
            "created_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    # GIN 索引支持 permission_tags && user_tags 数组重叠查询
    op.execute(
        "CREATE INDEX ix_documents_permission_tags "
        "ON documents USING GIN (permission_tags)"
    )

    # conversations 归属用户
    op.add_column(
        "conversations",
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.create_index(
        "ix_conversations_user_id", "conversations", ["user_id"], unique=False
    )


def downgrade() -> None:
    op.drop_index("ix_conversations_user_id", table_name="conversations")
    op.drop_column("conversations", "user_id")

    op.execute("DROP INDEX IF EXISTS ix_documents_permission_tags")
    op.drop_column("documents", "created_by")
    op.drop_column("documents", "permission_tags")

    op.drop_table("user_roles")
    op.drop_table("roles")
    op.drop_table("users")
