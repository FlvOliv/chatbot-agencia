# CLAUDE.md — Malu Bot · Lu Milhas & Viagens

> Lido automaticamente pelo Claude Code. Contexto permanente, convenções e regras do projeto.
> Mantém factual. Não é diário de progresso.

---

## 1. Visão geral

**Malu** é a assistente virtual (nível 1) da agência **Lu Milhas & Viagens**. Atende clientes pelo **WhatsApp**, coleta os dados da viagem e gera um **briefing** estruturado para a **Luciana** (atendente humana) fechar a cotação. **Nunca menciona preços** (regra de negócio).

O projeto tem duas partes:
- **Backend (bot):** FastAPI que recebe o webhook da Meta, conversa via IA e persiste leads/conversas.
- **Painel CRM (`crm/`):** app Next.js para a Luciana ver dashboard, leads, conversas e **assumir o atendimento** (inbox / takeover).

---

## 2. Stack e dependências

| Camada | Tecnologia |
|---|---|
| Backend | Python **3.12** + FastAPI 0.115 (async) |
| IA principal | **Groq** `llama-3.3-70b-versatile` |
| IA fallback | **Google Gemini** `gemini-2.5-flash` (fallback automático em `app/ai.py`) |
| Sessão/histórico | **Redis** (asyncio) — em produção/dev usa **Upstash** (TLS `rediss://`) |
| Banco | **PostgreSQL** (SQLAlchemy 2 async + Alembic) — usa **Supabase** |
| Fila | **Celery 5** + Redis (lembretes de inatividade) |
| WhatsApp | **Meta WhatsApp Cloud API** (oficial — sem risco de ban) |
| Painel | **Next.js 16** (React, TypeScript) em `crm/` |
| HTTP | **httpx** async · validação **pydantic 2** · server **uvicorn** |

> **Importante:** **NÃO** usamos Anthropic/Claude nem Ollama no runtime (o `ai.py` é Groq + Gemini). Gemini free tem limite de **~20 req/dia** — por isso **Groq é o principal**.

---

## 3. Estrutura de pastas

```
app/
  main.py          # FastAPI + /webhook + pipeline (handle_message)
  ai.py            # Router de IA: Groq/Gemini + fallback automático (route_and_ask)
  whatsapp.py      # Cliente Meta Cloud API (parse_incoming, send_message)
  session.py       # Redis: histórico + estado da conversa (STATE_TRANSFERRED)
  briefing.py      # Extrai briefing, salva lead, notifica Luciana
  clientes.py      # get_or_create_cliente, nome preferido
  reservas.py      # checagem de reserva ativa
  reminders.py     # agenda/cancela lembretes (Celery)
  commands.py      # comandos (/sair), intents (1/2), respostas fixas
  models.py        # ORM: Lead, Conversation, Cliente, Reserva
  database.py      # engine async + SessionLocal + get_session
  config.py        # Pydantic Settings (lê .env) — fonte única de config
  api/             # Rotas REST do painel (todas /api/*, exigem X-API-Key)
    leads.py · conversations.py · metrics.py · reservas.py · auth.py · schemas.py
  prompts/malu_v4.md   # System prompt da Malu (NÃO EDITAR sem instrução)
workers/tasks.py   # Celery (lembretes + relatório diário)
alembic/versions/  # Migrations (0001_initial, 0002_clientes, 0003_reservas)
tests/             # pytest (test_api, test_commands, test_insights, test_reminders, ...)
scripts/
  demo_chat.py     # Chat interativo no terminal com a Malu (sem WhatsApp)
  sim_cliente.py   # Simula um cliente pelo pipeline REAL (popula o banco)
  check_setup.py · seed_test.py
crm/               # Painel Next.js (app/, components/, lib/)
  lib/api.ts       # cliente da API FastAPI (usa CRM_API_KEY server-side)
  app/             # páginas: / (dashboard), /leads, /conversas, /configuracoes
```

---

## 4. Ambiente de desenvolvimento (realidade atual)

- **SO:** Windows + **Git Bash** (MINGW64). Comandos em bash (`rm -rf`, `source`).
- **venv Python 3.12** — criar com `py -3.12 -m venv venv`. **NÃO usar 3.14** (asyncpg/pydantic-core não compilam).
- **Docker está DESCARTADO** nesta máquina (virtualização desligada na BIOS + 4GB RAM). Por isso Postgres/Redis vêm da **nuvem** (Supabase/Upstash), não do `docker-compose`.
- **Sempre** rodar Python com `export PYTHONUTF8=1` (scripts usam emoji; sem isso dá `UnicodeEncodeError` no console do Windows).
- **`.env`** (raiz) e **`crm/.env.local`** contêm segredos e **estão no `.gitignore`** — nunca commitar.

---

## 5. Comandos essenciais

```bash
# --- backend (na raiz, venv ativo) ---
source venv/Scripts/activate
export PYTHONUTF8=1
alembic upgrade head                       # migrations
uvicorn app.main:app --port 8000           # API (/health, /webhook, /api/*)
python -m pytest tests/ -q                 # testes (135 verdes)
python scripts/sim_cliente.py              # popula o banco simulando um cliente
ngrok http 8000                            # expõe o webhook (precisa authtoken)

# --- worker de lembretes ---
celery -A workers.tasks worker --beat --loglevel=info

# --- painel CRM (em crm/) ---
npm install
npm run dev      # http://localhost:3000
npm run build    # validação de build (pré-deploy)
npm run lint
```

`crm/.env.local` precisa de `NEXT_PUBLIC_API_BASE_URL=http://localhost:8000` e `CRM_API_KEY` (a mesma do backend).

---

## 6. Convenções de código

1. **async/await sempre** — FastAPI, SQLAlchemy e Redis são async. Nunca bloquear o event loop (sem `time.sleep`, sem I/O síncrono).
2. **Config só via `app/config.py`** (`settings`) — nunca `os.getenv()` em módulos de negócio.
3. **HTTP com `httpx` async** — nunca `requests`.
4. **`logging`, nunca `print()`** no código de runtime (scripts de demo podem imprimir).
5. **Toda chamada à Meta e à IA** com `try/except` + log.
6. **Type hints** em todas as funções; **docstrings** nas públicas.
7. **Cada módulo novo** com ao menos 1 teste em `tests/`.
8. **Webhook sempre responde 200** (exceto assinatura inválida → 401). Erro interno é logado, nunca propagado (senão a Meta reentrega e duplica).
9. **Schemas Pydantic** controlam o que sai na API; `id` UUID → usar o tipo `StrId` (coage para string).
10. Comentários e mensagens em **PT-BR** (padrão do repo).

---

## 7. Regras e preferências (SEMPRE / NUNCA)

- **NUNCA** commitar `.env`, `crm/.env.local` ou qualquer segredo.
- **NUNCA** editar `app/prompts/malu_v4.md` sem instrução explícita.
- **NUNCA** assumir Docker nesta máquina — usar nuvem (Supabase/Upstash).
- **SEMPRE** `AI_PRIMARY=groq`, `AI_FALLBACK=gemini` (Gemini free é limitado).
- **SEMPRE** explicar passos de forma simples e, para ações fora do terminal (Meta, Supabase, Vercel, etc.), dar instruções **clique a clique** — o dono do projeto (Flávio) não programa.
- **Colaboração git:** Flávio não tem escrita direta no repo do Gustavo (`origin = gustavomarcelloprf/chatbot-agencia`). Enviar mudanças pelo **fork** (`FlvOliv/chatbot-agencia`) → **Pull Request**.

---

## 8. Estado/limitação conhecida (crítica)

O bot está validado ponta a ponta **localmente**, mas o **envio físico no WhatsApp está bloqueado**: a conta usa o **número de teste da Meta** (`+1 555…`), que **não entrega no Brasil** (erro **130497** — restrição de país do sandbox). Para ir ao ar é preciso registrar um **número real e dedicado** no app `luma-bot` (App ID `1527584538749277`), o que muda `WA_PHONE_ID`/`WA_BUSINESS_ACCOUNT_ID`/`WA_TOKEN`. Sem isso, nada chega ao cliente.

---

## 9. Fluxo de uma mensagem (resumo)

`POST /webhook` → valida assinatura HMAC → `handle_message`: detecta não-texto → comando `/sair` → estado `transferred` (humano assumiu → bot calado) → identifica cliente → intent (1 reserva / 2 nova) → **IA** (`route_and_ask`) → envia resposta → se houver bloco `## Resumo da Solicitação de Cotação`, salva **lead** e **notifica a Luciana**.
