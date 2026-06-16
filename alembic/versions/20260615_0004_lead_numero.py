"""adicionar número de protocolo aos leads

Revision ID: 0004_lead_numero
Revises: 0003_reservas
Create Date: 2026-06-15

Cada lead ganha um número legível (#1001, #1002...) — uma referência
compartilhada entre cliente e Lu. NÃO identifica o cliente (isso é pelo
phone); é só uma etiqueta amigável. Vem de uma sequência do Postgres
começando em 1001. Os leads que já existem são numerados por ordem de criação.
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0004_lead_numero"
down_revision: Union[str, None] = "0003_reservas"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

SEQ = "leads_numero_seq"
START = 1001


def upgrade() -> None:
    # 1) sequência de protocolo, começando em 1001
    op.execute(f"CREATE SEQUENCE IF NOT EXISTS {SEQ} START WITH {START} MINVALUE 1")
    # 2) coluna nullable (temporário, pra permitir o backfill)
    op.add_column("leads", sa.Column("numero", sa.BigInteger(), nullable=True))
    # 3) backfill: numera os leads existentes por ordem de criação (1001, 1002...)
    op.execute(
        f"""
        WITH ordenados AS (
            SELECT id, row_number() OVER (ORDER BY created_at, id) - 1 AS rn
            FROM leads
        )
        UPDATE leads l
           SET numero = {START} + o.rn
          FROM ordenados o
         WHERE l.id = o.id
        """
    )
    # 4) avança a sequência pra continuar DEPOIS do maior número já usado
    op.execute(
        f"SELECT setval('{SEQ}', (SELECT COALESCE(MAX(numero), {START} - 1) FROM leads))"
    )
    # 5) default pra novos leads + NOT NULL + unicidade; amarra a sequência à coluna
    op.execute(f"ALTER TABLE leads ALTER COLUMN numero SET DEFAULT nextval('{SEQ}')")
    op.alter_column("leads", "numero", nullable=False)
    op.create_unique_constraint("uq_leads_numero", "leads", ["numero"])
    op.execute(f"ALTER SEQUENCE {SEQ} OWNED BY leads.numero")


def downgrade() -> None:
    op.drop_constraint("uq_leads_numero", "leads", type_="unique")
    op.drop_column("leads", "numero")  # drop da coluna remove a sequência (OWNED BY)
    op.execute(f"DROP SEQUENCE IF EXISTS {SEQ}")
