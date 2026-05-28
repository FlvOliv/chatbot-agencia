# CLAUDE.md — Malu Bot · Lu Milhas & Viagens

> Este arquivo é lido automaticamente pelo Claude Code.
> Ele define o contexto completo do projeto, convenções e regras.

---

## O que é este projeto

**Malu** é uma assistente virtual de atendimento nível 1 da agência **Lu Milhas & Viagens**.

Ela funciona via **WhatsApp**, recebe clientes, coleta informações de viagem e gera um briefing estruturado para a Luciana (atendente humana) fechar a cotação.

- Integração: **Meta WhatsApp Cloud API** (oficial — sem risco de ban)
- IA principal: **Claude claude-sonnet-4-5** via API Anthropic
- IA fallback (opcional): **Gemma 3 via Ollama** (local, para mensagens simples)
- Backend: **FastAPI** (Python, async)
- Sessões: **Redis** (histórico de conversa por número, TTL 24h)
- Banco: **PostgreSQL** (leads, conversas, briefings)
- Fila: **Celery + Redis** (lembretes de follow-up)
- Deploy: **Railway.app** (ou Render)

---

## Stack e versões

```
Python        3.12+
FastAPI       0.115+
anthropic     0.30+
redis         5.x (asyncio)
SQLAlchemy    2.x (async)
Alembic       1.x
Celery        5.x
httpx         0.27+
pydantic      2.x
uvicorn       0.30+
python-dotenv 1.x
```

---

## Estrutura de diretórios (target)

```
malu-bot/
├── app/
│   ├── main.py              # FastAPI app + webhook endpoints
│   ├── whatsapp.py          # Cliente Meta Cloud API (send/receive)
│   ├── ai.py                # Router de modelos (Claude / Gemma)
│   ├── session.py           # Redis — histórico de conversa
│   ├── briefing.py          # Parser de briefing + notificação Luciana
│   ├── models.py            # SQLAlchemy ORM (Lead, Conversation)
│   ├── database.py          # Engine async + SessionLocal
│   ├── config.py            # Pydantic Settings (lê .env)
│   └── prompts/
│       └── malu_v4.md       # System prompt da Malu (NÃO ALTERAR)
├── workers/
│   └── tasks.py             # Tarefas Celery (follow-up, notificações)
├── alembic/
│   └── versions/            # Migrações geradas automaticamente
├── tests/
│   ├── test_webhook.py
│   ├── test_ai.py
│   ├── test_session.py
│   └── test_briefing.py
├── scripts/
│   └── seed_test.py         # Simula mensagens WhatsApp para teste local
├── .env.example             # Template de variáveis (sem secrets reais)
├── .env                     # Secrets reais (NO .gitignore)
├── .gitignore
├── docker-compose.yml       # PostgreSQL + Redis local
├── Dockerfile
├── requirements.txt
├── alembic.ini
└── README.md
```

---

## Variáveis de ambiente (.env)

```env
# Meta WhatsApp Cloud API
WA_TOKEN=your_permanent_access_token
WA_PHONE_ID=your_phone_number_id
WA_VERIFY_TOKEN=qualquer_string_aleatoria
WA_APP_SECRET=seu_app_secret_meta

# Anthropic
ANTHROPIC_API_KEY=sk-ant-...

# Banco e cache
DATABASE_URL=postgresql+asyncpg://malu:malu@localhost:5432/malu
REDIS_URL=redis://localhost:6379/0

# Negócio
LUCIANA_PHONE=5511999999999
BUSINESS_HOURS_START=9
BUSINESS_HOURS_END=18

# IA
AI_PRIMARY=claude          # "claude" | "openai" | "gemma"
AI_FALLBACK=gemma          # "gemma" | "none"
OLLAMA_URL=http://localhost:11434
```

---

## Schema do banco (PostgreSQL)

```sql
-- leads
CREATE TABLE leads (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    phone         TEXT NOT NULL UNIQUE,
    name          TEXT,
    destination   TEXT,
    travel_type   TEXT,
    lead_temp     TEXT CHECK (lead_temp IN ('frio','morno','quente','urgente')),
    briefing_md   TEXT,
    raw_data      JSONB DEFAULT '{}',
    notified_at   TIMESTAMPTZ,
    created_at    TIMESTAMPTZ DEFAULT now(),
    updated_at    TIMESTAMPTZ DEFAULT now()
);

-- conversations (log de auditoria)
CREATE TABLE conversations (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    phone       TEXT NOT NULL,
    role        TEXT CHECK (role IN ('user','assistant')),
    content     TEXT NOT NULL,
    model_used  TEXT,
    created_at  TIMESTAMPTZ DEFAULT now()
);
```

---

## Regras de código (SEGUIR SEMPRE)

1. **Sempre usar async/await** — FastAPI é async, SQLAlchemy async, Redis async.
2. **Nunca bloquear o event loop** — sem `time.sleep()`, sem I/O síncrono.
3. **Config via `app/config.py`** — nunca `os.getenv()` direto em módulos de negócio.
4. **Tratamento de erro** — toda chamada à API Meta e à IA deve ter try/except com log.
5. **Testes** — cada módulo novo deve ter pelo menos 1 teste em `tests/`.
6. **Sem secrets no código** — tudo via `.env`.
7. **Type hints** em todas as funções.
8. **Docstrings** em funções públicas.

---

## Fluxo principal de uma mensagem

```
1. Cliente manda mensagem no WhatsApp
2. Meta envia POST /webhook para o backend
3. Backend valida assinatura HMAC-SHA256
4. Extrai phone + texto da payload
5. Busca histórico no Redis (get_history)
6. Adiciona mensagem do usuário ao histórico
7. Chama ask_malu(history) → retorna resposta
8. Adiciona resposta ao histórico → salva no Redis
9. Envia resposta via Meta API
10. Verifica se resposta contém "## Resumo da Solicitação"
11. Se sim → salva lead no PostgreSQL + notifica Luciana via WhatsApp
```

---

## System prompt

O arquivo `app/prompts/malu_v4.md` contém o prompt completo da Malu.
**NÃO editar esse arquivo sem instrução explícita.**
Ele é injetado como `system` message em toda chamada à IA.

---

## Convenção de notificação para Luciana

Quando a Malu gerar um briefing completo (bloco `## Resumo da Solicitação de Cotação`),
o sistema deve:

1. Extrair o bloco markdown
2. Salvar na tabela `leads` (campo `briefing_md`)
3. Enviar mensagem WhatsApp para `LUCIANA_PHONE` no formato:

```
📋 *Novo lead — Malu*

📱 Cliente: +55 11 99999-9999
🌡 Temperatura: Quente

[conteúdo do briefing aqui]
```

---

## Como rodar localmente

```bash
# 1. Sobe postgres + redis
docker-compose up -d

# 2. Cria banco e roda migrations
alembic upgrade head

# 3. Inicia FastAPI
uvicorn app.main:app --reload --port 8000

# 4. Em outro terminal, expõe o webhook
ngrok http 8000

# 5. Cola a URL ngrok no Meta Developer Console
#    Webhook URL: https://XXXX.ngrok.io/webhook
#    Verify token: mesmo valor de WA_VERIFY_TOKEN no .env
```

---

## Testes

```bash
pytest tests/ -v
```

O arquivo `scripts/seed_test.py` simula uma conversa completa sem precisar
de WhatsApp real — útil para testar o fluxo de IA e o briefing.

---

## O que NÃO fazer

- Não usar `requests` (síncrono) — usar `httpx` async
- Não commitar `.env`
- Não alterar `app/prompts/malu_v4.md` sem instrução
- Não usar `print()` para debug — usar `logging`
- Não retornar erro 500 para a Meta (ela vai retentar e duplicar mensagens) — sempre retornar 200 e logar o erro internamente
