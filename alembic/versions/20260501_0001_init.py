"""initial schema

Revision ID: 0001_init
Revises:
Create Date: 2026-05-01 00:00:00
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector

revision = "0001_init"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.create_table(
        "resolutions",
        sa.Column("id", sa.String(length=32), primary_key=True),
        sa.Column("bug_report", sa.Text, nullable=False),
        sa.Column("root_cause", sa.Text, nullable=False),
        sa.Column("fix_diff", sa.Text, nullable=False),
        sa.Column("files_changed", sa.JSON, nullable=False),
        sa.Column("severity", sa.String(length=16), nullable=False),
        sa.Column("component", sa.String(length=16), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("embedding", Vector(384), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_resolutions_component", "resolutions", ["component"])
    op.create_index("ix_resolutions_severity", "resolutions", ["severity"])

    op.create_table(
        "triage_results",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("incoming_bug", sa.Text, nullable=False),
        sa.Column("classification", sa.JSON, nullable=False),
        sa.Column("retrieved_ids", sa.dialects.postgresql.ARRAY(sa.String), nullable=False),
        sa.Column("suggestion", sa.JSON, nullable=False),
        sa.Column(
            "suggested_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("model_version", sa.String(length=64), nullable=False),
        sa.Column("total_cost_usd", sa.Float, nullable=False, server_default="0"),
        sa.Column("total_latency_ms", sa.Integer, nullable=False, server_default="0"),
    )


def downgrade() -> None:
    op.drop_table("triage_results")
    op.drop_index("ix_resolutions_severity", table_name="resolutions")
    op.drop_index("ix_resolutions_component", table_name="resolutions")
    op.drop_table("resolutions")
