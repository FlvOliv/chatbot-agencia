# Malu Bot — Lu Milhas & Viagens

[![tests](https://github.com/FlvOliv/chatbot-agencia/actions/workflows/tests.yml/badge.svg)](https://github.com/FlvOliv/chatbot-agencia/actions/workflows/tests.yml)

Assistente virtual de atendimento nível 1 da agência **Lu Milhas & Viagens**.
Atende clientes via WhatsApp, coleta informações de viagem e gera um briefing estruturado para a Lu (atendente humana) fechar a cotação.

- Integração oficial via **Meta WhatsApp Cloud API** (sem risco de banimento)
- **Roteamento multi-LLM com fallback automático** (`app/ai.py::route_and_ask`). Em produção a cadeia é:
  1. **Groq · Llama 3.3 70B** (primário)
  2. **Cerebras · gpt-oss-120b** (camada gratuita extra)
  3. **Mistral** (piso pago, só com `PAID_FLOOR_ENABLED` e com teto mensal de tokens em `app/budget.py`)
  4. **Google Gemini 2.5 Flash** (último recurso)

  Cada perna só entra se tiver chave; erro ou resposta vazia passa pra próxima. A ordem segue a LGPD: o briefing carrega dado pessoal, e os provedores que não treinam com os dados vêm antes do Gemini gratuito.
- **Extração estruturada do briefing em JSON** (`extract_lead_data`, temperatura 0) com **gate de completude** por tipo de atendimento (`app/briefing.py::gate_missing_fields`): a Malu não fecha o lead com coleta furada.
- Backend: **FastAPI** async · **PostgreSQL 16** · **Redis 7** (histórico com fallback pro Postgres) · follow-ups por **cron externo** (`POST /internal/tick`) · multi-tenant com segredos por agência cifrados (Fernet)
- Persona da Malu em `app/prompts/malu_v4.md` (conteúdo na **versão 5.0**): regras contra cotar preço, contra prompt injection e contra fuga de escopo, mais a tabela de temperatura do lead. Um `price_guard` no código mascara valor que escape do modelo.
- Painel de atendimento humano (Next.js, pasta `crm/`): conversas ao vivo, leads, tags, áudio e PWA.

---

## Origem e autoria

Este repositório é um **fork** de [`gustavomarcelloprf/chatbot-agencia`](https://github.com/gustavomarcelloprf/chatbot-agencia). O histórico de commits fica preservado aqui como registro de quem fez o quê.

- **Gustavo Marcello** (10 commits, 28/05 a 05/06/2026): versão 1 do bot (webhook, roteador Gemini/Groq, prompt v4), lembretes via Celery, suporte inicial a áudio, scripts de deploy no Railway e a primeira versão do painel de insights.
- **Flávio Henrique Oliveira da Silva** (67 commits, 01/06 a 16/11/2026), a partir da v1:
  - fallback automático entre provedores e, depois, a cadeia de 4 provedores com piso pago e trava de orçamento;
  - extração do briefing em JSON, gate de completude, anti-loop, anti-amnésia do histórico e ficha de coleta persistida;
  - prompt da v4.4 até a v5.0, calibrado com o checklist real da agência;
  - transcrição de áudio (Whisper via Groq), troca do Celery por agendamento em Postgres com cron, e multi-tenant;
  - inbox de atendimento humano, login, tags e redesign do painel;
  - suíte de conformidade da Malu, que roda o pipeline real com IA real e checagens automáticas (`scripts/conformance_probe.py`), e 277 das 347 funções de teste (contagem por `git blame`);
  - framework de avaliação comparativa de LLMs (`evals/`): 30 conversas sintéticas em 7 categorias rodando pelo pipeline real, com acerto por campo do briefing, guardrails, tokens, custo e latência. Achou e corrigiu 2 bugs de produção (resposta de modelo de raciocínio cortada no teto de tokens; pergunta de indicação repetida). Rodada completa em andamento, ver [`evals/README.md`](evals/README.md).

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
git clone https://github.com/FlvOliv/chatbot-agencia.git malu-bot
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

A cadeia de IA é montada pelas variáveis abaixo (configuração de produção):
```env
AI_PRIMARY=groq          # primeira perna
AI_FALLBACK=gemini       # última perna (none | auto | gemini | groq)
CEREBRAS_API_KEY=...     # vazio = perna Cerebras desligada
PAID_FLOOR_ENABLED=true  # liga o piso pago (Mistral), com MONTHLY_PAID_TOKEN_CAP
```
Reinicie o `uvicorn` depois de mudar. **Nenhuma mudança de código necessária.**

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
4. Recupera histórico do Redis (TTL 24h; se sumir, reconstrói do Postgres)
5. Com COLETA_STATE_ENABLED, extrai a ficha de coleta em JSON e injeta o estado no contexto da Malu
6. Chama o roteador de IA (cadeia com fallback) com o system prompt + histórico
7. price_guard + anti-loop na resposta; salva e envia ao cliente via Meta API
8. Quando a coleta fecha e o gate de completude aprova:
   - Salva o lead no Postgres com o briefing renderizado
   - Notifica a Lu via WhatsApp
```

---

## Testes

```bash
pytest tests/ -v
```

**453 testes** coletados pelo pytest (347 funções, algumas parametrizadas), todos com **fakeredis** e mocks dos providers. Não dependem de serviço externo. No Windows, o `tzdata` do `requirements.txt` fornece o fuso `America/Sao_Paulo`.

**CI (GitHub Actions):** `.github/workflows/tests.yml` roda a suíte inteira a cada push na `main` e em todo PR (Ubuntu, Python 3.12, sem segredo nenhum).

### Suíte de conformidade (IA real, sem WhatsApp)

```bash
COLETA_STATE_ENABLED=true PYTHONUTF8=1 python -m scripts.conformance_probe
```

Dirige o pipeline real (`_process_text_message`) com IA real e I/O externo stubbado, e dá veredito automático por cenário: repetição, re-saudação, vazamento de preço, fecho no turno certo, transferência, pergunta de indicação e silêncio pós-fecho.

### Simular uma conversa real (sem WhatsApp)

```bash
python scripts/seed_test.py
```

Roda um diálogo simulado de 8 turnos usando o provider de IA ativo e imprime o briefing gerado.

---

## Follow-ups (cron, sem worker)

Não há worker Celery. Um cron externo (ex.: cron-job.org, grátis) faz `POST /internal/tick` a cada 1 min com o header `X-Cron-Secret` (= `CRON_SECRET`). Cada batida:

- dispara os **lembretes de inatividade** vencidos — agendados em `app/reminders.py` na tabela `reminders` (Postgres), 30 min após a última resposta da Malu se a coleta não terminou; cancelados em `/sair` ou quando a Lu assume.
- roda o **resumo diário** dos leads para a Lu, 1×/dia a partir das 8h (`app/reports.py`).

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

Para os follow-ups, **não** crie um segundo service. Configure um **cron externo** (cron-job.org) com `POST https://SUA-URL.up.railway.app/internal/tick` a cada 1 min e o header `X-Cron-Secret` = `CRON_SECRET`.

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
│   ├── ai.py                # Roteador multi-LLM com fallback + extração JSON
│   ├── briefing.py          # Campos do briefing, gate de completude, recap
│   ├── budget.py            # Teto mensal de tokens do piso pago
│   ├── prompts/malu_v4.md   # System prompt da Malu (conteúdo v5.0)
│   ├── reports.py           # resumo diário de leads (disparado pelo cron)
│   └── api/tick.py          # POST /internal/tick (cron) → follow-ups + resumo
├── alembic/                 # Migrations
├── tests/                   # pytest (453 testes)
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
