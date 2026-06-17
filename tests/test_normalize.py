"""Testes da normalização de datas/quantidades do briefing (P1)."""

from __future__ import annotations

import pytest

from app.briefing import normalize_lead_data


def test_data_relativa_vira_pendente() -> None:
    """Data vaga não pode virar texto solto — vira pendente preservando o dito."""
    out = normalize_lead_data({"data_ida": "Novembro, perto do feriado"})
    assert out["data_ida"].startswith("pendente")
    assert "Novembro, perto do feriado" in out["data_ida"]


@pytest.mark.parametrize(
    "raw",
    ["12/11/2026", "15/11", "12-11-2026", "12 de novembro"],
)
def test_data_concreta_mantida(raw: str) -> None:
    assert normalize_lead_data({"data_ida": raw})["data_ida"] == raw


@pytest.mark.parametrize(
    "raw,esperado",
    [("2", "2"), ("2 adultos", "2"), ("duas", "2"), ("dois", "2")],
)
def test_qtd_coage_para_numero(raw: str, esperado: str) -> None:
    assert normalize_lead_data({"qtd_adultos": raw})["qtd_adultos"] == esperado


def test_qtd_nao_numerica_vira_pendente() -> None:
    out = normalize_lead_data({"qtd_adultos": "ainda não sei"})
    assert out["qtd_adultos"].startswith("pendente")


def test_qtd_criancas_zero() -> None:
    assert normalize_lead_data({"qtd_criancas": "0"})["qtd_criancas"] == "0"


def test_idades_viram_lista() -> None:
    out = normalize_lead_data({"idades_criancas": "5 e 8 anos"})
    assert out["idades_criancas"] == "5, 8"


def test_campo_nulo_continua_nulo() -> None:
    out = normalize_lead_data({"data_ida": None, "qtd_adultos": ""})
    assert out["data_ida"] is None
    assert out.get("qtd_adultos") in (None, "")
