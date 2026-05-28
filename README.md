# Malu Bot — Lu Milhas & Viagens

Assistente virtual de atendimento nível 1 da agência **Lu Milhas & Viagens**.
Atende clientes via WhatsApp, coleta informações de viagem e gera um briefing estruturado para a Luciana (atendente humana) fechar a cotação.

- Integração oficial via **Meta WhatsApp Cloud API** (sem risco de banimento)
- **Arquitetura multi-provider de IA** com switch dinâmico via `.env`:
  - Primário: **Google Gemini 2.5 Flash** (camada gratuita do AI Studio)
  - Stand-by: **Groq Llama 3.3 70B** (camada gratuita generosa — ativar com `AI_PRIMARY=groq` no `.env`)
- Backend: **FastAPI** async · **PostgreSQL 16** · **Redis 7** · **Celery**
- Persona da Malu definida em `app/prompts/malu_v4.md` — inclui regras anti-preço, anti-prompt-injection, filtro off-topic e tabela de temperatura do lead

---

## Pré-requisitos

- Python **3.12+**
- Docker + Docker Compose (para Postgres e Redis locais)
- Conta no **Meta for Developers** com um App de WhatsApp Business
- API key do **Google AI Studio** (https://aistudio.google.com/app/apikey) — gratuita
- *(opcional/stand-by)* API key da **Groq** (https://console.groq.com/keys) — gratuita
- `ngrok` (ou tunnel equivalente) para expor o webhook em dev

---

## Setup local

### 1. Clone e prepare o ambiente

```bash
git clone https://github.com/gustavomarcelloprf/chatbot-agencia.git malu-bot
cd malu-bot
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

### 2. Configure variáveis

```bash
cp .env.example .env
# edite .env com seus secrets reais:
#   WA_TOKEN, WA_PHONE_ID, WA_APP_SECRET, WA_VERIFY_TOKEN
#   GEMINI_API_KEY (e/ou GROQ_API_KEY)
#   LUCIANA_PHONE (E.164 sem +)
```

Para trocar de provider de IA, edite uma linha:
```env
AI_PRIMARY=gemini   # padrão atual
# AI_PRIMARY=groq   # ativar Groq como primário (cole também GROQ_API_KEY)
```
e reinicie o `uvicorn`. **Nenhuma mudança de código necessária.**

### 3. Suba Postgres + Redis

```bash
docker-compose up -d
```

Postgres expõe na porta **5433** (para não conflitar com outras instâncias locais).

### 4. Rode as migrations

```bash
alembic upgrade head
```

### 5. Valide o ambiente

```bash
python scripts/check_setup.py
```

Deve mostrar `✅` para todas as checagens (env, prompt, Redis, Postgres, e o provider ativo).

### 6. Inicie o servidor

```bash
uvicorn app.main:app --reload --port 8000
```

### 7. Exponha o webhook (outro terminal)

```bash
ngrok http 8000
```

Copie a URL `https://XXXX.ngrok-free.dev` — você vai colar no Meta Developer Console.

---

## Configurando o webhook na Meta

1. Acesse **developers.facebook.com → seu App → WhatsApp → Configuration**.
2. Em **Webhook**, clique em *Edit*.
3. **Callback URL**: `https://XXXX.ngrok-free.dev/webhook`
4. **Verify token**: o mesmo valor de `WA_VERIFY_TOKEN` no `.env`.
5. Clique em **Verify and save** — a Meta dispara um `GET /webhook` e espera o `challenge` de volta. O servidor responde automaticamente.
6. Em **Webhook fields**, marque `messages`.
7. Em **API Setup → To**, adicione na **"Manage phone number list"** todos os números que receberão mensagens (em modo Development).
8. Em **System Users**, gere um **token permanente** com escopo `whatsapp_business_messaging` → `WA_TOKEN`.
9. Em **App settings → Basic**, copie o **App secret** → `WA_APP_SECRET` (usado para validar a assinatura HMAC).

> **Modo Development vs Live:** em Development a Meta restringe destinatários à allowed list. Para produção real, **publique o app** (Mode toggle no topo do dashboard) — não exige App Review para WhatsApp Business Messaging.

---

## Como funciona uma conversa

```
1. Cliente manda mensagem no WhatsApp
2. Meta envia POST /webhook → app valida HMAC-SHA256
3. Backend retorna 200 imediatamente e processa em background
4. Recupera histórico do Redis (TTL 24h)
5. Chama o provider ativo (Gemini ou Groq) com o system prompt da Malu + histórico
6. Salva resposta no Redis + envia ao cliente via Meta API
7. Se a resposta contém "## Resumo da Solicitação":
   - Salva lead no Postgres
   - Notifica Luciana via WhatsApp
```

---

## Testes

```bash
pytest tests/ -v
```

**27 testes**, todos com **fakeredis** e mocks dos providers — não dependem de serviços externos.

### Simular uma conversa real (sem WhatsApp)

```bash
python scripts/seed_test.py
```

Roda um diálogo simulado de 8 turnos usando o provider de IA ativo e imprime o briefing gerado.

---

## Worker Celery

```bash
celery -A workers.tasks worker --loglevel=info --beat
```

- `send_followup(phone)` — manda lembrete leve para clientes que pararam de responder
- `daily_lead_report()` — roda às 8h diariamente; envia resumo dos leads do dia anterior para a Luciana

---

## Deploy no Railway

1. Crie um projeto novo em [railway.app](https://railway.app).
2. Provisione **PostgreSQL** e **Redis** dentro do projeto.
3. Conecte o repositório GitHub → Railway detecta o `Dockerfile`.
4. Em **Variables**, cole todas as chaves do `.env`. Substitua:
   - `DATABASE_URL` → use a do plugin Postgres do Railway (formato `postgresql+asyncpg://...`).
   - `REDIS_URL` → use a do plugin Redis.
5. Em **Settings → Build**, ative o auto-deploy do branch `main`.
6. Em **Deploy**, configure o start command (opcional):
   ```bash
   alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port $PORT
   ```
7. Pegue a URL pública (`https://malu-XXX.up.railway.app`) e atualize o webhook na Meta Developer Console.

Para o worker, crie um segundo **Service** no mesmo projeto apontando para o mesmo repo, com start command:
```bash
celery -A workers.tasks worker --loglevel=info --beat
```

---

## Estrutura do projeto

```
chatbot-agencia/
├── app/
│   ├── main.py              # FastAPI + webhook + HMAC + handle_message
│   ├── config.py            # Pydantic Settings (lê .env)
│   ├── database.py          # SQLAlchemy async engine
│   ├── models.py            # Lead + Conversation ORM
│   ├── session.py           # Histórico Redis
│   ├── whatsapp.py          # Cliente Meta Cloud API
│   ├── ai.py                # Router multi-provider (Gemini/Groq)
│   ├── briefing.py          # Parser de briefing + notificação Luciana
│   └── prompts/malu_v4.md   # System prompt da Malu (v4 com anti-injection)
├── workers/tasks.py         # Celery (follow-up + relatório diário)
├── alembic/                 # Migrations
├── tests/                   # pytest (27 testes)
├── scripts/
│   ├── seed_test.py         # Simula conversa completa de 8 turnos
│   └── check_setup.py       # Valida ambiente (env, Redis, Postgres, IA)
├── docs/                    # Documentação histórica de planejamento
├── docker-compose.yml       # Postgres + Redis
├── Dockerfile
├── requirements.txt
├── .env.example             # Template — copie para .env e preencha
└── CLAUDE.md                # Contexto técnico (lido pelo Claude Code)
```

---

## Regras

- **Não editar** `app/prompts/malu_v4.md` sem instrução explícita.
- **Não commitar** `.env`.
- Webhook **sempre** retorna 200 para a Meta (erros internos são logados, não propagados).
- Toda I/O é async — nunca usar `requests`, `time.sleep`, etc.
- Cada provider de IA novo deve ser adicionado em `app/ai.py` via dispatcher por `settings.ai_primary`.
