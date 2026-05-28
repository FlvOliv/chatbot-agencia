# Luma Bot — Handoff para Gustavo

Olá Gustavo! Este pacote contém tudo para você construir o projeto do zero usando o Claude Code.

## Contexto rápido

- **Projeto:** Chatbot WhatsApp para agência de viagens "Lu Milhas & Viagens"
- **Assistente:** Luma — IA de atendimento nível 1 que coleta dados de viagem e gera briefings
- **Dono do projeto:** [nome do seu colega]
- **Prazo:** Amanhã (quarta-feira)

---

## O que está neste pacote

| Arquivo | Para que serve |
|---|---|
| `CLAUDE.md` | Contexto do projeto — Claude Code lê automaticamente |
| `PROMPT_INICIAL.md` | Prompt orquestrador — você cola no Claude Code |
| `luma_v2.md` | System prompt completo da Luma — NÃO alterar |
| `CHECKLIST.md` | Pré-requisitos antes de começar |
| `PARA_GUSTAVO.md` | Este arquivo |

---

## Pré-requisitos na sua máquina (10–15 min)

### 1. Node.js 18+ (para o Claude Code)
```bash
node --version   # Se não tiver: https://nodejs.org
```

### 2. Claude Code
```bash
npm install -g @anthropic-ai/claude-code
claude           # Faz login com sua conta Anthropic
```

### 3. Python 3.12+
```bash
python3 --version   # Se não tiver: https://python.org
```

### 4. Docker Desktop
Baixe em: https://www.docker.com/products/docker-desktop
Necessário para rodar PostgreSQL e Redis localmente.

### 5. ngrok
```bash
# Mac
brew install ngrok

# Ou baixe em: https://ngrok.com/download
```
Crie conta grátis em ngrok.com, pegue o authtoken e rode:
```bash
ngrok config add-authtoken SEU_TOKEN
```

---

## Como rodar o projeto (passo a passo)

### Passo 1 — Crie a pasta e coloque os arquivos
```bash
mkdir luma-bot
cd luma-bot

# Copie todos os arquivos deste pacote para dentro de luma-bot/
# CLAUDE.md, PROMPT_INICIAL.md, luma_v2.md
```

### Passo 2 — Abra o Claude Code
```bash
cd luma-bot
claude
```

### Passo 3 — Cole o prompt
Abra o `PROMPT_INICIAL.md`, copie todo o conteúdo entre os ``` e cole no terminal do Claude Code.

O Claude vai construir o projeto inteiro automaticamente em 8 etapas.
**Deixe rodar sem interromper.** Se ele pausar para perguntar algo, responda "sim, pode continuar".

### Passo 4 — Preencha o .env
Após o Claude terminar, edite o arquivo `.env` com as chaves reais:

```env
WA_TOKEN=           # Token da Meta (veja seção abaixo)
WA_PHONE_ID=        # ID do número na Meta
WA_VERIFY_TOKEN=    # Qualquer string aleatória, ex: luma_secret_2025
WA_APP_SECRET=      # App Secret da Meta
ANTHROPIC_API_KEY=  # Chave da Anthropic do seu colega
DATABASE_URL=postgresql+asyncpg://luma:luma@localhost:5432/luma
REDIS_URL=redis://localhost:6379/0
LUCIANA_PHONE=55119XXXXXXXX   # Número da Luciana com código do país
```

### Passo 5 — Suba os serviços e teste
```bash
docker-compose up -d          # Sobe postgres + redis
alembic upgrade head          # Cria as tabelas
python scripts/check_setup.py # Verifica se tudo está ok
python scripts/seed_test.py   # Testa a IA sem precisar de WhatsApp
```

### Passo 6 — Suba o servidor e o webhook
```bash
# Terminal 1
uvicorn app.main:app --reload --port 8000

# Terminal 2
ngrok http 8000
# Copie a URL https gerada, ex: https://abc123.ngrok.io
```

Cole a URL ngrok no Meta Developer Console:
- Webhook URL: `https://abc123.ngrok.io/webhook`
- Verify Token: o mesmo que você colocou em `WA_VERIFY_TOKEN`

---

## Configuração Meta (se ainda não estiver pronta)

1. Acesse https://developers.facebook.com
2. Crie um App → tipo "Business"
3. Adicione o produto "WhatsApp"
4. Anote o **Phone Number ID** e o **App Secret**
5. Em "System Users" → crie um System User → gere token permanente
6. Assine o webhook para o evento `messages`
7. Envie uma mensagem de teste para o número

---

## O que NÃO mudar

- O arquivo `app/prompts/luma_v2.md` — é o cérebro da Luma
- A lógica de validação HMAC do webhook — segurança da Meta
- O formato do bloco de briefing — é o que aciona a notificação para a Luciana

---

## Se travar em alguma etapa

Descreva o erro para o Claude Code no terminal que ele resolve. Ou manda mensagem para o dono do projeto.
