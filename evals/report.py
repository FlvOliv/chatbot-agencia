"""Gera evals/results/summary.md a partir dos .jsonl de uma rodada.

    python -m evals.report --run 2026-11-16
    python -m evals.report --run 2026-11-16 --partial   # só imprime, não grava

Sem --partial, recusa gerar o summary se a rodada estiver incompleta
(algum caso × repetição faltando em algum provedor): eval pela metade não
vira tabela publicada.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except Exception:  # noqa: BLE001
        pass

import yaml  # noqa: E402

from evals import metrics as M  # noqa: E402
from evals.run import DATASET, EVALS_DIR, RESULTS, results_path  # noqa: E402

GUARD_CATS = ("pede_preco", "prompt_injection", "fora_de_escopo")


def _load(path: Path) -> list[dict]:
    if not path.exists():
        return []
    rows = [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x.strip()]
    dedup = {(r["case_id"], r["rep"]): r for r in rows}  # última gravação vence
    return list(dedup.values())


def _fmt(v: float | None, spec: str = ".1f", suffix: str = "") -> str:
    return "—" if v is None else f"{v:{spec}}{suffix}"


def provider_stats(rows: list[dict]) -> dict[str, Any]:
    calls = [c for r in rows for t in r["turns"] for c in t["calls"]]
    ok_lat = [c["latency_ms"] / 1000 for c in calls if c["latency_ms"] is not None and not c["error"]]
    chat_lat = [c["latency_ms"] / 1000 for c in calls if c["kind"] == "chat" and c["latency_ms"] and not c["error"]]

    # Acerto de campos só nos casos que DEVIAM gerar briefing (os que não deviam
    # fechar entram em "fecho indevido" e nos guardrails, não aqui).
    closers = [r for r in rows if r["expect_finalize"]]
    closed = [r for r in closers if r["finalize_turn"]]
    field_hits: dict[str, list[bool]] = defaultdict(list)
    for r in closers:
        for f, hit in r["field_scores"].items():
            field_hits[f].append(hit)
    per_field = {f: 100 * sum(h) / len(h) for f, h in sorted(field_hits.items())}
    cond_hits = [h for r in closed for h in r["field_scores"].values()]

    guards: dict[str, list[bool]] = defaultdict(list)
    for r in rows:
        if r["guard_pass"] is not None:
            guards[r["category"]].append(bool(r["guard_pass"]))

    # Variação entre repetições: desvio-padrão, por caso, do acerto de campos.
    by_case: dict[str, list[float]] = defaultdict(list)
    for r in closers:
        s = r["field_scores"]
        if s:
            by_case[r["case_id"]].append(100 * sum(s.values()) / len(s))
    spreads = [M.stdev(v) for v in by_case.values() if len(v) > 1]

    return {
        "n_rows": len(rows),
        "per_field": per_field,
        "field_mean": M.mean(per_field.values()),
        "field_mean_closed": 100 * sum(cond_hits) / len(cond_hits) if cond_hits else None,
        "complete_pct": 100 * len(closed) / len(closers) if closers else None,
        "turns_mean": M.mean(r["finalize_turn"] for r in closed),
        "turns_median": M.median(r["finalize_turn"] for r in closed),
        "guards": {c: 100 * sum(v) / len(v) for c, v in guards.items()},
        "guard_all": (100 * sum(sum(v) for v in guards.values()) / sum(len(v) for v in guards.values()))
        if guards else None,
        "false_close": sum(1 for r in rows if not r["expect_finalize"] and r["finalize_turn"]),
        "duplicate_leads": sum(1 for r in rows if r["leads_created"] > 1),
        "truncated_chat": sum(r.get("truncated_chat", 0) for r in rows),
        "cost_mean": M.mean(r["cost_usd"] for r in rows),
        "tin_mean": M.mean(r["prompt_tokens"] for r in rows),
        "tout_mean": M.mean(r["output_tokens"] for r in rows),
        "lat_p50": M.percentile(ok_lat, 50),
        "lat_p95": M.percentile(ok_lat, 95),
        "chat_p50": M.percentile(chat_lat, 50),
        "chat_p95": M.percentile(chat_lat, 95),
        "conv_p50": M.percentile((r["conv_llm_ms"] / 1000 for r in rows), 50),
        "conv_p95": M.percentile((r["conv_llm_ms"] / 1000 for r in rows), 95),
        "n_calls": len(calls),
        "err_pct": 100 * sum(1 for c in calls if c["error"]) / len(calls) if calls else None,
        "retries": sum(c["retries"] for c in calls),
        "spread_mean": M.mean(s for s in spreads if s is not None) if spreads else None,
    }


def render(run: str, stats: dict[str, dict], cfg: dict, pricing: dict, n_cases: int, partial: bool) -> str:
    provs = list(stats)
    head = "| Métrica | " + " | ".join(f"{p} ({cfg['providers'][p]['model']})" for p in provs) + " |"
    sep = "|---|" + "---|" * len(provs)

    def row(label: str, key: str, spec: str = ".1f", suffix: str = "") -> str:
        return f"| {label} | " + " | ".join(_fmt(stats[p][key], spec, suffix) for p in provs) + " |"

    lines = [
        f"# Eval comparativo da Malu: rodada {run}" + (" (PARCIAL, não publicar)" if partial else ""),
        "",
        f"N = {n_cases} conversas sintéticas · k = {cfg['k']} · linhas por provedor: "
        + ", ".join(f"{p} {stats[p]['n_rows']}" for p in provs),
        "",
        head,
        sep,
        row("Acerto médio por campo (casos que deviam fechar)", "field_mean", suffix="%"),
        row("Acerto por campo (só conversas que fecharam)", "field_mean_closed", suffix="%"),
        row("Briefing completo (casos que deviam fechar)", "complete_pct", suffix="%"),
        row("Turnos até o briefing: média", "turns_mean"),
        row("Turnos até o briefing: mediana", "turns_median"),
        row("Guardrails: pass geral", "guard_all", suffix="%"),
        row("Fecho indevido (casos que não deviam fechar)", "false_close", "d"),
        row("Conversas com lead duplicado", "duplicate_leads", "d"),
        row("Respostas de chat cortadas no teto (finish_reason=length)", "truncated_chat", "d"),
        row("Tokens de entrada por conversa", "tin_mean", ",.0f"),
        row("Tokens de saída por conversa (inclui thinking)", "tout_mean", ",.0f"),
        row("Custo por conversa (US$)", "cost_mean", ".4f"),
        row("Latência por chamada de LLM p50 (s)", "lat_p50", ".2f"),
        row("Latência por chamada de LLM p95 (s)", "lat_p95", ".2f"),
        row("Latência da resposta (chat) p50 (s)", "chat_p50", ".2f"),
        row("Latência da resposta (chat) p95 (s)", "chat_p95", ".2f"),
        row("Tempo de LLM por conversa p50 (s)", "conv_p50", ".1f"),
        row("Tempo de LLM por conversa p95 (s)", "conv_p95", ".1f"),
        row("Erro de API/timeout (% das chamadas)", "err_pct", suffix="%"),
        row("Retries por rate limit", "retries", "d"),
        row("Variação entre repetições (desvio do acerto, p.p.)", "spread_mean"),
        "",
        "## Guardrails por categoria",
        "",
        "| Categoria | " + " | ".join(provs) + " |",
        "|---|" + "---|" * len(provs),
    ]
    cats = sorted({c for p in provs for c in stats[p]["guards"]})
    for c in cats:
        lines.append(f"| {c} | " + " | ".join(_fmt(stats[p]["guards"].get(c), suffix="%") for p in provs) + " |")
    lines += ["", "## Acerto por campo", "", "| Campo | " + " | ".join(provs) + " |", "|---|" + "---|" * len(provs)]
    fields = sorted({f for p in provs for f in stats[p]["per_field"]})
    for f in fields:
        lines.append(f"| {f} | " + " | ".join(_fmt(stats[p]["per_field"].get(f), suffix="%") for p in provs) + " |")
    lines += ["", "## Preços usados", ""]
    for p in provs:
        m = cfg["providers"][p]["model"]
        pr = pricing[m]
        lines.append(
            f"- `{m}`: US$ {pr['input_per_m']}/M entrada, US$ {pr['output_per_m']}/M saída · "
            f"{pr['status']} · {pr['source']} (consultado em {pr['checked']})"
        )
    lines += [
        "",
        "## Configuração",
        "",
        "```yaml",
        yaml.safe_dump(cfg, allow_unicode=True, sort_keys=False).strip(),
        "```",
        "",
        "Limitações: ver evals/README.md (dados sintéticos, N pequeno, turnos roteirizados, "
        "preço na data da consulta, temperatura diferente entre os caminhos de produção).",
    ]
    return "\n".join(lines) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--run", required=True)
    ap.add_argument("--partial", action="store_true", help="aceita rodada incompleta; só imprime")
    args = ap.parse_args()

    cfg = yaml.safe_load((EVALS_DIR / "config.yaml").read_text(encoding="utf-8"))
    pricing = yaml.safe_load((EVALS_DIR / "pricing.yaml").read_text(encoding="utf-8"))
    case_ids = [json.loads(x)["id"] for x in DATASET.read_text(encoding="utf-8").splitlines() if x.strip()]
    expected = len(case_ids) * int(cfg["k"])

    stats: dict[str, dict] = {}
    missing = []
    for p in cfg["providers"]:
        rows = _load(results_path(args.run, p))
        if len(rows) < expected:
            missing.append(f"{p}: {len(rows)}/{expected}")
        if rows:
            stats[p] = provider_stats(rows)
    if not stats:
        print(f"nenhum resultado para a rodada {args.run}")
        return 1
    if missing and not args.partial:
        print("rodada incompleta (" + "; ".join(missing) + "). Use --partial pra só visualizar.")
        return 1
    text = render(args.run, stats, cfg, pricing, len(case_ids), partial=bool(missing))
    if missing:
        print(text)
        return 0
    out = RESULTS / "summary.md"
    out.write_text(text, encoding="utf-8")
    print(f"gravado: {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
