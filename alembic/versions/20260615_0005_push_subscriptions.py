"""tabela de inscrições de push web (notificação da Lu)

Revision ID: 0005_push_subscriptions
Revises: 0004_lead_numero
Create Date: 2026-06-15

Guarda as inscrições de push web (Fase 3). Cada linha é um navegador/dispositivo
da Lu que aceitou receber aviso de lead novo. `endpoint` é único.
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0005_push_subscriptions"
down_revision: Union[str, None] = "0004_lead_numero"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "push_subscriptions",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            primary_key=True,
        ),
        sa.Column("endpoint", sa.Text(), nullable=False),
        sa.Column("p256dh", sa.Text(), nullable=False),
        sa.Column("auth", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint("endpoint", name="uq_push_subscriptions_endpoint"),
    )


def downgrade() -> None:
    op.drop_table("push_subscriptions")
