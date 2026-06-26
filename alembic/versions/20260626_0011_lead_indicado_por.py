"""coluna indicado_por em leads (programa de indicação)

Revision ID: 0011_lead_indicado_por
Revises: 0010_rls_tags
Create Date: 2026-06-26

Guarda QUEM indicou o cliente (nome/telefone) numa coluna própria — não em
raw_data — pra a Lu creditar/relatar a indicação. NULL = sem indicação ou não
informado.
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0011_lead_indicado_por"
down_revision: Union[str, None] = "0010_rls_tags"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "leads",
        sa.Column("indicado_por", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("leads", "indicado_por")
