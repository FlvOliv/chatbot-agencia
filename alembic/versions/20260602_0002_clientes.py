"""adicionar tabela clientes

Revision ID: 0002_clientes
Revises: 0001_initial
Create Date: 2026-06-02

Cria a tabela `clientes` para armazenar:
- profile_name (vem do payload Meta, pode ser null)
- name (nome confirmado/preferido pelo cliente — atualizado quando a Malu
  identifica no briefing)

A tabela `clientes` é a fonte de verdade de "quem é a pessoa por trás do
número". A tabela `leads` continua representando intenções de viagem.
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0002_clientes"
down_revision: Union[str, None] = "0001_initial"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "clientes",
        sa.Column("phone", sa.Text(), primary_key=True, nullable=False),
        sa.Column(
            "profile_name",
            sa.Text(),
            nullable=True,
            comment="Nome do perfil WhatsApp (payload Meta contacts[].profile.name)",
        ),
        sa.Column(
            "name",
            sa.Text(),
            nullable=True,
            comment="Nome preferido/confirmado pelo cliente (atualizado do briefing)",
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
    op.drop_table("clientes")
