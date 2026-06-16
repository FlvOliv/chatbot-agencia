"""Popula o banco com leads de exemplo (pra demonstrar o dashboard).

NÃO usa IA — monta os dados estruturados na mão e salva pela MESMA função
(`save_lead` + `render_briefing`) que o fluxo real usa. Idempotente: limpa os
números de exemplo antes de inserir.

Uso (venv ativo):
    python scripts/seed_demo.py
"""
from __future__ import annotations

import asyncio
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except Exception:
        pass

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import delete  # noqa: E402

from app.briefing import lead_columns_from_data, render_briefing, save_lead  # noqa: E402
from app.clientes import get_or_create_cliente, update_preferred_name  # noqa: E402
from app.database import SessionLocal  # noqa: E402
from app.models import Conversation, Lead  # noqa: E402
from app.session import clear_history, clear_state, close_redis  # noqa: E402


# (phone, profile_name, dados_estruturados, conversa[(role, texto)])
LEADS = [
    (
        "5511970001111",
        "Carlos Mendes",
        {
            "nome_cliente": "Carlos Mendes",
            "tipo_atendimento": "Pacote completo",
            "origem": "Curitiba",
            "destino": "Gramado",
            "data_ida": "10 de julho",
            "data_volta": "14 de julho",
            "flexibilidade_datas": "Tenho flexibilidade",
            "qtd_adultos": 2,
            "qtd_criancas": 0,
            "hospedagem_incluida": "Sim",
            "tipo_hospedagem": "Pousada",
            "carro_alugado": "Não",
            "bagagem_despachada": "Sim",
            "forma_pagamento": "Cartão",
            "motivo_viagem": "Lazer",
            "prazo_decisao": "Sem pressa, só pesquisando",
            "temperatura_lead": "frio",
            "observacoes": "Cliente disse que está só cotando por enquanto",
        },
        [
            ("user", "oi, queria uma cotação pra Gramado"),
            ("assistant", "Oi, Carlos! Que bom. Pra quando seria e quantas pessoas?"),
            ("user", "julho, eu e minha esposa. mas é só uma pesquisa por enquanto"),
            ("assistant", "Perfeito! Já passo pra Lu montar uma cotação sem compromisso."),
        ],
    ),
    (
        "5511970002222",
        "Juliana Prado",
        {
            "nome_cliente": "Juliana Prado",
            "tipo_atendimento": "Passagem + hospedagem",
            "origem": "São Paulo",
            "destino": "Porto de Galinhas",
            "data_ida": "5 de setembro",
            "data_volta": "12 de setembro",
            "qtd_adultos": 2,
            "qtd_criancas": 1,
            "idades_criancas": "6 anos",
            "hospedagem_incluida": "Sim",
            "regiao_hospedagem": "Perto da praia",
            "tipo_hospedagem": "Resort com café da manhã",
            "qtd_quartos": 1,
            "bagagem_despachada": "Sim",
            "preferencia_voo": "Voo direto se possível",
            "forma_pagamento": "Cartão, parcelado",
            "orcamento": "Cerca de 8 mil no total",
            "motivo_viagem": "Férias em família",
            "prazo_decisao": "Decidir nas próximas semanas",
            "temperatura_lead": "morno",
        },
        [
            ("user", "boa tarde! pacote pra Porto de Galinhas em setembro"),
            ("assistant", "Boa tarde, Juliana! Quantas pessoas e de onde vocês saem?"),
            ("user", "eu, meu marido e minha filha de 6 anos, saindo de SP"),
            ("assistant", "Anotado! Resort perto da praia com café. Já encaminho pra Lu."),
        ],
    ),
    (
        "5511970003333",
        "Roberto Lima",
        {
            "nome_cliente": "Roberto Lima",
            "tipo_atendimento": "Pacote completo",
            "origem": "Rio de Janeiro",
            "destino": "Cancún",
            "data_ida": "20 de agosto",
            "data_volta": "27 de agosto",
            "flexibilidade_datas": "Datas fixas",
            "qtd_adultos": 2,
            "qtd_criancas": 0,
            "hospedagem_incluida": "Sim",
            "tipo_hospedagem": "Resort all inclusive",
            "qtd_quartos": 1,
            "carro_alugado": "Não",
            "bagagem_despachada": "Sim",
            "preferencia_voo": "Voo direto",
            "forma_pagamento": "Cartão",
            "orcamento": "Até 20 mil",
            "motivo_viagem": "Lua de mel",
            "prazo_decisao": "Quer fechar essa semana",
            "veio_indicacao": "Indicação de uma amiga",
            "temperatura_lead": "quente",
            "observacoes": "Muito interessado, quer fechar logo",
        },
        [
            ("user", "Oi Malu! Lua de mel em Cancún, all inclusive"),
            ("assistant", "Que sonho, Roberto! Pra quando e saindo de onde?"),
            ("user", "20 a 27 de agosto, saindo do Rio. quero fechar essa semana!"),
            ("assistant", "Maravilha! Já passo tudo pra Lu te retornar rapidinho."),
        ],
    ),
]


async def seed_one(phone, profile, data, conversa) -> None:
    # limpa o que existir desse número (idempotente)
    await clear_history(phone)
    await clear_state(phone)
    async with SessionLocal() as db:
        await db.execute(delete(Conversation).where(Conversation.phone == phone))
        await db.execute(delete(Lead).where(Lead.phone == phone))
        await db.commit()

    async with SessionLocal() as db:
        await get_or_create_cliente(phone, profile, db)
        # Timestamps crescentes pra conversa aparecer na ordem certa no painel
        base = datetime.now(timezone.utc) - timedelta(minutes=10)
        for i, (role, content) in enumerate(conversa):
            db.add(
                Conversation(
                    phone=phone,
                    role=role,
                    content=content,
                    model_used="llama-3.3-70b-versatile" if role == "assistant" else None,
                    created_at=base + timedelta(seconds=i * 20),
                )
            )
        briefing_md = render_briefing(data, phone)
        cols = lead_columns_from_data(data)
        await save_lead(
            phone,
            db,
            briefing_md=briefing_md,
            lead_temp=cols["lead_temp"],
            name=cols["name"],
            destination=cols["destination"],
            travel_type=cols["travel_type"],
            raw_data=data,
        )
        if cols["name"]:
            await update_preferred_name(phone, cols["name"], db)
        await db.commit()
    print(f"  ✓ {profile:<16} | {data['destino']:<20} | {data['temperatura_lead']}")


async def main() -> None:
    print("Semeando leads de exemplo (sem IA)...")
    for phone, profile, data, conversa in LEADS:
        await seed_one(phone, profile, data, conversa)
    await close_redis()
    print("Pronto. Abra/atualize o dashboard: http://localhost:3000")


if __name__ == "__main__":
    asyncio.run(main())
