"""phone deixa de ser único em leads (várias cotações por cliente)

Revision ID: 0007_lead_phone_nao_unico
Revises: 0006_conversation_media_path
Create Date: 2026-06-19

O mesmo cliente pode pedir várias cotações; cada uma é um lead separado (com seu
`numero`). Remove as duas travas de unicidade do phone (a constraint
`leads_phone_key` e o índice único `ix_leads_phone`) e mantém só um índice
comum pra busca. `uq_leads_numero` (número único) é preservado.
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0007_lead_phone_nao_unico"
down_revision: Union[str, None] = "0006_conversation_media_path"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Constraint única do phone (some junto o índice que a sustenta).
    op.drop_constraint("leads_phone_key", "leads", type_="unique")
    # Índice único do phone → recria como índice comum (mantém busca rápida).
    op.drop_index("ix_leads_phone", table_name="leads")
    op.create_index("ix_leads_phone", "leads", ["phone"], unique=False)


def downgrade() -> None:
    # ATENÇÃO: só funciona se não houver phones duplicados na tabela.
    op.drop_index("ix_leads_phone", table_name="leads")
    op.create_index("ix_leads_phone", "leads", ["phone"], unique=True)
    op.create_unique_constraint("leads_phone_key", "leads", ["phone"])
