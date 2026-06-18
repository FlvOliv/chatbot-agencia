"""Testes da trava de orçamento do piso pago (Mistral) — usa fakeredis."""

from __future__ import annotations

import pytest

from app import budget


@pytest.mark.asyncio
async def test_starts_at_zero() -> None:
    assert await budget.paid_tokens_used() == 0


@pytest.mark.asyncio
async def test_record_accumulates() -> None:
    await budget.record_paid_tokens(1000)
    await budget.record_paid_tokens(500)
    assert await budget.paid_tokens_used() == 1500


@pytest.mark.asyncio
async def test_record_ignores_non_positive() -> None:
    await budget.record_paid_tokens(0)
    await budget.record_paid_tokens(-5)
    assert await budget.paid_tokens_used() == 0


@pytest.mark.asyncio
async def test_cap_reached_when_at_or_over(monkeypatch) -> None:
    monkeypatch.setattr(budget.settings, "monthly_paid_token_cap", 1000)
    await budget.record_paid_tokens(1000)
    assert await budget.paid_floor_cap_reached() is True


@pytest.mark.asyncio
async def test_cap_not_reached_when_under(monkeypatch) -> None:
    monkeypatch.setattr(budget.settings, "monthly_paid_token_cap", 1000)
    await budget.record_paid_tokens(999)
    assert await budget.paid_floor_cap_reached() is False


@pytest.mark.asyncio
async def test_cap_disabled_when_non_positive(monkeypatch) -> None:
    """cap <= 0 = sem teto (nunca bloqueia) — o liga/desliga é PAID_FLOOR_ENABLED."""
    monkeypatch.setattr(budget.settings, "monthly_paid_token_cap", 0)
    await budget.record_paid_tokens(10_000_000)
    assert await budget.paid_floor_cap_reached() is False


def test_month_key_format() -> None:
    from datetime import datetime, timezone

    key = budget._month_key(datetime(2026, 6, 17, tzinfo=timezone.utc))
    assert key == "malu:paid_tokens:2026-06"
