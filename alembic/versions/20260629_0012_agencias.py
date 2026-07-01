"""tabela agencias (tenant) — fundação multi-tenant Fase 1 (B1)

Revision ID: 0012_agencias
Revises: 0011_lead_indicado_por
Create Date: 2026-06-29

Cria a tabela `agencias` (cada linha = um tenant). DDL apenas — a tabela nasce
VAZIA. O seed do tenant 1 (Lu Milhas) é feito FORA da migration, por
`scripts/seed_tenant_lu.py`, pra NÃO acoplar o boot automático do Railway
(`alembic upgrade head`) à TENANT_SECRET_KEY / cifragem (se faltar a chave, o
deploy não pode cair). `wa_phone_id` é a chave de roteamento do webhook (B3).
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0012_agencias"
down_revision: Union[str, None] = "0011_lead_indicado_por"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "agencias",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            primary_key=True,
        ),
        sa.Column("nome", sa.Text(), nullable=False),
        sa.Column("wa_phone_id", sa.Text(), nullable=False, unique=True),
        sa.Column("wa_token_enc", sa.Text(), nullable=False),
        sa.Column("owner_phone", sa.Text(), nullable=False),
        sa.Column(
            "business_hours_start", sa.Integer(), nullable=False, server_default="9"
        ),
        sa.Column(
            "business_hours_end", sa.Integer(), nullable=False, server_default="18"
        ),
        sa.Column(
            "brand",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="{}",
        ),
        sa.Column(
            "prompt_overrides",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="{}",
        ),
        sa.Column("plano", sa.Text(), nullable=False, server_default="essencial"),
        sa.Column(
            "ativo", sa.Boolean(), nullable=False, server_default=sa.text("true")
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_table("agencias")
