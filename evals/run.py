"""Runner do eval comparativo da Malu.

    python -m evals.run --provider all              # rodada completa (respeita as travas)
    python -m evals.run --provider groq --limit 1   # piloto
    python -m evals.run --provider all --dry-run    # só estima chamadas/tokens/custo
    python -m evals.run --provider groq --run 2026-11-16   # continua uma rodada de outro dia

Cada caso × repetição vira uma linha em evals/results/<run>_<provedor>.jsonl.
Casos já gravados são pulados (retomada), então a rodada pode ser fatiada em
vários dias no free tier. O relatório sai de `python -m evals.report`.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import random
import sys
import time
from dataclasses import asdict
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except Exception:  # noqa: BLE001
        pass

import yaml  # noqa: E402

EVALS_DIR = Path(__file__).resolve().parent
ROOT = EVALS_DIR.parent
DATASET = EVALS_DIR / "dataset" / "casos.jsonl"
RESULTS = EVALS_DIR / "results"

# Chars por token aproximado do português (só pra estimativa antes do piloto).
_CHARS_PER_TOKEN = 3.5


def load_yaml(name: str) -> dict[str, Any]:
    return yaml.safe_load((EVALS_DIR / name).read_text(encoding="utf-8"))


def load_cases(seed: int) -> list[dict[str, Any]]:
    cases = [json.loads(line) for line in DATASET.read_text(encoding="utf-8").splitlines() if line.strip()]
    random.Random(seed).shuffle(cases)  # rodada parcial cobre categorias variadas
    return cases


def synthetic_phone(case_id: str, rep: int) -> str:
    """Telefone sintético estável (DDI 55 + DDD 00, que não existe)."""
    digits = int(hashlib.sha256(f"{case_id}:{rep}".encode()).hexdigest(), 16) % 10**8
    return f"5500{digits:08d}"


def results_path(run: str, provider: str) -> Path:
    return RESULTS / f"{run}_{provider}.jsonl"


def done_keys(path: Path) -> set[tuple[str, int]]:
    if not path.exists():
        return set()
    out = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            r = json.loads(line)
            out.add((r["case_id"], r["rep"]))
    return out


def estimate(cases: list[dict[str, Any]], k: int, coleta: bool, price: dict[str, Any], prior: list[dict]) -> dict:
    """Estimativa de chamadas, tokens e custo. Usa médias observadas se houver."""
    turns = sum(len(c["turns"]) for c in cases) * k
    calls_per_turn = 2 if coleta else 1
    calls = turns * calls_per_turn
    if prior:
        all_calls = [c for r in prior for t in r["turns"] for c in t["calls"]]
        in_per_call = sum(c["prompt_tokens"] for c in all_calls) / max(len(all_calls), 1)
        out_per_call = sum(c["output_tokens"] for c in all_calls) / max(len(all_calls), 1)
        basis = f"média observada em {len(all_calls)} chamadas anteriores"
    else:
        prompt_chars = (ROOT / "app" / "prompts" / "malu_v4.md").stat().st_size
        chat_in = prompt_chars / _CHARS_PER_TOKEN + 1500  # + histórico médio
        in_per_call = (chat_in + 2000 * (calls_per_turn - 1)) / calls_per_turn
        out_per_call = 400
        basis = "chute pelo tamanho do prompt (sem piloto ainda)"
    tin, tout = calls * in_per_call, calls * out_per_call
    cost = (tin * price["input_per_m"] + tout * price["output_per_m"]) / 1_000_000
    return {"calls": calls, "tokens_in": int(tin), "tokens_out": int(tout), "cost_usd": cost, "basis": basis}


def load_prior(provider: str) -> list[dict]:
    rows: list[dict] = []
    for p in RESULTS.glob(f"*_{provider}.jsonl"):
        rows += [json.loads(x) for x in p.read_text(encoding="utf-8").splitlines() if x.strip()]
    return rows


def build_record(case: dict, provider: str, model: str, rep: int, run: str, turns: list) -> dict[str, Any]:
    from evals import metrics

    finalize_turn = next((i for i, t in enumerate(turns, 1) if t.finalized), None)
    finalized_data = turns[finalize_turn - 1].finalized[0] if finalize_turn else None
    replies = [r for t in turns for r in t.replies]
    calls = [c for t in turns for c in t.calls]
    price_cost = 0.0
    return {
        "run": run,
        "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "case_id": case["id"],
        "category": case["category"],
        "provider": provider,
        "model": model,
        "rep": rep,
        "n_turns": len(turns),
        "expect_finalize": bool(case.get("expect_finalize")),
        "finalize_turn": finalize_turn,
        "leads_created": sum(len(t.finalized) for t in turns),
        "finalized_data": finalized_data,
        "field_scores": metrics.score_fields(case.get("gold") or {}, finalized_data),
        "guard_pass": metrics.check_guard(case.get("guard"), replies, finalize_turn is not None),
        "price_guard_triggered": any(t.price_attempt for t in turns),
        "malu_error_turns": sum(1 for t in turns if "error" in t.models),
        "n_calls": len(calls),
        "n_call_errors": sum(1 for c in calls if c.error),
        "retries": sum(c.retries for c in calls),
        "prompt_tokens": sum(c.prompt_tokens for c in calls),
        "output_tokens": sum(c.output_tokens for c in calls),
        "cost_usd": price_cost,  # preenchido pelo chamador (precisa da tabela)
        "conv_llm_ms": sum(c.latency_ms or 0 for c in calls),
        "conv_wall_ms": sum(t.wall_ms for t in turns),
        "turns": [
            {
                "user": t.user,
                "replies": t.replies,
                "models": t.models,
                "finalized": bool(t.finalized),
                "notify": t.notify,
                "price_attempt": t.price_attempt,
                "wall_ms": round(t.wall_ms, 1),
                "calls": [asdict(c) for c in t.calls],
            }
            for t in turns
        ],
    }


async def run_provider(provider: str, args: argparse.Namespace, cfg: dict, pricing: dict) -> int:
    from app.config import settings
    from evals import harness, metrics

    model = cfg["providers"][provider]["model"]
    price = pricing[model]
    key = settings.gemini_api_key if provider == "gemini" else settings.groq_api_key
    k = args.k or int(cfg["k"])
    cases = load_cases(int(cfg["seed"]))
    if args.cases:
        wanted = set(args.cases.split(","))
        cases = [c for c in cases if c["id"] in wanted]
    if args.category:
        cases = [c for c in cases if c["category"] == args.category]
    if args.limit:
        cases = cases[: args.limit]

    out = results_path(args.run, provider)
    done = done_keys(out)
    todo = [(c, rep) for c in cases for rep in range(1, k + 1) if (c["id"], rep) not in done]
    est = estimate([c for c, _ in todo], 1, bool(cfg["coleta_state_enabled"]), price, load_prior(provider))
    print(f"\n=== {provider} / {model} · run {args.run}")
    print(f"pendentes: {len(todo)} (caso×rep) · já gravados: {len(done)}")
    print(
        f"estimativa: {est['calls']} chamadas · {est['tokens_in']:,} tokens de entrada · "
        f"{est['tokens_out']:,} de saída · US$ {est['cost_usd']:.2f} no preço pago ({est['basis']})"
    )
    if price.get("status") != "oficial":
        print(f"⚠️ preço de {model}: {price.get('status')} (ver evals/pricing.yaml)")
    if args.dry_run or not todo:
        return 0
    if not key:
        print(f"❌ chave de {provider} vazia no .env — preencha antes de rodar.")
        return 1
    if est["cost_usd"] > float(cfg["limits"]["max_cost_usd"]):
        print(f"❌ estimativa acima do teto (US$ {cfg['limits']['max_cost_usd']}) — reduza --limit ou ajuste o config.")
        return 1

    recorder = harness.install(provider, model, cfg, price)
    out.parent.mkdir(parents=True, exist_ok=True)
    for idx, (case, rep) in enumerate(todo, 1):
        print(f"[{idx}/{len(todo)}] {case['id']} ({case['category']}) rep {rep} …", flush=True)
        n0 = len(recorder.calls)
        try:
            turns = await harness.run_conversation(
                case, synthetic_phone(case["id"], rep), float(cfg["sleep_between_turns_s"])
            )
        except harness.QuotaExhausted as exc:
            del recorder.calls[n0:]  # caso incompleto não entra; --resume refaz
            print(f"⛔ rodada parada: {exc}\n   caso {case['id']} descartado; rode de novo com --run {args.run} pra continuar.")
            return 2
        rec = build_record(case, provider, model, rep, args.run, turns)
        rec["cost_usd"] = sum(
            metrics.call_cost_usd(c["prompt_tokens"], c["output_tokens"], price)
            for t in rec["turns"] for c in t["calls"]
        )
        with out.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
        fin = f"fechou no turno {rec['finalize_turn']}" if rec["finalize_turn"] else "não fechou"
        print(
            f"    {fin} · {rec['n_calls']} chamadas · {rec['prompt_tokens']:,}+{rec['output_tokens']:,} tokens"
            f" · US$ {rec['cost_usd']:.4f} · erros {rec['n_call_errors']}"
        )
        if idx < len(todo):
            await asyncio.sleep(float(cfg["sleep_between_cases_s"]))
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--provider", choices=["gemini", "groq", "all"], default="all")
    ap.add_argument("--run", default=date.today().isoformat(), help="id da rodada (padrão: data de hoje)")
    ap.add_argument("--cases", help="ids separados por vírgula")
    ap.add_argument("--category")
    ap.add_argument("--limit", type=int)
    ap.add_argument("--k", type=int, help="sobrescreve o k do config")
    ap.add_argument("--dry-run", action="store_true", help="só estima, não chama API")
    args = ap.parse_args()

    os.chdir(ROOT)  # o Settings lê o .env da raiz
    cfg, pricing = load_yaml("config.yaml"), load_yaml("pricing.yaml")
    providers = ["gemini", "groq"] if args.provider == "all" else [args.provider]
    t0 = time.time()
    code = 0
    for p in providers:
        code = max(code, asyncio.run(run_provider(p, args, cfg, pricing)))
    print(f"\nfim em {time.time() - t0:.0f}s")
    return code


if __name__ == "__main__":
    sys.exit(main())
