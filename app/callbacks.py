"""Textos dos follow-ups automáticos (callbacks) — FONTE ÚNICA.

Tanto o backend (agendamento em `app/reminders.py`) quanto a seção
"Mensagens de callback" do prompt da Malu se referem a ESTES textos.
Edite aqui — não duplique o literal em outro lugar.

Tom da Malu: cordial, sem pressão, sem preço, no máximo 1 emoji, negrito
com asterisco simples (*assim*).
"""

from __future__ import annotations

# 30 min após a última mensagem da Malu, se a coleta ainda está aberta.
CALLBACK_30M = (
    "{saudacao} Passando só pra saber se ainda posso te ajudar a organizar "
    "sua cotação 🙂"
)

# Pouco antes de fechar a janela de 24h (Meta), se a coleta ficou em aberto.
CALLBACK_PRE24H = (
    "{saudacao} Ainda dá tempo de a Lu preparar sua cotação — se quiser, "
    "é só me mandar por aqui os últimos detalhes que faltam. 😊"
)


def render_callback(template: str, name: str | None) -> str:
    """Preenche a saudação com o nome do cliente (ou genérica se não houver).

    Mantém o tom natural: "Oi Ana!" quando há nome, "Oi!" quando não há —
    nunca deixa um "{saudacao}" cru escapar pro cliente.
    """
    nome = (name or "").strip()
    saudacao = f"Oi {nome}!" if nome else "Oi!"
    return template.format(saudacao=saudacao)


__all__ = ["CALLBACK_30M", "CALLBACK_PRE24H", "render_callback"]
