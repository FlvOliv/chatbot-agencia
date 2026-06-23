"""Testes do resumo diário de leads (conteúdo). A query/envio é I/O fino."""

from __future__ import annotations

from app.reports import build_daily_report_body


def test_report_empty_day() -> None:
    body = build_daily_report_body("2026-06-22", {})
    assert "2026-06-22" in body
    assert "Nenhum lead novo" in body


def test_report_with_counts() -> None:
    body = build_daily_report_body("2026-06-22", {"quente": 2, "morno": 1})
    assert "Total: 3" in body
    assert "Quente: 2" in body
    assert "Morno: 1" in body
