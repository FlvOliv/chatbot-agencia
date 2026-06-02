"""Comandos especiais do cliente — detectados ANTES de chamar a IA.

Mantemos a lista enxuta de propósito: só palavras inequívocas de
encerramento. O cliente que escreve uma frase com a palavra "sair" no meio
(ex.: "vou sair de casa cedo") não dispara o comando — só mensagens cuja
forma reduzida (strip + lowercase) seja exatamente uma das palavras-chave.
"""

from __future__ import annotations

# Palavras que encerram a conversa em qualquer momento.
# Comparação é exata (strip + lower) — não pega substring.
EXIT_WORDS: frozenset[str] = frozenset(
    {
        "sair",
        "/sair",
        "parar",
        "/parar",
        "encerrar",
        "/encerrar",
        "tchau",
        "exit",
    }
)

EXIT_REPLY: str = (
    "Tudo bem! Encerrei nossa conversa por aqui. "
    "Quando precisar, é só me chamar de novo. 👋"
)


def is_exit_command(text: str) -> bool:
    """True se a mensagem é um comando de encerramento.

    Compara a forma reduzida (strip + lower) com `EXIT_WORDS`.
    Não pega substrings (ex.: "vou sair de casa" → False).
    """
    if not text:
        return False
    return text.strip().lower() in EXIT_WORDS


# ---------------------------------------------------------------------------
# Parser de intenção (cliente com reserva ativa: continuar ou nova viagem?)
# ---------------------------------------------------------------------------
INTENT_RESERVA = "reserva"
INTENT_NOVA = "nova"

# Palavras/frases que indicam "quero falar sobre a reserva que já tenho"
_INTENT_RESERVA_KEYS = (
    "1",
    "1️⃣",
    "um",
    "primeira",
    "primeiro",
    "reserva",
    "tenho",
    "minha reserva",
    "ja tenho",
    "já tenho",
    "ja tenho uma reserva",
    "já tenho uma reserva",
    "tenho reserva",
    "tenho uma reserva",
)

# Palavras/frases que indicam "quero planejar uma viagem nova"
_INTENT_NOVA_KEYS = (
    "2",
    "2️⃣",
    "dois",
    "segunda",
    "segundo",
    "nova",
    "nova viagem",
    "viagem nova",
    "planejar",
    "quero planejar",
    "quero uma nova",
    "outra viagem",
    "cotar",
    "cotacao",
    "cotação",
    "quero viajar",
    "procurando",
)


def _normalize(text: str) -> str:
    """Lowercase + strip + remove pontuação básica pra match mais flexível."""
    cleaned = (text or "").strip().lower()
    # remove vírgulas, pontos, exclamação, etc. nas pontas
    cleaned = cleaned.strip(".,!?;:")
    return cleaned


def parse_intent(text: str) -> str | None:
    """Detecta a intenção do cliente quando ele precisa escolher entre
    "1) tenho reserva" e "2) nova viagem".

    Returns:
        INTENT_RESERVA, INTENT_NOVA, ou None se ambíguo.
    """
    if not text:
        return None
    norm = _normalize(text)
    if not norm:
        return None

    # Match exato primeiro (responde "1" ou "2" sozinhos)
    if norm in _INTENT_RESERVA_KEYS:
        return INTENT_RESERVA
    if norm in _INTENT_NOVA_KEYS:
        return INTENT_NOVA

    # Detecção por substring (mensagem longa)
    is_reserva = any(k in norm for k in _INTENT_RESERVA_KEYS if len(k) >= 6)
    is_nova = any(k in norm for k in _INTENT_NOVA_KEYS if len(k) >= 5)

    if is_reserva and not is_nova:
        return INTENT_RESERVA
    if is_nova and not is_reserva:
        return INTENT_NOVA
    return None  # ambíguo ou sem match


# Mensagens fixas do fluxo de cliente novo/existente
def intent_question(customer_name: str | None) -> str:
    """Mensagem inicial pra cliente com reserva ativa."""
    greeting = f"Olá, {customer_name}!" if customer_name else "Olá!"
    return (
        f"{greeting} Sou a Malu, assistente da Lu Milhas & Viagens. "
        f"Vi que você já tem uma reserva conosco. Como posso te ajudar agora?\n\n"
        f"1️⃣ *Quero falar sobre minha reserva*\n"
        f"2️⃣ *Quero planejar uma viagem nova*"
    )


def intent_unclear_reply() -> str:
    """Pede pro cliente reescolher quando a intenção não foi clara."""
    return (
        "Desculpa, não entendi bem! Pode responder *1* ou *2*?\n\n"
        "1️⃣ Quero falar sobre minha reserva\n"
        "2️⃣ Quero planejar uma viagem nova"
    )


def transferred_reply(customer_name: str | None) -> str:
    """Mensagem ao cliente quando escolhe a opção 1 (reserva existente)."""
    addressing = f"Beleza, {customer_name}" if customer_name else "Beleza"
    return (
        f"{addressing}! Já chamei a Lu aqui pra te ajudar com sua reserva. "
        f"Ela responde em instantes. 🙌"
    )
