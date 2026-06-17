"""Testes das funções puras dos callbacks.

  - render_callback: saudação com/sem nome
  - _compute_pre24h_target: alvo de tarde; 21h→19:59 mesmo dia; madrugada→19:59
    da véspera; sem horário válido (None); nunca ≥ C nem dentro do silêncio.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from app.callbacks import CALLBACK_30M, CALLBACK_PRE24H, render_callback
from app.reminders import _compute_pre24h_target, _in_quiet

TZ = ZoneInfo("America/Sao_Paulo")
QUIET_START = 20
QUIET_END = 8
BUFFER = 60  # minutos


def _dt(y, mo, d, h, mi=0, s=0):  # noqa: ANN001
    return datetime(y, mo, d, h, mi, s, tzinfo=TZ)


def _target(t0, now):  # noqa: ANN001
    return _compute_pre24h_target(t0, now, TZ, QUIET_START, QUIET_END, BUFFER)


# ---------------------------------------------------------------------------
# render_callback
# ---------------------------------------------------------------------------
def test_render_callback_with_name() -> None:
    out = render_callback(CALLBACK_30M, "Ana")
    assert out.startswith("Oi Ana!")
    assert "{saudacao}" not in out


def test_render_callback_without_name() -> None:
    out = render_callback(CALLBACK_PRE24H, None)
    assert out.startswith("Oi!")
    assert "{saudacao}" not in out


def test_render_callback_blank_name_falls_back() -> None:
    assert render_callback(CALLBACK_30M, "   ").startswith("Oi!")


# ---------------------------------------------------------------------------
# _compute_pre24h_target — cenários
# ---------------------------------------------------------------------------
def test_target_afternoon_is_kept() -> None:
    """Alvo de tarde (fora do silêncio): agenda no próprio alvo (C − buffer)."""
    t0 = _dt(2026, 6, 17, 15, 0)
    got = _target(t0, t0)
    assert got == _dt(2026, 6, 18, 14, 0)


def test_target_evening_quiet_pulled_to_1959_same_day() -> None:
    """Alvo às 21h (silêncio) → 19:59:59 do MESMO dia."""
    t0 = _dt(2026, 6, 17, 22, 0)  # C = 18/06 22:00, alvo = 21:00 (silêncio)
    got = _target(t0, t0)
    assert got == _dt(2026, 6, 18, 19, 59, 59)


def test_target_dawn_quiet_pulled_to_1959_previous_day() -> None:
    """Alvo de madrugada (silêncio) → 19:59:59 da VÉSPERA, dentro da janela."""
    t0 = _dt(2026, 6, 17, 4, 0)  # C = 18/06 04:00, alvo = 03:00 (silêncio)
    got = _target(t0, t0)
    assert got == _dt(2026, 6, 17, 19, 59, 59)


def test_target_none_when_already_past_buffer_point() -> None:
    """Sem horário válido (agora já passou do ponto de buffer) → None."""
    t0 = _dt(2026, 6, 16, 15, 0)  # C = 17/06 15:00, alvo = 14:00
    now = _dt(2026, 6, 17, 14, 45)  # já passou do alvo
    assert _target(t0, now) is None


def test_target_never_in_quiet_and_before_C() -> None:
    """Invariante: qualquer alvo retornado está fora do silêncio e antes de C."""
    for hour in range(0, 24):
        t0 = _dt(2026, 6, 17, hour, 0)
        got = _target(t0, t0)
        if got is None:
            continue
        c = t0 + timedelta(hours=24)
        assert got < c
        assert not _in_quiet(got, QUIET_START, QUIET_END)


def test_in_quiet_wraps_midnight() -> None:
    assert _in_quiet(_dt(2026, 6, 17, 23, 0), 20, 8) is True
    assert _in_quiet(_dt(2026, 6, 17, 3, 0), 20, 8) is True
    assert _in_quiet(_dt(2026, 6, 17, 12, 0), 20, 8) is False
    assert _in_quiet(_dt(2026, 6, 17, 8, 0), 20, 8) is False  # fim exclusivo
