"""Adiciona 5 leads NOVOS ao banco, alternando a temperatura.

Mesma mecânica do seed_demo.py (grava pela função real `save_lead` +
`render_briefing`), mas usa números próprios (5511970004444..0008888) pra
NÃO sobrescrever os leads de exemplo. Idempotente nesses números.

Uso (venv ativo):
    python scripts/seed_novos.py
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
        "5511970004444",
        "Fernanda Souza",
        {
            "nome_cliente": "Fernanda Souza",
            "tipo_atendimento": "Pacote completo",
            "origem": "Belo Horizonte",
            "destino": "Maceió",
            "data_ida": "3 de outubro",
            "data_volta": "10 de outubro",
            "flexibilidade_datas": "Datas fixas",
            "qtd_adultos": 2,
            "qtd_criancas": 0,
            "hospedagem_incluida": "Sim",
            "tipo_hospedagem": "Resort all inclusive",
            "qtd_quartos": 1,
            "bagagem_despachada": "Sim",
            "preferencia_voo": "Voo direto",
            "forma_pagamento": "Cartão",
            "orcamento": "Até 15 mil no total",
            "motivo_viagem": "Aniversário de casamento",
            "prazo_decisao": "Quer fechar essa semana",
            "temperatura_lead": "quente",
            "observacoes": "Muito empolgada, já decidiu o destino",
        },
        [
            ("user", "Oi Malu! Pacote pra Maceió em outubro, all inclusive"),
            ("assistant", "Que delícia, Fernanda! Pra quando e quantas pessoas?"),
            ("user", "3 a 10 de outubro, eu e meu marido. quero fechar essa semana!"),
            ("assistant", "Maravilha! Já passo tudo pra Lu te retornar rapidinho."),
        ],
    ),
    (
        "5511970005555",
        "Marcos Antônio",
        {
            "nome_cliente": "Marcos Antônio",
            "tipo_atendimento": "Passagem + hospedagem",
            "origem": "São Paulo",
            "destino": "Foz do Iguaçu",
            "data_ida": "15 de novembro",
            "data_volta": "19 de novembro",
            "flexibilidade_datas": "Tenho alguma flexibilidade",
            "qtd_adultos": 2,
            "qtd_criancas": 2,
            "idades_criancas": "9 e 12 anos",
            "hospedagem_incluida": "Sim",
            "tipo_hospedagem": "Hotel com café da manhã",
            "qtd_quartos": 1,
            "bagagem_despachada": "Sim",
            "forma_pagamento": "Cartão, parcelado",
            "orcamento": "Cerca de 10 mil",
            "motivo_viagem": "Férias em família",
            "prazo_decisao": "Decidir nas próximas semanas",
            "temperatura_lead": "morno",
        },
        [
            ("user", "boa tarde, queria passagem e hotel pra Foz do Iguaçu"),
            ("assistant", "Boa tarde, Marcos! Pra quando e quantas pessoas?"),
            ("user", "novembro, eu, minha esposa e dois filhos. saindo de SP"),
            ("assistant", "Anotado! Já encaminho pra Lu montar a cotação."),
        ],
    ),
    (
        "5511970006666",
        "Patrícia Gomes",
        {
            "nome_cliente": "Patrícia Gomes",
            "tipo_atendimento": "Passagem só",
            "origem": "Rio de Janeiro",
            "destino": "Salvador",
            "data_ida": "Ainda não definido",
            "data_volta": "Ainda não definido",
            "flexibilidade_datas": "Bem flexível",
            "qtd_adultos": 1,
            "qtd_criancas": 0,
            "hospedagem_incluida": "Não",
            "bagagem_despachada": "Não",
            "forma_pagamento": "Não informado",
            "motivo_viagem": "Lazer",
            "prazo_decisao": "Sem pressa, só pesquisando",
            "temperatura_lead": "frio",
            "observacoes": "Cliente só pesquisando preços, sem datas definidas",
        },
        [
            ("user", "oi, quanto custa uma passagem pro Rio pra Salvador?"),
            ("assistant", "Oi, Patrícia! Tem data em mente ou ainda está pesquisando?"),
            ("user", "ainda tô só vendo preço, sem data certa"),
            ("assistant", "Sem problema! Já passo pra Lu te dar uma ideia de valores."),
        ],
    ),
    (
        "5511970007777",
        "Ricardo Alves",
        {
            "nome_cliente": "Ricardo Alves",
            "tipo_atendimento": "Passagem só",
            "origem": "São Paulo",
            "destino": "Recife",
            "data_ida": "Amanhã, dia 13",
            "data_volta": "16 de junho",
            "flexibilidade_datas": "Datas fixas, é urgente",
            "qtd_adultos": 1,
            "qtd_criancas": 0,
            "hospedagem_incluida": "Não",
            "bagagem_despachada": "Sim",
            "preferencia_voo": "O mais cedo possível",
            "forma_pagamento": "Cartão",
            "motivo_viagem": "Emergência familiar",
            "prazo_decisao": "Precisa resolver hoje",
            "temperatura_lead": "urgente",
            "observacoes": "Emergência familiar, precisa viajar amanhã",
        },
        [
            ("user", "Preciso de uma passagem pra Recife amanhã, é urgente!"),
            ("assistant", "Entendi, Ricardo, vou agilizar. Saindo de onde e volta quando?"),
            ("user", "saindo de SP, volto dia 16. é emergência, preciso resolver hoje"),
            ("assistant", "Pode deixar! Já estou avisando a Lu pra te atender agora."),
        ],
    ),
    (
        "5511970008888",
        "Camila Ribeiro",
        {
            "nome_cliente": "Camila Ribeiro",
            "tipo_atendimento": "Pacote completo",
            "origem": "Curitiba",
            "destino": "Fernando de Noronha",
            "data_ida": "8 de dezembro",
            "data_volta": "13 de dezembro",
            "flexibilidade_datas": "Datas fixas",
            "qtd_adultos": 2,
            "qtd_criancas": 0,
            "hospedagem_incluida": "Sim",
            "tipo_hospedagem": "Pousada charmosa",
            "qtd_quartos": 1,
            "bagagem_despachada": "Sim",
            "preferencia_voo": "Voo direto se possível",
            "forma_pagamento": "Cartão",
            "orcamento": "Até 18 mil no total",
            "motivo_viagem": "Lua de mel",
            "prazo_decisao": "Quer fechar logo",
            "veio_indicacao": "Indicação de uma amiga",
            "temperatura_lead": "quente",
            "observacoes": "Lua de mel, bem decidida",
        },
        [
            ("user", "Oi Malu! Lua de mel em Noronha, dezembro"),
            ("assistant", "Que sonho, Camila! Pra quantas pessoas e saindo de onde?"),
            ("user", "eu e meu marido, saindo de Curitiba. queremos fechar logo!"),
            ("assistant", "Perfeito! Já passo tudo pra Lu te retornar com as opções."),
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
    print(f"  + {profile:<18} | {data['destino']:<22} | {data['temperatura_lead']}")


async def main() -> None:
    print("Adicionando 5 leads novos (temperaturas alternadas)...")
    for phone, profile, data, conversa in LEADS:
        await seed_one(phone, profile, data, conversa)
    await close_redis()
    print("Pronto. Abra/atualize o painel: http://localhost:3000")


if __name__ == "__main__":
    asyncio.run(main())
