"""Models ORM — leads e conversations.

Schema espelha as tabelas definidas no CLAUDE.md.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    String,
    Text,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class Lead(Base):
    """Lead/cotação capturado pela Malu — uma linha POR COTAÇÃO.

    O mesmo cliente (phone) pode ter várias cotações (uma viagem diferente cada
    vez). A identidade de uma cotação é o `numero` (#1001...), NÃO o phone — por
    isso phone não é único.
    """

    __tablename__ = "leads"
    __table_args__ = (
        CheckConstraint(
            "lead_temp IN ('frio','morno','quente','urgente')",
            name="ck_leads_temp",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=func.gen_random_uuid(),
    )
    # Número de protocolo legível (#1001, #1002...) — referência compartilhada
    # entre cliente e Lu. NÃO é usado pra identificar o cliente (isso é pelo
    # phone); é só uma etiqueta amigável. Vem de uma sequência do Postgres.
    numero: Mapped[int] = mapped_column(
        BigInteger,
        server_default=text("nextval('leads_numero_seq')"),
        unique=True,
        nullable=False,
    )
    # NÃO é único: o mesmo cliente pode ter várias cotações. Só índice (busca).
    phone: Mapped[str] = mapped_column(Text, nullable=False, index=True)
    name: Mapped[str | None] = mapped_column(Text, nullable=True)
    destination: Mapped[str | None] = mapped_column(Text, nullable=True)
    travel_type: Mapped[str | None] = mapped_column(Text, nullable=True)
    lead_temp: Mapped[str | None] = mapped_column(String(16), nullable=True)
    briefing_md: Mapped[str | None] = mapped_column(Text, nullable=True)
    raw_data: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default="{}")
    notified_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Lead phone={self.phone!r} temp={self.lead_temp!r}>"


class Cliente(Base):
    """Pessoa por trás de um número de WhatsApp.

    Atualizada na primeira mensagem (com `profile_name` vindo da Meta) e
    refinada quando a Malu identifica o nome preferido no briefing.
    """

    __tablename__ = "clientes"

    phone: Mapped[str] = mapped_column(Text, primary_key=True)
    profile_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    name: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    @property
    def display_name(self) -> str | None:
        """Nome preferido (name) com fallback pro profile_name."""
        return self.name or self.profile_name

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Cliente phone={self.phone!r} name={self.display_name!r}>"


class Reserva(Base):
    """Viagem já fechada com a Lu. Linkada ao cliente pelo phone.

    A Malu consulta status='ativa' na primeira mensagem do cliente pra
    decidir se oferece o atalho de transferência direta pra Lu.
    """

    __tablename__ = "reservas"
    __table_args__ = (
        CheckConstraint(
            "status IN ('ativa','encerrada','cancelada')",
            name="ck_reservas_status",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=func.gen_random_uuid(),
    )
    phone: Mapped[str] = mapped_column(
        Text,
        ForeignKey("clientes.phone", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    codigo_reserva: Mapped[str | None] = mapped_column(Text, nullable=True)
    destino: Mapped[str | None] = mapped_column(Text, nullable=True)
    data_viagem: Mapped[date | None] = mapped_column(Date, nullable=True)
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default="ativa"
    )
    observacoes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Reserva phone={self.phone!r} destino={self.destino!r} status={self.status!r}>"


class PushSubscription(Base):
    """Inscrição de push web (Fase 3) — um navegador/dispositivo da Lu.

    Guardada quando a Lu clica "Ativar notificações" no painel. O backend usa
    `endpoint` + chaves pra enviar o aviso de lead novo via protocolo Web Push.
    Inscrições expiradas (HTTP 404/410 ao enviar) são removidas na hora do envio.
    """

    __tablename__ = "push_subscriptions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=func.gen_random_uuid(),
    )
    endpoint: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    p256dh: Mapped[str] = mapped_column(Text, nullable=False)
    auth: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<PushSubscription endpoint={self.endpoint[:40]!r}...>"


class Reminder(Base):
    """Follow-up agendado (callback) — substitui o agendamento via Celery/Redis.

    Cada coleta em aberto gera até 2 linhas: o lembrete de 30 min e o pré-24h.
    Um cron externo bate em `/internal/tick` a cada minuto e dispara os que já
    venceram (`due_at <= now`) e ainda não foram enviados (`sent_at IS NULL`).

    Supersede: uma mensagem nova do cliente apaga os pendentes do número e
    reinsere → nunca dispara um lembrete velho. `sent_at` serve de trava
    anti-duplicado (marcado ANTES do envio, dentro de uma transação travada).
    """

    __tablename__ = "reminders"
    __table_args__ = (
        CheckConstraint("kind IN ('30m','pre24h')", name="ck_reminders_kind"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=func.gen_random_uuid(),
    )
    phone: Mapped[str] = mapped_column(Text, nullable=False, index=True)
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    due_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    sent_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Reminder phone={self.phone!r} kind={self.kind!r} due={self.due_at}>"


class Tag(Base):
    """Etiqueta colorida para organizar conversas no painel."""

    __tablename__ = "tags"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=func.gen_random_uuid(),
    )
    name: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    color: Mapped[str] = mapped_column(String(7), nullable=False, server_default="#6b7280")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Tag name={self.name!r} color={self.color!r}>"


class ClienteTag(Base):
    """Associação M2M cliente ↔ tag (por phone do cliente)."""

    __tablename__ = "cliente_tags"

    cliente_phone: Mapped[str] = mapped_column(
        Text,
        ForeignKey("clientes.phone", ondelete="CASCADE"),
        primary_key=True,
    )
    tag_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tags.id", ondelete="CASCADE"),
        primary_key=True,
    )


class Conversation(Base):
    """Log de cada mensagem trocada — auditoria e analytics."""

    __tablename__ = "conversations"
    __table_args__ = (
        CheckConstraint(
            "role IN ('user','assistant')",
            name="ck_conversations_role",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=func.gen_random_uuid(),
    )
    phone: Mapped[str] = mapped_column(Text, nullable=False, index=True)
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    model_used: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Caminho do áudio no Supabase Storage (só mensagens de voz do cliente).
    # NULL = mensagem de texto normal. O painel gera um link assinado a partir disso.
    media_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Conversation phone={self.phone!r} role={self.role!r}>"
