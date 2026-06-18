"""coluna media_path em conversations (áudio guardado no Storage)

Revision ID: 0006_conversation_media_path
Revises: 0005_push_subscriptions
Create Date: 2026-06-18

Guarda o caminho do áudio do cliente no Supabase Storage (só mensagens de voz).
NULL = mensagem de texto. O painel gera um link assinado a partir desse caminho
pra Lu ouvir o áudio original.
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0006_conversation_media_path"
down_revision: Union[str, None] = "0005_push_subscriptions"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "conversations",
        sa.Column("media_path", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("conversations", "media_path")
