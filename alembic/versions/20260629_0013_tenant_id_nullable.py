"""tenant_id (FK agencias) nullable em todas as tabelas + backfill — Fase 1 (B2)

Revision ID: 0013_tenant_id_nullable
Revises: 0012_agencias
Create Date: 2026-06-29

Adiciona `tenant_id` (FK -> agencias.id) NULLABLE em todas as tabelas de dados e
backfilla TODAS as linhas existentes para o tenant mais antigo (= a Lu, criada
pelo `scripts/seed_tenant_lu.py`). Estratégia expand/contract: aqui é só a fase
EXPAND (nullable) — nenhuma query filtra ainda, comportamento idêntico. O NOT
NULL (contract) vem no B6/0015, depois que B5 garantir que tudo escreve tenant.

⚠️ ORDEM: rodar o seed (cria a agência da Lu) ANTES deste deploy. Se não houver
agência ainda, o backfill é no-op (coluna nullable) e as linhas ficam com NULL —
re-rodar o backfill depois de seedar (ver nota no fim).
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0013_tenant_id_nullable"
down_revision: Union[str, None] = "0012_agencias"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Toda tabela de dados que passa a pertencer a um tenant.
TABLES: tuple[str, ...] = (
    "leads",
    "clientes",
    "reservas",
    "conversations",
    "reminders",
    "tags",
    "cliente_tags",
    "push_subscriptions",
)


def upgrade() -> None:
    for table in TABLES:
        op.add_column(
            table,
            sa.Column(
                "tenant_id",
                postgresql.UUID(as_uuid=True),
                sa.ForeignKey("agencias.id"),
                nullable=True,
            ),
        )
        op.create_index(f"ix_{table}_tenant", table, ["tenant_id"])

    # Backfill: tudo que já existe vira o tenant mais antigo (a Lu). Se ainda não
    # houver agência seedada, o subselect é NULL → no-op seguro (coluna nullable).
    for table in TABLES:
        op.execute(
            f"UPDATE {table} SET tenant_id = "
            "(SELECT id FROM agencias ORDER BY created_at ASC LIMIT 1) "
            "WHERE tenant_id IS NULL"
        )


def downgrade() -> None:
    for table in TABLES:
        op.drop_index(f"ix_{table}_tenant", table_name=table)
        op.drop_column(table, "tenant_id")
