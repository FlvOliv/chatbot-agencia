"""adicionar tabela reservas

Revision ID: 0003_reservas
Revises: 0002_clientes
Create Date: 2026-06-02

Cria a tabela `reservas` para registrar viagens já fechadas com a Lu.
A Malu consulta essa tabela na primeira mensagem do cliente — se houver
reserva ativa, oferece ao cliente a opção de continuar planejando uma
viagem nova ou transferir direto pra Lu (que tem o contexto da reserva).

População é manual via SQL no Supabase (MVP) — quando a Lu fecha uma
cotação, ela mesma insere a reserva. Futuramente vira parte do CRM.
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0003_reservas"
down_revision: Union[str, None] = "0002_clientes"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "reservas",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column(
            "phone",
            sa.Text(),
            sa.ForeignKey("clientes.phone", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "codigo_reserva",
            sa.Text(),
            nullable=True,
            comment="Código interno usado pela Lu pra identificar a reserva",
        ),
        sa.Column("destino", sa.Text(), nullable=True),
        sa.Column("data_viagem", sa.Date(), nullable=True),
        sa.Column(
            "status",
            sa.String(length=16),
            nullable=False,
            server_default=sa.text("'ativa'"),
        ),
        sa.Column("observacoes", sa.Text(), nullable=True),
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
        sa.CheckConstraint(
            "status IN ('ativa','encerrada','cancelada')",
            name="ck_reservas_status",
        ),
    )
    op.create_index(
        "ix_reservas_phone_status",
        "reservas",
        ["phone", "status"],
    )


def downgrade() -> None:
    op.drop_index("ix_reservas_phone_status", table_name="reservas")
    op.drop_table("reservas")
