"""habilita RLS nas tabelas de tags (consistência com a postura de segurança)

Revision ID: 0010_rls_tags
Revises: 0009_sistema_tags
Create Date: 2026-06-24

As demais tabelas públicas já têm RLS (alerta "rls_disabled_in_public" do
Supabase). As tabelas novas `tags`/`cliente_tags` nasceram sem — habilita aqui.
O bot conecta como role `postgres` (BYPASSRLS), então nada quebra; só silencia
o alerta e mantém a API pública sem acesso direto.
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "0010_rls_tags"
down_revision: Union[str, None] = "0009_sistema_tags"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE tags ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE cliente_tags ENABLE ROW LEVEL SECURITY")


def downgrade() -> None:
    op.execute("ALTER TABLE cliente_tags DISABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE tags DISABLE ROW LEVEL SECURITY")
