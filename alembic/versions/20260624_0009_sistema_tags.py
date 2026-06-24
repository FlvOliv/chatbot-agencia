"""sistema de etiquetas (tags) nas conversas

Revision ID: 0009_sistema_tags
Revises: 0008_reminders
Create Date: 2026-06-24

Cria `tags` (catálogo: nome único + cor hex) e `cliente_tags` (M2M).
FK em `clientes`, não em `conversations` — que é log de msgs, não entidade única.
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0009_sistema_tags"
down_revision: Union[str, None] = "0008_reminders"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "tags",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            primary_key=True,
        ),
        sa.Column("name", sa.Text(), nullable=False, unique=True),
        sa.Column("color", sa.String(7), nullable=False, server_default="#6b7280"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_table(
        "cliente_tags",
        sa.Column(
            "cliente_phone",
            sa.Text(),
            sa.ForeignKey("clientes.phone", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "tag_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tags.id", ondelete="CASCADE"),
            primary_key=True,
        ),
    )


def downgrade() -> None:
    op.drop_table("cliente_tags")
    op.drop_table("tags")
