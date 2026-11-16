"""Harness do eval: o pipeline REAL da Malu com I/O externo stubbado.

Reaproveita os stubs da suíte de conformidade (`scripts/conformance_probe.py`):
nada sai pra Meta nem pra Lu, a sessão roda em fakeredis e o Postgres é
falso. Por cima disso, este módulo:

- força UM provedor por rodada (só em memória: o `settings` do processo do
  eval; nada de `.env` nem de código de produção muda);
- instrumenta cada chamada de LLM por monkeypatch em `app.ai._ask_provider`
  (latência do round-trip, retry em 429) e `app.ai._log_usage` (tokens).
"""

from __future__ import annotations

import asyncio
import contextvars
import time
from dataclasses import dataclass, field
from typing import Any

from fakeredis import aioredis as fakeredis_aio

from app import ai, main, session
from app.config import settings
from scripts import conformance_probe as probe


class QuotaExhausted(BaseException):
    """Cota diária do provedor acabou, ou trava de chamadas/custo do eval: para a rodada.

    Herda de BaseException DE PROPÓSITO: `route_and_ask`, `extract_lead_data` e
    o `_process_text_message` capturam `Exception` (produção degrada pra
    "probleminha técnico"). Aqui a rodada tem que PARAR, e não virar um caso
    cheio de erro que contaminaria a métrica.
    """


_DAILY_MARKERS = ("per day", "tokens per day", "tpd", "requests per day", "rpd", "perday")


def _is_network(exc: BaseException) -> bool:
    """Falha de rede do lado do cliente (DNS, conexão recusada). Visto na rodada de
    16/11: `getaddrinfo failed` no Groq virou 'IA indisponível' e quebraria o caso.
    Timeout e 5xx NÃO entram aqui: são do provedor e contam em % de erro."""
    chain: list[BaseException] = []
    cur: BaseException | None = exc
    while cur is not None and len(chain) < 6:
        chain.append(cur)
        cur = cur.__cause__ or cur.__context__
    for e in chain:
        name = type(e).__name__.lower()
        if "connecterror" in name or "apiconnectionerror" in name or "gaierror" in name:
            return True
        if "getaddrinfo" in str(e).lower():
            return True
    return False


def _is_rate_limit(exc: BaseException) -> bool:
    name = type(exc).__name__.lower()
    text = str(exc).lower()
    return "ratelimit" in name or "resourceexhausted" in name or "429" in text or "rate limit" in text


def _is_daily_quota(exc: BaseException) -> bool:
    text = str(exc).lower().replace("_", " ")
    return _is_rate_limit(exc) and any(m in text for m in _DAILY_MARKERS)


def _is_fatal_setup(exc: BaseException) -> bool:
    """Modelo inexistente/sem acesso ou chave inválida: não é resultado do modelo,
    é infra. A rodada para em vez de gravar um caso cheio de erro."""
    name = type(exc).__name__.lower()
    text = str(exc).lower()
    return (
        "notfound" in name
        or "model_not_found" in text
        or "authentication" in name
        or "permissiondenied" in name
        or "api key not valid" in text
        or "invalid_api_key" in text
    )


@dataclass
class CallLog:
    """Uma chamada lógica de LLM (pode ter tido retries)."""

    provider: str
    model: str | None
    kind: str  # "chat" | "extract"
    latency_ms: float | None = None  # só a tentativa final, round-trip da API
    prompt_tokens: int = 0
    output_tokens: int = 0  # completion + thinking (o que é cobrado como saída)
    thinking_tokens: int = 0
    retries: int = 0
    error: str | None = None


@dataclass
class Recorder:
    """Acumula as chamadas da rodada e aplica as travas de cota e custo."""

    max_calls: int
    max_cost_usd: float
    price: dict[str, Any]
    retry_backoff_s: list[int]
    calls: list[CallLog] = field(default_factory=list)

    def cost_usd(self) -> float:
        return sum(
            (c.prompt_tokens * self.price["input_per_m"] + c.output_tokens * self.price["output_per_m"])
            / 1_000_000
            for c in self.calls
        )


_current: contextvars.ContextVar[CallLog | None] = contextvars.ContextVar("eval_call", default=None)
_recorder: Recorder | None = None

_real_ask_provider = ai._ask_provider
_real_log_usage = ai._log_usage


def _usage_numbers(usage: Any) -> tuple[int, int, int]:
    """(prompt, saída cobrada, thinking) de um objeto usage Groq ou Gemini."""
    if usage is None:
        return 0, 0, 0
    if isinstance(usage, dict):
        get = usage.get
    else:
        def get(k, d=None):  # noqa: ANN001, ANN202
            return getattr(usage, k, d)
    prompt = get("prompt_tokens", None)
    if prompt is None:
        prompt = get("prompt_token_count", 0)
    completion = get("completion_tokens", None)
    if completion is not None:
        # Estilo OpenAI/Groq: completion_tokens JÁ inclui o raciocínio
        # (completion_tokens_details.reasoning_tokens só detalha).
        details = get("completion_tokens_details", None) or {}
        reasoning = details.get("reasoning_tokens", 0) if isinstance(details, dict) else getattr(details, "reasoning_tokens", 0)
        return int(prompt or 0), int(completion or 0), int(reasoning or 0)
    # Gemini: candidates_token_count NÃO inclui o thinking, que é cobrado como saída.
    # O SDK google.generativeai (legado) não expõe thoughts_token_count: o thinking
    # aparece só no total (visto em 16/11: prompt 6472 + candidates 97 ≠ total 7036).
    # Sem o campo, thinking = total - prompt - candidates.
    completion = int(get("candidates_token_count", 0) or 0)
    prompt = int(prompt or 0)
    thinking = int(get("thoughts_token_count", 0) or 0)
    if not thinking:
        total = int(get("total_token_count", 0) or 0)
        thinking = max(total - prompt - completion, 0)
    return prompt, completion + thinking, thinking


def _traced_log_usage(provider: str, model: str, usage: Any, json_mode: bool = False) -> None:
    _real_log_usage(provider, model, usage, json_mode)
    rec = _current.get()
    if rec is not None:
        p, o, t = _usage_numbers(usage)
        rec.prompt_tokens, rec.output_tokens, rec.thinking_tokens = p, o, t


async def _traced_ask_provider(
    provider: str,
    history: list[dict],
    system_prompt: str,
    json_mode: bool = False,
    model: str | None = None,
) -> str:
    assert _recorder is not None
    r = _recorder
    if len(r.calls) >= r.max_calls:
        raise QuotaExhausted(f"trava do eval: {r.max_calls} chamadas por execução")
    if r.cost_usd() > r.max_cost_usd:
        raise QuotaExhausted(f"trava do eval: custo estimado passou de US$ {r.max_cost_usd:.2f}")

    rec = CallLog(provider=provider, model=model, kind="extract" if json_mode else "chat")
    r.calls.append(rec)
    attempt = 0
    while True:
        token = _current.set(rec)
        t0 = time.perf_counter()
        try:
            out = await _real_ask_provider(provider, history, system_prompt, json_mode=json_mode, model=model)
            rec.latency_ms = (time.perf_counter() - t0) * 1000
            rec.error = None
            return out
        except Exception as exc:  # noqa: BLE001
            rec.latency_ms = (time.perf_counter() - t0) * 1000
            rec.error = f"{type(exc).__name__}: {str(exc)[:300]}"
            if _is_daily_quota(exc) or _is_fatal_setup(exc):
                raise QuotaExhausted(rec.error) from exc
            if (_is_rate_limit(exc) or _is_network(exc)) and attempt < len(r.retry_backoff_s):
                await asyncio.sleep(r.retry_backoff_s[attempt])
                attempt += 1
                rec.retries = attempt
                continue
            if _is_network(exc):
                # A rede DESTA máquina caiu (DNS, conexão): não é erro do modelo.
                # Para a rodada; o --run refaz o caso depois.
                raise QuotaExhausted(f"rede local: {rec.error}") from exc
            raise
        finally:
            _current.reset(token)


def install(provider: str, model: str, cfg: dict[str, Any], price: dict[str, Any]) -> Recorder:
    """Liga stubs + instrumentação e força a cadeia a ter só `provider`."""
    global _recorder
    probe._install_stubs()
    ai._ask_provider = _traced_ask_provider  # type: ignore[assignment]
    ai._log_usage = _traced_log_usage  # type: ignore[assignment]

    # Atribuição direta pula a validação Literal do pydantic (mesmo truque da
    # suíte de conformidade). Só neste processo.
    settings.ai_primary = provider  # type: ignore[assignment]
    settings.ai_fallback = "none"  # type: ignore[assignment]
    settings.cerebras_api_key = ""
    settings.paid_floor_enabled = False
    settings.groq_fallback_model = ""
    if provider == "gemini":
        settings.gemini_model = model
    else:
        settings.groq_model = model
    settings.coleta_state_enabled = bool(cfg.get("coleta_state_enabled", True))

    _recorder = Recorder(
        max_calls=int(cfg["limits"]["max_llm_calls_per_provider"]),
        max_cost_usd=float(cfg["limits"]["max_cost_usd"]),
        price=price,
        retry_backoff_s=list(cfg["retry"]["backoff_s"])[: int(cfg["retry"]["max_retries"])],
    )
    return _recorder


@dataclass
class TurnResult:
    user: str
    replies: list[str]
    models: list[str]
    finalized: list[dict]
    notify: list[str]
    price_attempt: bool
    calls: list[CallLog]
    wall_ms: float


async def run_conversation(
    case: dict[str, Any], phone: str, sleep_between_turns_s: float
) -> list[TurnResult]:
    """Roda os turnos roteirizados de um caso numa sessão nova (fakeredis limpo)."""
    assert _recorder is not None
    session.set_redis_client(fakeredis_aio.FakeRedis(decode_responses=True))
    from_audio = case.get("category") == "audio_transcrito"
    turns: list[TurnResult] = []
    for i, msg in enumerate(case["turns"]):
        if i:
            await asyncio.sleep(sleep_between_turns_s)
        probe.SIG.clear()
        first_call = len(_recorder.calls)
        t0 = time.perf_counter()
        await main._process_text_message(phone, msg, case.get("name"), from_audio=from_audio)
        wall = (time.perf_counter() - t0) * 1000
        turns.append(
            TurnResult(
                user=msg,
                replies=list(probe.SIG.get("sent", [])),
                models=[r.get("model") for r in probe.SIG.get("routes", [])],
                finalized=list(probe.SIG.get("finalized", [])),
                notify=list(probe.SIG.get("notify", [])),
                price_attempt=bool(probe.SIG.get("price_attempt")),
                calls=list(_recorder.calls[first_call:]),
                wall_ms=wall,
            )
        )
    return turns
