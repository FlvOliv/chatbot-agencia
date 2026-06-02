# Deploy no Railway — Malu Bot (passo a passo)

Tempo estimado: **1 hora**, primeira vez. Depois 5 minutos por deploy.

Este guia assume que:
- Você já fez o setup local funcionando (`pytest` verde, `seed_test.py` rodando)
- O app Meta já está **publicado** (modo Live) — veja `MIGRACAO-META.md`
- Você tem conta no Railway, Supabase e Upstash (criação coberta abaixo)

---

## Arquitetura em produção

```
┌──────────────────────────────────────────┐
│         Railway Project: Malu            │
│                                          │
│  ┌──────────────┐    ┌────────────────┐  │
│  │  Service:    │    │   Service:     │  │
│  │  web         │    │   worker       │  │
│  │  (FastAPI)   │    │   (Celery)     │  │
│  └──────┬───────┘    └────────┬───────┘  │
│         │                     │          │
└─────────┼─────────────────────┼──────────┘
          │                     │
          │ DATABASE_URL        │
          │ REDIS_URL           │
          ▼                     ▼
   ┌─────────────────┐  ┌────────────────┐
   │   Supabase      │  │    Upstash     │
   │   Postgres      │  │     Redis      │
   └─────────────────┘  └────────────────┘
```

Backend e worker são **dois serviços separados** no mesmo projeto Railway, lendo do mesmo
GitHub. Banco e cache são serviços externos (Supabase + Upstash) — mais barato e gerenciado.

---

## Etapa 1 — Supabase (Postgres na nuvem)

### 1.1 Criar projeto Supabase

1. Acessa https://supabase.com → **Start your project**
2. Login com GitHub
3. **New project**
4. Preenche:
   - **Name**: `malu-bot-producao`
   - **Database Password**: clica em **Generate a password** e **salva em lugar seguro**
   - **Region**: `South America (São Paulo)` — menor latência pro Brasil
   - **Pricing Plan**: Free
5. Clica **Create new project** — espera ~2 min provisionar

### 1.2 Pegar a connection string

1. Projeto criado → **Settings** (engrenagem) → **Database**
2. Em **Connection string**, escolhe **URI** (formato `postgresql://...`)
3. **Connection mode**: **Session pooler** (`*.pooler.supabase.com:5432`)
4. Copia a string. Vai parecer:
   ```
   postgresql://postgres.xxxxxxx:[YOUR-PASSWORD]@aws-0-sa-east-1.pooler.supabase.com:5432/postgres
   ```
5. **Troca `[YOUR-PASSWORD]` pela senha** que você salvou.
6. **Troca `postgresql://` por `postgresql+asyncpg://`** (nosso código usa asyncpg).

A string final que vai pro `DATABASE_URL` no Railway:
```
postgresql+asyncpg://postgres.xxxxx:SUASENHAAQUI@aws-0-sa-east-1.pooler.supabase.com:5432/postgres
```

### 1.3 Habilitar a extensão pgcrypto

Nossa migration `0001_initial` usa `gen_random_uuid()` que vem de `pgcrypto`.

1. Supabase → **Database** → **Extensions**
2. Procura `pgcrypto` → clica em **Enable**

Pronto. O `alembic upgrade head` no deploy vai rodar nossas 3 migrations sem erro.

---

## Etapa 2 — Upstash (Redis serverless)

### 2.1 Criar database

1. https://upstash.com → **Sign up with GitHub**
2. **Create Database**
3. Preenche:
   - **Name**: `malu-bot-prod`
   - **Type**: **Regional** (mais barato)
   - **Region**: `sa-east-1` (São Paulo)
   - **TLS**: ✅ **Enabled** (default — não desabilita)
4. Clica **Create**

### 2.2 Pegar a connection string

1. Database criado → aba **Details**
2. Copia o **`UPSTASH_REDIS_TLS_URL`** (formato `rediss://default:...@xxx.upstash.io:6379`)
3. Esse é o `REDIS_URL` que vai pro Railway. Note o `rediss://` (com SS — TLS habilitado).

> ⚠️ **Se aparecer "Eviction"** nas configurações: deixa como `noeviction` ou `allkeys-lru`.
> Nossas sessões têm TTL próprio (24h), então qualquer modo serve.

---

## Etapa 3 — Railway (deploy do backend)

### 3.1 Criar projeto

1. https://railway.app → **Login with GitHub**
2. **New Project** → **Deploy from GitHub repo**
3. Autoriza acesso ao repo `gustavomarcelloprf/chatbot-agencia`
4. Seleciona o repo
5. Railway detecta o `Dockerfile` automaticamente e começa o build

### 3.2 Adicionar as variáveis de ambiente

Antes do primeiro deploy completar (ele vai falhar por falta das vars), entra em **Variables**
no painel do projeto e adiciona todas:

```env
# Meta WhatsApp Cloud API
WA_TOKEN=<token permanente do System User>
WA_PHONE_ID=<phone number ID>
WA_VERIFY_TOKEN=luma_secret_2025
WA_APP_SECRET=<app secret da Meta>

# Gemini (primário)
GEMINI_API_KEY=AIza...
GEMINI_MODEL=gemini-2.5-flash

# Groq (fallback automático)
GROQ_API_KEY=gsk_...
GROQ_MODEL=llama-3.3-70b-versatile
AI_PRIMARY=gemini
AI_FALLBACK=auto

# Banco e cache (Etapas 1 e 2 acima)
DATABASE_URL=postgresql+asyncpg://postgres.xxxxx:SENHA@aws-0-sa-east-1.pooler.supabase.com:5432/postgres
REDIS_URL=rediss://default:xxxxx@xxxxx.upstash.io:6379

# Negócio
LUCIANA_PHONE=5511963971510
BUSINESS_HOURS_START=9
BUSINESS_HOURS_END=18

# App
APP_ENV=production
LOG_LEVEL=INFO
SESSION_TTL_SECONDS=86400

# CRM API (consumida pelo Vercel CRM)
CRM_API_KEY=<gere com: python -c "import secrets; print(secrets.token_urlsafe(32))">
CRM_CORS_ORIGINS=https://crm-lu-milhas.vercel.app,http://localhost:3000

# Concorrência (opcional — Railway dá 512MB no plano básico)
WEB_CONCURRENCY=2
WORKER_CONCURRENCY=2
```

### 3.3 Confirmar build do serviço web

1. Aba **Deployments** → aguarda build (3-5 min)
2. Quando aparecer `Active`, gera um domínio público:
   - Aba **Settings** → **Networking** → **Generate Domain**
   - Você ganha algo tipo `malu-bot.up.railway.app`
3. Testa o health:
   ```bash
   curl https://malu-bot.up.railway.app/health
   ```
   Deve responder JSON com `"status": "ok"`.

### 3.4 Criar o serviço worker (Celery)

1. No projeto Railway → botão **+ New** → **GitHub Repo** → **mesmo repo**
2. Renomeia pra `malu-worker` (Settings → Service Name)
3. Em **Settings → Deploy → Custom Start Command**, coloca:
   ```
   ./scripts/start_worker.sh
   ```
4. Em **Variables**, clica **Add Reference** e seleciona **todas** as vars do serviço web
   (Railway permite compartilhar). Importante: `DATABASE_URL`, `REDIS_URL`, `WA_TOKEN`,
   `LUCIANA_PHONE`, `GEMINI_API_KEY`, `GROQ_API_KEY`.
5. Deploy automático. Confere os logs — deve aparecer `celery@malu-worker ready`.

> Worker não precisa de domínio público — ele só consome mensagens da fila Redis.

---

## Etapa 4 — Atualizar webhook na Meta

1. https://developers.facebook.com → seu app → **WhatsApp → Configuration**
2. Em **Webhook**, clica **Edit**
3. **Callback URL**: `https://malu-bot.up.railway.app/webhook`
4. **Verify Token**: o mesmo de `WA_VERIFY_TOKEN`
5. Clica **Verify and save** — deve ficar verde
6. Garante que **`messages`** está assinado em Webhook fields

---

## Etapa 5 — Validação end-to-end

### Do seu computador:

```bash
# Health check
curl https://malu-bot.up.railway.app/health

# Métricas (com API key correta)
curl -H "X-API-Key: SUACHAVEAQUI" https://malu-bot.up.railway.app/api/dashboard/metrics

# Lista de leads
curl -H "X-API-Key: SUACHAVEAQUI" https://malu-bot.up.railway.app/api/leads
```

### Do WhatsApp:

1. Manda uma mensagem do **seu** celular pro número da Malu (qualquer texto)
2. Em <10s deve chegar resposta
3. Confere nos logs do Railway (aba **Deployments → Logs** do serviço web):
   ```
   INFO malu — incoming from 5511...: oi
   INFO httpx — POST .../messages "HTTP/1.1 200 OK"
   INFO malu — whatsapp send_message OK
   ```

> ⚠️ **Se você ainda está em modo Development na Meta**, só números na "Allowed phone number
> list" funcionam. Publica o app primeiro (`docs/MIGRACAO-META.md` Etapa 2).

---

## Etapa 6 — Deploy do CRM (Vercel)

Sai do escopo desse guia (CRM vive na worktree `chatbot-agencia-crm`). Resumo:

1. https://vercel.com → **Import Project** → seu repo `chatbot-agencia`
2. **Framework Preset**: Next.js
3. **Root Directory**: `crm/`
4. **Build Command**: `npm run build`
5. **Environment Variables**:
   ```
   API_BASE_URL=https://malu-bot.up.railway.app
   CRM_API_KEY=<mesma do Railway>
   ```
   (NÃO usar prefixo `NEXT_PUBLIC_` — key é server-side only)
6. Deploy → você ganha um domínio `https://crm-lu-milhas.vercel.app`
7. Volta no Railway e atualiza `CRM_CORS_ORIGINS` pra incluir essa URL

---

## Manutenção pós-deploy

### Atualizar código

Push pra `main` no GitHub → Railway faz deploy automático (3-5 min).

### Ver logs

Railway → projeto → serviço → aba **Deployments → Logs**. Filtrar por tempo ou search.

### Rollback

Railway → projeto → serviço → **Deployments** → versão anterior → **Redeploy**.

### Trocar token Meta

Railway → Variables → edita `WA_TOKEN` → **Save** → redeploy automático.

### Trocar de IA (Gemini ↔ Groq)

Railway → Variables → edita `AI_PRIMARY` (`gemini` ou `groq`) → redeploy.

---

## Custos esperados

| Serviço | Plano | Custo mês |
|---|---|---|
| Railway | Hobby ($5 free credit) | $5-10/mês após créditos |
| Supabase | Free | $0 até 500MB |
| Upstash | Free | $0 até 10k requests/dia |
| **Total** | — | **~R$ 25-50/mês** |

Quando passar de ~200 conversas/dia, considere upgrade pro Railway Pro ($20/mês).

---

## Checklist final pré-deploy

- [ ] Postgres Supabase criado, extensão `pgcrypto` habilitada
- [ ] Redis Upstash criado, TLS URL copiada
- [ ] Railway projeto criado, conectado ao GitHub
- [ ] Todas as variáveis de ambiente preenchidas (não esquecer nenhuma)
- [ ] Build do serviço web verde (`Active`)
- [ ] Domínio público gerado
- [ ] `curl /health` responde 200
- [ ] Serviço worker criado, logs sem erro
- [ ] App Meta em modo Live (`docs/MIGRACAO-META.md`)
- [ ] Webhook Meta apontando pro domínio Railway
- [ ] Mensagem real de teste pelo WhatsApp → Malu responde
- [ ] CRM no Vercel (opcional pra primeira etapa)

Quando todos os ✅ estiverem marcados, **a Lu pode usar com clientes reais**.
