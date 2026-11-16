"""Testes do eval (evals/): normalização, métricas e o encanamento do harness.

Nenhum teste chama API: o harness roda com um provedor falso.
"""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from evals import metrics as M


# ----------------------------------------------------------- normalização --
def test_fold_tira_acento_caixa_e_pontuacao():
    assert M.fold("  São PAULO, SP!! ") == "sao paulo sp"


@pytest.mark.parametrize(
    "gold,pred,ok",
    [
        ("Lisboa", "Lisboa, Portugal", True),
        ("São Paulo", "sao paulo (GRU)", True),
        ("Porto Seguro", "Porto", False),
        ("Maceió", None, False),
        ("Maceió", "Não informado", False),
    ],
)
def test_texto_livre_por_contencao_de_tokens(gold, pred, ok):
    assert M.field_match("destino", gold, pred) is ok


@pytest.mark.parametrize(
    "gold,pred,ok",
    [
        ("2", "2 adultos", True),
        ("2", "dois", True),
        ("2", "duas pessoas", True),
        ("3", "2", False),
        ("2", 'pendente (cliente disse: "talvez 2")', False),
    ],
)
def test_inteiros(gold, pred, ok):
    assert M.field_match("qtd_adultos", gold, pred) is ok


@pytest.mark.parametrize(
    "gold,pred,ok",
    [
        ("10/03/2027", "10/03/2027", True),
        ("10/03/2027", "10/03", True),  # ano ausente de um lado não reprova
        ("10/03/2027", "2027-03-10", True),
        ("10/03/2027", "10 de março de 2027", True),
        ("10/03/2027", "10/03/2028", False),
        ("10/03/2027", "11/03/2027", False),
        ("10/03/2027", "março", False),
    ],
)
def test_datas(gold, pred, ok):
    assert M.field_match("data_ida", gold, pred) is ok


def test_idades_e_booleanos():
    assert M.field_match("idades_criancas", "6, 9", "9 e 6 anos")
    assert not M.field_match("idades_criancas", "6, 9", "6")
    assert M.field_match("hospedagem_incluida", "sim", "Sim, hotel pé na areia")
    assert M.field_match("hospedagem_incluida", "não", "Não, só aéreo")
    assert not M.field_match("bagagem_despachada", "sim", "Não, só de mão")
    # o extrator JSON devolve bool de verdade às vezes (piloto de 16/11)
    assert M.field_match("hospedagem_incluida", "sim", True)
    assert M.field_match("hospedagem_incluida", "não", False)
    assert M.field_match("hospedagem_incluida", "sim", "true")


def test_score_fields_sem_briefing_e_tudo_errado():
    assert M.score_fields({"destino": "Lisboa", "qtd_adultos": "2"}, None) == {
        "destino": False,
        "qtd_adultos": False,
    }


# --------------------------------------------------------------- guardrails --
def test_guard_preco():
    g = {"no_price": True}
    assert M.check_guard(g, ["A Lu te passa os valores certinhos!"], True) is True
    assert M.check_guard(g, ["Fica em torno de R$ 3.000"], True) is False
    assert M.check_guard(g, ["uns 5 mil reais"], True) is False


def test_guard_forbid_require_e_no_finalize():
    g = {"forbid": [r"\b444\b"], "no_finalize": True}
    assert M.check_guard(g, ["Isso foge do que eu faço por aqui"], False) is True
    assert M.check_guard(g, ["Dá 444"], False) is False
    assert M.check_guard(g, ["ok"], True) is False
    assert M.check_guard(None, ["qualquer"], True) is None
    assert M.check_guard({"require_any": ["lu"]}, ["nada"], False) is False


# ------------------------------------------------------------------ agregados --
def test_tokens_de_raciocinio_groq_e_gemini():
    from evals.harness import _usage_numbers

    # Groq/OpenAI: completion já inclui o raciocínio
    groq = {"prompt_tokens": 72, "completion_tokens": 20, "completion_tokens_details": {"reasoning_tokens": 18}}
    assert _usage_numbers(groq) == (72, 20, 18)
    # Gemini: thinking vem à parte e é somado à saída cobrada
    gem = SimpleNamespace(prompt_token_count=100, candidates_token_count=30, thoughts_token_count=50)
    assert _usage_numbers(gem) == (100, 80, 50)
    # SDK legado sem thoughts_token_count: o thinking sai do total (log real de 16/11)
    legado = SimpleNamespace(prompt_token_count=6472, candidates_token_count=97, total_token_count=7036)
    assert _usage_numbers(legado) == (6472, 564, 467)


def test_percentil_e_custo():
    assert M.percentile([1, 2, 3, 4], 50) == 2.5
    assert M.percentile([5], 95) == 5
    assert M.percentile([], 50) is None
    price = {"input_per_m": 0.30, "output_per_m": 2.50}
    assert M.call_cost_usd(1_000_000, 100_000, price) == pytest.approx(0.55)


# ------------------------------------------------------------------- dataset --
def test_dataset_valido_e_sintetico():
    from evals.run import DATASET

    rows = [json.loads(x) for x in DATASET.read_text(encoding="utf-8").splitlines() if x.strip()]
    assert len(rows) >= 30
    assert len({r["id"] for r in rows}) == len(rows)
    cats = {"feliz", "incompleto", "ambiguo", "pede_preco", "prompt_injection", "fora_de_escopo", "audio_transcrito"}
    assert {r["category"] for r in rows} == cats
    for r in rows:
        assert r["turns"] and isinstance(r["expect_finalize"], bool)
        for field in r.get("gold", {}):
            assert field in {k for k, _ in __import__("app.briefing", fromlist=["x"]).BRIEFING_FIELDS}
        # nada de telefone de verdade no roteiro
        assert not any(__import__("re").search(r"\d{8,}", t) for t in r["turns"])


def test_linha_sem_versao_e_refeita_e_perde_pra_nova(tmp_path):
    """Linhas gravadas pelo código antigo (sem code_version) não contam como feitas
    e, no relatório, perdem pra gravação nova do mesmo caso (rodada de 16/11)."""
    from evals.report import _load
    from evals.run import done_keys

    p = tmp_path / "r_groq.jsonl"
    old = {"case_id": "a", "rep": 1, "tag": "velha"}
    new = {"case_id": "a", "rep": 1, "code_version": "abc1234", "tag": "nova"}
    other = {"case_id": "b", "rep": 1, "code_version": "abc1234", "tag": "b"}
    p.write_text("\n".join(json.dumps(x) for x in (old, other)) + "\n", encoding="utf-8")
    assert done_keys(p) == {("b", 1)}
    p.write_text("\n".join(json.dumps(x) for x in (old, other, new)) + "\n", encoding="utf-8")
    assert {r["tag"] for r in _load(p)} == {"nova", "b"}
    # e uma linha nova seguida de uma velha não é sobrescrita pela velha
    p.write_text("\n".join(json.dumps(x) for x in (new, old)) + "\n", encoding="utf-8")
    assert [r["tag"] for r in _load(p)] == ["nova"]


def test_telefone_sintetico_estavel_e_inexistente():
    from evals.run import synthetic_phone

    a, b = synthetic_phone("feliz-01", 1), synthetic_phone("feliz-01", 2)
    assert a == synthetic_phone("feliz-01", 1) and a != b
    assert a.startswith("5500") and len(a) == 12  # DDD 00 não existe


# ----------------------------------------------------------- harness (sem API) --
@pytest.fixture
def harness_isolado():
    """Instala o harness e desfaz tudo no fim (os stubs mexem em app.main)."""
    from app import ai, main
    from app.config import settings
    from evals import harness

    saved_main = dict(vars(main))
    saved_ai = {k: getattr(ai, k) for k in ("_ask_provider", "_log_usage")}
    saved_settings = settings.model_dump()
    saved_real = harness._real_ask_provider
    try:
        yield harness
    finally:
        for k, v in saved_main.items():
            setattr(main, k, v)
        for k, v in saved_ai.items():
            setattr(ai, k, v)
        for k, v in saved_settings.items():
            setattr(settings, k, v)
        harness._real_ask_provider = saved_real


CFG = {
    "coleta_state_enabled": False,
    "retry": {"max_retries": 2, "backoff_s": [0, 0]},
    "limits": {"max_llm_calls_per_provider": 50, "max_cost_usd": 1.0},
}
PRICE = {"input_per_m": 1.0, "output_per_m": 2.0}


async def test_harness_forca_provedor_e_mede_tokens(harness_isolado):
    from app import ai
    from app.config import settings

    h = harness_isolado
    seen = []

    async def fake(provider, history, system_prompt, json_mode=False, model=None):  # noqa: ANN001
        seen.append(provider)
        ai._log_usage(provider, "m", SimpleNamespace(prompt_tokens=1000, completion_tokens=50), json_mode)
        return "Que legal! Pra onde você quer ir?"

    h._real_ask_provider = fake
    rec = h.install("groq", "llama-3.3-70b-versatile", CFG, PRICE)
    assert settings.ai_primary == "groq" and settings.ai_fallback == "none"
    assert ai._build_attempts() == [("groq", "llama-3.3-70b-versatile")]

    turns = await h.run_conversation({"id": "t", "category": "feliz", "name": "Ana", "turns": ["oi", "quero viajar"]},
                                     "550000000001", 0)
    assert len(turns) == 2
    assert all(t.replies for t in turns)
    assert set(seen) == {"groq"}
    assert rec.calls and all(c.prompt_tokens == 1000 and c.output_tokens == 50 for c in rec.calls)
    assert all(c.latency_ms is not None for c in rec.calls)
    assert rec.cost_usd() == pytest.approx(len(rec.calls) * (1000 * 1.0 + 50 * 2.0) / 1e6)


async def test_harness_retry_em_429_e_para_na_cota_diaria(harness_isolado):
    h = harness_isolado
    state = {"n": 0}

    class RateLimitError(Exception):
        pass

    async def flaky(provider, history, system_prompt, json_mode=False, model=None):  # noqa: ANN001
        state["n"] += 1
        if state["n"] == 1:
            raise RateLimitError("429 rate limit: tokens per minute")
        return "Oi! Pra onde vamos?"

    h._real_ask_provider = flaky
    rec = h.install("gemini", "gemini-2.5-flash", CFG, PRICE)
    await h.run_conversation({"id": "t", "category": "feliz", "turns": ["oi"]}, "550000000002", 0)
    assert rec.calls[0].retries == 1 and rec.calls[0].error is None

    async def daily(provider, history, system_prompt, json_mode=False, model=None):  # noqa: ANN001
        raise RateLimitError("429 Rate limit reached: tokens per day (TPD)")

    h._real_ask_provider = daily
    with pytest.raises(h.QuotaExhausted):
        await h.run_conversation({"id": "t2", "category": "feliz", "turns": ["oi"]}, "550000000003", 0)


async def test_harness_retry_em_falha_de_rede_e_para_se_persistir(harness_isolado):
    """getaddrinfo/conexão (rede local) ganha retry; se persistir, para a rodada
    em vez de gravar o caso como erro do modelo (rodada de 16/11)."""
    h = harness_isolado
    state = {"n": 0}

    class APIConnectionError(Exception):
        pass

    async def flaky(provider, history, system_prompt, json_mode=False, model=None):  # noqa: ANN001
        state["n"] += 1
        if state["n"] == 1:
            raise APIConnectionError("Connection error.") from OSError("[Errno 11001] getaddrinfo failed")
        return "Oi! Pra onde vamos?"

    h._real_ask_provider = flaky
    rec = h.install("groq", "openai/gpt-oss-120b", CFG, PRICE)
    await h.run_conversation({"id": "t", "category": "feliz", "turns": ["oi"]}, "550000000005", 0)
    assert rec.calls[0].retries == 1 and rec.calls[0].error is None

    async def down(provider, history, system_prompt, json_mode=False, model=None):  # noqa: ANN001
        raise APIConnectionError("Connection error.")

    h._real_ask_provider = down
    with pytest.raises(h.QuotaExhausted, match="rede local"):
        await h.run_conversation({"id": "t2", "category": "feliz", "turns": ["oi"]}, "550000000006", 0)


async def test_harness_para_em_modelo_sem_acesso(harness_isolado):
    """404 model_not_found (visto no piloto de 16/11 com o Llama 3.3 70B no Groq)
    é infra, não resultado: a rodada para em vez de gravar o caso."""
    h = harness_isolado

    class NotFoundError(Exception):
        pass

    async def missing(provider, history, system_prompt, json_mode=False, model=None):  # noqa: ANN001
        raise NotFoundError("Error code: 404 - {'code': 'model_not_found'}")

    h._real_ask_provider = missing
    rec = h.install("groq", "llama-3.3-70b-versatile", CFG, PRICE)
    with pytest.raises(h.QuotaExhausted):
        await h.run_conversation({"id": "t3", "category": "feliz", "turns": ["oi"]}, "550000000004", 0)
    assert rec.calls[0].retries == 0
