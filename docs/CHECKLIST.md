# Checklist — Antes de usar o Claude Code

Faça isso ANTES de colar o prompt no Claude Code.

---

## 1. Instale o Claude Code

```bash
npm install -g @anthropic-ai/claude-code
```

Precisa de Node.js 18+. Para verificar:
```bash
node --version
```

---

## 2. Autentique o Claude Code

```bash
claude
# Na primeira vez ele vai pedir login — siga as instruções
```

---

## 3. Crie a pasta do projeto e coloque os arquivos

```bash
mkdir luma-bot
cd luma-bot

# Copie os dois arquivos que você baixou para dentro desta pasta:
# - CLAUDE.md        (contexto automático do projeto)
# - PROMPT_INICIAL.md  (o prompt que você vai colar)
```

---

## 4. Coloque o MD da Luma na pasta

```bash
# Copie o arquivo md_luma_assistente_lu_milhas.md para a pasta também:
cp ~/Downloads/md_luma_assistente_lu_milhas.md ./luma_v2.md
```

---

## 5. Instale o Docker Desktop

Necessário para rodar PostgreSQL e Redis localmente.
Download: https://www.docker.com/products/docker-desktop

---

## 6. Instale o ngrok (para expor o webhook)

```bash
# Mac
brew install ngrok

# Windows / Linux
# Baixe em https://ngrok.com/download
```

Crie conta gratuita em ngrok.com e autentique:
```bash
ngrok config add-authtoken SEU_TOKEN_AQUI
```

---

## 7. Abra a conta na Meta for Developers

1. Acesse https://developers.facebook.com
2. Crie um app → tipo "Business"
3. Adicione o produto "WhatsApp"
4. Anote:
   - **Phone Number ID** (WA_PHONE_ID)
   - **App Secret** (WA_APP_SECRET)
5. Gere um **System User Token** permanente (não use o token temporário)
   - Vai virar: WA_TOKEN no .env

---

## 8. Tenha sua chave da Anthropic

Acesse https://console.anthropic.com → API Keys → Create Key
Vai virar: ANTHROPIC_API_KEY no .env

---

## 9. Inicie o Claude Code na pasta do projeto

```bash
cd luma-bot
claude
```

---

## 10. Cole o prompt

Abra o arquivo `PROMPT_INICIAL.md`, copie tudo entre os ``` e cole no terminal do Claude Code.

**Importante:** Antes de colar, substitua a linha:
```
[COLE AQUI O CONTEÚDO DO ARQUIVO md_luma_assistente_lu_milhas.md]
```
pelo conteúdo real do arquivo `luma_v2.md`.

---

## Depois que o Claude Code terminar

```bash
# 1. Sobe os serviços locais
docker-compose up -d

# 2. Cria o banco
alembic upgrade head

# 3. Verifica tudo
python scripts/check_setup.py

# 4. Testa a IA sem WhatsApp
python scripts/seed_test.py

# 5. Sobe o servidor
uvicorn app.main:app --reload --port 8000

# 6. Em outro terminal, expõe o webhook
ngrok http 8000

# 7. Cola a URL ngrok no Meta Developer Console
```

---

## Custo estimado

| Serviço | Custo |
|---|---|
| Meta WhatsApp API | Grátis até 1.000 conversas/mês |
| Anthropic (Claude Sonnet) | ~$0,003 por conversa |
| Railway.app (deploy) | ~$5–10/mês |
| ngrok (dev) | Grátis |
| **Total inicial** | **< $15/mês** |
