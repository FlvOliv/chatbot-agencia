"""Indicação respondida espontaneamente pelo cliente não é reperguntada.

Origem: eval de 16/11/2026. O cliente disse "…ninguém me indicou" no 1º turno,
o extrator devolveu `indicado_por` nulo, e o gate mandou "alguém indicou a Lu
pra você?" no turno seguinte.
"""

from __future__ import annotations

import pytest

from app.briefing import gate_missing_fields, indicacao_respondida_pelo_cliente, normalize_lead_data


def _user(text: str) -> list[dict]:
    return [{"role": "user", "content": text}]


@pytest.mark.parametrize(
    "fala",
    [
        "Boa noite. Quero passagem e hotel em Buenos Aires, 2 adultos, ninguém me indicou",
        "Ninguém indicou, vi o perfil de vocês no Instagram",
        "ninguem indicou nao",
        "Não fui indicada por ninguém",
        "Fui indicado pela minha cunhada, a Patrícia",
        "Indicação da Juliana",
        "foi minha vizinha Cláudia que indicou vocês",
        "quem indicou foi o meu primo Anderson",
        "Vim sem indicação, achei no Google",
        "Fomos indicados pelo Rodrigo",
    ],
)
def test_reconhece_resposta_espontanea(fala):
    assert indicacao_respondida_pelo_cliente(_user(fala)) is True


@pytest.mark.parametrize(
    "fala",
    [
        "Você me indica um hotel bom em Palermo?",
        "Qual bairro você indica?",
        "Quem indicou vocês pra minha mãe?",
        "Indica algum passeio?",
        "Quero passagem pra Lisboa, 2 adultos",
        "",
    ],
)
def test_nao_confunde_pedido_de_indicacao_com_resposta(fala):
    assert indicacao_respondida_pelo_cliente(_user(fala)) is False


def test_fala_da_malu_nao_conta_como_resposta_do_cliente():
    hist = [{"role": "assistant", "content": "Ninguém indicou? Tudo bem!"}]
    assert indicacao_respondida_pelo_cliente(hist) is False


def _dados_completos() -> dict:
    return normalize_lead_data({"data_ida": "15/04/2027", "data_volta": "20/04/2027", "qtd_adultos": "2"})


def test_gate_nao_repergunta_quando_cliente_ja_disse_ninguem():
    hist = _user("saindo de Porto Alegre, ida 15/04/2027, volta 20/04/2027, 2 adultos, ninguém me indicou")
    assert gate_missing_fields(_dados_completos(), hist) == []


def test_gate_ainda_pede_indicacao_quando_ninguem_tocou_no_assunto():
    hist = _user("ida 15/04/2027, volta 20/04/2027, 2 adultos")
    assert gate_missing_fields(_dados_completos(), hist) == ["__indicacao__"]


def test_gate_ainda_pede_indicacao_se_cliente_so_pediu_dica():
    hist = _user("ida 15/04/2027, volta 20/04/2027, 2 adultos. Você me indica um hotel?")
    assert gate_missing_fields(_dados_completos(), hist) == ["__indicacao__"]
