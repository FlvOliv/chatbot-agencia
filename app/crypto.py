"""Cifra/decifra segredos por tenant (ex.: `wa_token`) com Fernet.

Chave mestra simétrica vem de `settings.tenant_secret_key` (Fernet key base64,
32 bytes). Gerar com:
    python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"

Sem chave configurada, `encrypt`/`decrypt` falham EXPLÍCITO (fail-closed) — nunca
gravar/ler um segredo em texto puro por engano. Usado pelo seed do tenant e pelo
caminho de envio WhatsApp por agência (Fase 1, bloco B4).
"""

from __future__ import annotations

from functools import lru_cache

from cryptography.fernet import Fernet

from app.config import settings


@lru_cache(maxsize=1)
def _fernet() -> Fernet:
    key = settings.tenant_secret_key
    if not key:
        raise RuntimeError(
            "TENANT_SECRET_KEY não configurada — impossível cifrar/decifrar "
            "segredos de tenant (fail-closed)."
        )
    return Fernet(key.encode() if isinstance(key, str) else key)


def encrypt(plaintext: str) -> str:
    """Cifra um segredo (ex.: wa_token) → texto base64 guardável no banco."""
    return _fernet().encrypt(plaintext.encode()).decode()


def decrypt(token: str) -> str:
    """Decifra um segredo cifrado por `encrypt`."""
    return _fernet().decrypt(token.encode()).decode()
