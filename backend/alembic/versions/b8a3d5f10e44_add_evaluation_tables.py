"""add evaluation tables

Revision ID: b8a3d5f10e44
Revises: 12fe5475a294
Create Date: 2026-05-13 14:00:00.000000

第 10 章评测与 Bad Case 分析：
- evaluation_runs：单次评测 run 的元数据 + 聚合指标
- evaluation_items：单条 case 的输入快照 / 实际输出 / 指标 / Bad Case 归因
  输入字段全部"复制"而非外键 documents，避免评测集迭代后历史 run 失真
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "b8a3d5f10e44"
down_revision: Union[str, Sequence[str], None] = "12fe5475a294"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "evaluation_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(256), nullable=False),
        sa.Column("dataset_name", sa.String(128), nullable=False),
        sa.Column("dataset_size", sa.Integer, nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("progress_total", sa.Integer, nullable=False, server_default="0"),
        sa.Column("progress_completed", sa.Integer, nullable=False, server_default="0"),
        sa.Column("progress_failed", sa.Integer, nullable=False, server_default="0"),
        # 聚合指标：跑完后回填；中途为 NULL
        sa.Column("faithfulness", sa.Float, nullable=True),
        sa.Column("answer_relevancy", sa.Float, nullable=True),
        sa.Column("context_precision", sa.Float, nullable=True),
        sa.Column("context_recall", sa.Float, nullable=True),
        sa.Column("citation_hit_rate", sa.Float, nullable=True),
        sa.Column("refusal_accuracy", sa.Float, nullable=True),
        sa.Column("avg_latency_ms", sa.Float, nullable=True),
        # 首 token 延迟，端到端 latency 之外单独看流式响应起步快慢；拒答 case 不计入
        sa.Column("avg_first_token_latency_ms", sa.Float, nullable=True),
        sa.Column("error_message", sa.Text, nullable=True),
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
        "ix_evaluation_runs_created_at", "evaluation_runs", ["created_at"]
    )

    op.create_table(
        "evaluation_items",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "run_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("evaluation_runs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        # 输入快照（复制评测集 jsonl 当时的值，避免文件后续被改动后历史 run 失真）
        sa.Column("case_id", sa.String(64), nullable=False),
        sa.Column("question", sa.Text, nullable=False),
        sa.Column("expected_answer", sa.Text, nullable=False),
        sa.Column(
            "expected_document_names",
            postgresql.JSONB,
            nullable=False,
            server_default="[]",
        ),
        sa.Column(
            "expected_keywords",
            postgresql.JSONB,
            nullable=False,
            server_default="[]",
        ),
        sa.Column("should_refuse", sa.Boolean, nullable=False),
        sa.Column("tags", postgresql.JSONB, nullable=False, server_default="[]"),
        # 实际输出快照
        sa.Column("actual_answer", sa.Text, nullable=False, server_default=""),
        sa.Column(
            "actual_refused", sa.Boolean, nullable=False, server_default=sa.text("false")
        ),
        sa.Column("citations", postgresql.JSONB, nullable=False, server_default="[]"),
        sa.Column(
            "retrieved_chunks_meta",
            postgresql.JSONB,
            nullable=False,
            server_default="[]",
        ),
        sa.Column("query_route", postgresql.JSONB, nullable=True),
        sa.Column("agent_steps", postgresql.JSONB, nullable=True),
        sa.Column("verify_result", postgresql.JSONB, nullable=True),
        sa.Column("trace_id", sa.String(64), nullable=True),
        sa.Column("latency_ms", sa.Integer, nullable=False, server_default="0"),
        # 拒答 / 报错时为 None：没有真正生成 token，首 token 延迟无意义
        sa.Column("first_token_latency_ms", sa.Integer, nullable=True),
        sa.Column("error_message", sa.Text, nullable=True),
        # 指标
        sa.Column("faithfulness", sa.Float, nullable=True),
        sa.Column("answer_relevancy", sa.Float, nullable=True),
        sa.Column("context_precision", sa.Float, nullable=True),
        sa.Column("context_recall", sa.Float, nullable=True),
        # citation_hit 在 should_refuse=True 时为 NULL，避免拒答 case 拉低命中率
        sa.Column("citation_hit", sa.Boolean, nullable=True),
        sa.Column("refusal_correct", sa.Boolean, nullable=False),
        # Bad Case 归因：规则自动初判，前端可 PATCH 覆盖
        sa.Column(
            "is_bad_case", sa.Boolean, nullable=False, server_default=sa.text("false")
        ),
        sa.Column("bad_case_category", sa.String(64), nullable=True),
        sa.Column("bad_case_note", sa.Text, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_evaluation_items_run_id", "evaluation_items", ["run_id"]
    )
    # 只看 bad case 是详情页主要的筛选场景，加复合索引避免全表扫描
    op.create_index(
        "ix_evaluation_items_run_bad",
        "evaluation_items",
        ["run_id", "is_bad_case"],
    )


def downgrade() -> None:
    op.drop_index("ix_evaluation_items_run_bad", table_name="evaluation_items")
    op.drop_index("ix_evaluation_items_run_id", table_name="evaluation_items")
    op.drop_table("evaluation_items")
    op.drop_index("ix_evaluation_runs_created_at", table_name="evaluation_runs")
    op.drop_table("evaluation_runs")
