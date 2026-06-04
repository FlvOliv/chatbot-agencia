# Painel de Insights da Malu

Painel web (Plano Básico, MVP **read-only**) para a Lu acompanhar como a Malu
está atendendo no WhatsApp.

Consome o backend FastAPI deste mesmo repo (`../app`), incluindo o endpoint
`GET /api/dashboard/insights` (série diária de conversas/leads, top destinos,
distribuição horária, taxa de conversão e breakdown de IA).

## Telas

- `/` — dashboard com KPIs, conversas 7d, temperatura, destinos e conversão
- `/leads` — lista filtrável por temperatura e busca
- `/leads/[phone]` — detalhe de um lead + briefing + histórico
- `/configuracoes` — visualização das envs (sem edição)

## Rodar local

```bash
cp .env.local.example .env.local
# edite CRM_API_KEY com a mesma chave configurada no backend
npm install
npm run dev
```

Sobe em `http://localhost:3000`. O backend precisa estar de pé em
`NEXT_PUBLIC_API_BASE_URL` (default `http://localhost:8000`).

## Variáveis

- `NEXT_PUBLIC_API_BASE_URL` — URL do backend FastAPI
- `CRM_API_KEY` — chave usada em `X-API-Key`, **server-only** (nunca expor)
- `NEXT_PUBLIC_LUCIANA_PHONE`, `NEXT_PUBLIC_AI_PRIMARY`,
  `NEXT_PUBLIC_AI_FALLBACK`, `NEXT_PUBLIC_BUSINESS_HOURS_*` — exibidas em
  `/configuracoes`

## Fora de escopo

O painel é **read-only** por design. Não faz parte deste MVP:

- responder mensagens de cliente
- criar ou editar leads manualmente
- alterar conversas operacionais
- escrever no banco do backend

Tudo isso continua acontecendo no WhatsApp / no backend.

## Stack

Next.js 16 (App Router, server components), React 19, Tailwind v4,
Recharts, react-markdown. Sem state client além dos charts.
