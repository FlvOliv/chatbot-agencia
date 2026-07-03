"""Sonda de comportamento da Malu — linha de base ANTES das mudanças.

Roda cenários scriptados contra o CÉREBRO REAL da Malu (route_and_ask + prompt
real) e aplica a MESMA pós-produção do pipeline (split de marcadores, price_guard,
sanitizer, extração estruturada e o GATE de completude). Assim reproduz fielmente
os 3 comportamentos (repetir / transferir / completar) — mas NÃO envia nada pra
Meta nem pra Lu, e NÃO toca Redis/Postgres. Só chama a IA.

Uso (Git Bash, venv ativo):
    PYTHONUTF8=1 venv/Scripts/python -m scripts.behavior_probe
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except Exception:
        pass

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.ai import extract_lead_data, route_and_ask  # noqa: E402
from app.briefing import (  # noqa: E402
    ask_missing_fields,
    gate_missing_fields,
    normalize_lead_data,
    split_reply_and_briefing,
    split_reply_and_transfer,
)
from app.sanitize import price_guard, sanitize_outgoing  # noqa: E402

SEP = "─" * 70


# Cada cenário: nome do cliente + turnos que o cliente manda, na ordem.
SCENARIOS: dict[str, dict] = {
    "T1 · Só passagem (nacional)": {
        "name": "Marina",
        "turns": [
            "Oi, queria uma passagem pra Porto Seguro",
            "Saindo de São Paulo",
            "Ida dia 10 de dezembro e volta dia 17",
            "Somos 2 adultos e uma criança de 6 anos",
            "Prefiro voo direto se tiver",
            "Pode ser no cartão, parcelado",
            "Por enquanto só pesquisando, mas se for bom eu fecho",
        ],
    },
    "T2 · Pacote (passagem + hospedagem) + preço/milhas": {
        "name": "Rodrigo",
        "turns": [
            "Oi Malu! Quero um pacote pra Maceió pra mim e minha esposa, "
            "saindo do Rio, de 5 a 12 de janeiro. Voo e hotel.",
            "Queria um hotel bom, de frente pra praia, com café da manhã",
            "Tenho umas milhas do Latam Pass, dá pra usar?",
            "E mais ou menos quanto fica? tenho uns 8 mil pra gastar",
            "1 quarto pra nós dois",
            "Quero fechar essa semana ainda",
        ],
    },
    "T3 · Triagem — pede atendente no meio": {
        "name": "Carla",
        "turns": [
            "Oi, queria uma cotação de passagem",
            "Pra Lisboa, saindo de SP, em março",
            "Na verdade prefiro falar direto com uma atendente, pode ser?",
        ],
    },
}


async def run_scenario(title: str, cfg: dict) -> None:
    print("\n" + "=" * 70)
    print(f"CENÁRIO {title}")
    print("=" * 70)

    name = cfg["name"]
    history: list[dict] = []
    outcome = "coleta-em-aberto (não finalizou nos turnos scriptados)"

    for i, user_msg in enumerate(cfg["turns"]):
        history.append({"role": "user", "content": user_msg})
        ctx = {"name": name, "is_first_turn": i == 0}

        reply, model = await route_and_ask(history, customer_context=ctx)

        if model == "error":
            print(f"\n[CLIENTE] {user_msg}")
            print(f"[MALU/ERRO] cadeia de IA caiu → pipeline transferiria pra Lu")
            outcome = "TRANSFERIU (falha de IA)"
            break

        # Mesma pós-produção do main.py, na mesma ordem:
        customer_reply, briefing_block = split_reply_and_briefing(reply)
        customer_reply, wants_transfer = split_reply_and_transfer(customer_reply)
        customer_reply, price_blocked = price_guard(customer_reply)
        customer_reply = sanitize_outgoing(customer_reply)

        flags = [f"modelo={model}"]
        if price_blocked:
            flags.append("⚠ PRICE_GUARD disparou (modelo citou valor)")

        print(f"\n[CLIENTE] {user_msg}")

        if wants_transfer:
            print(f"[MALU] {customer_reply}")
            print(f"        » {', '.join(flags)}")
            print("        » 🔁 EMITIU ## TRANSFERIR → pipeline passa pra Lu e silencia")
            outcome = f"TRANSFERIU no turno {i + 1}"
            break

        if briefing_block:
            # Reproduz o gate exatamente como o main.py: extrai sobre o history
            # (sem a resposta atual da Malu) e decide bloquear ou finalizar.
            raw = await extract_lead_data(history)
            lead_data = normalize_lead_data(raw) if raw else None
            missing = gate_missing_fields(
                lead_data if lead_data is not None else {}, history
            )
            if missing:
                nudge = ask_missing_fields(missing)
                print(f"[MALU] (tentou fechar o briefing)")
                print(f"        » 🚧 GATE BLOQUEOU. Faltam: {missing}")
                print(f"        » nudge que iria pro cliente: {nudge}")
                print(f"        » {', '.join(flags)}")
                customer_reply = nudge  # o que entra no history (como no main.py)
            else:
                print(f"[MALU] {customer_reply}")
                print(f"        » ✅ GATE LIBEROU → FINALIZA lead + fecha coleta")
                print(f"        » extração final: {lead_data}")
                print(f"        » {', '.join(flags)}")
                outcome = f"FINALIZOU no turno {i + 1}"
                history.append({"role": "assistant", "content": customer_reply})
                break
        else:
            print(f"[MALU] {customer_reply}")
            print(f"        » {', '.join(flags)}")

        history.append({"role": "assistant", "content": customer_reply})

    print(f"\n>>> RESULTADO: {outcome}")

    # Diagnóstico final: o que a extração + gate diriam do estado atual da coleta.
    raw = await extract_lead_data(history)
    lead_data = normalize_lead_data(raw) if raw else None
    missing = gate_missing_fields(lead_data if lead_data is not None else {}, history)
    print(f">>> GATE no fim: {'COMPLETO ✅' if not missing else f'faltando {missing}'}")
    print(f">>> Extração final (o que a Lu receberia):")
    if lead_data:
        for k, v in lead_data.items():
            if v:
                print(f"      {k}: {v}")
    else:
        print("      (extração vazia/None)")


async def main() -> None:
    print("SONDA DE COMPORTAMENTO — Malu (linha de base, cérebro REAL, sem envio)")
    for title, cfg in SCENARIOS.items():
        try:
            await run_scenario(title, cfg)
        except Exception as exc:  # não deixa 1 cenário derrubar os outros
            print(f"\n[ERRO no cenário {title}] {type(exc).__name__}: {exc}")
    print("\n" + SEP + "\nFIM DA SONDA\n")


if __name__ == "__main__":
    asyncio.run(main())
