"""Rotas REST consumidas pelo frontend CRM (Next.js).

Todas as rotas exigem header `X-API-Key` (definido em CRM_API_KEY no .env).
Estrutura:
    /api/leads                — lista paginada com filtros
    /api/leads/{phone}        — detalhe (lead + cliente + histórico)
    /api/conversations        — lista de conversas com últimos timestamps
    /api/conversations/{phone}— histórico completo de mensagens
    /api/reservas             — lista de reservas
    /api/reservas             — POST criar nova reserva (manual pela Lu)
    /api/dashboard/metrics    — métricas agregadas pro dashboard
    /api/dashboard/insights   — séries temporais e agregados (Painel de Insights)
"""

from __future__ import annotations

from fastapi import APIRouter

from app.api import conversations, leads, metrics, reservas

api_router = APIRouter(prefix="/api")
api_router.include_router(leads.router)
api_router.include_router(conversations.router)
api_router.include_router(reservas.router)
api_router.include_router(metrics.router)
