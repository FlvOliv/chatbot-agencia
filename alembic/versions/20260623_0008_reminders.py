"""tabela de lembretes (follow-ups) — agendamento via Postgres + cron

Revision ID: 0008_reminders
Revises: 0007_lead_phone_nao_unico
Create Date: 2026-06-23

Substitui o agendamento dos callbacks via Celery/Redis (que cutucava o Redis
24h e estourava o limite do plano grátis) por linhas no Postgres, disparadas
por um cron externo que chama `/internal/tick`. Índices em `phone` (supersede)
e `due_at` (seleção dos vencidos).
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0008_reminders"
down_revision: Union[str, None] = "0007_lead_phone_nao_unico"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "reminders",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            primary_key=True,
        ),
        sa.Column("phone", sa.Text(), nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint("kind IN ('30m','pre24h')", name="ck_reminders_kind"),
    )
    op.create_index("ix_reminders_phone", "reminders", ["phone"], unique=False)
    op.create_index("ix_reminders_due_at", "reminders", ["due_at"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_reminders_due_at", table_name="reminders")
    op.drop_index("ix_reminders_phone", table_name="reminders")
    op.drop_table("reminders")
