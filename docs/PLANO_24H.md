# Plano de 24h — Luma Bot ao vivo até amanhã

> Hoje é terça-feira. Meta para quarta.
> Este plano assume que você e Gustavo trabalham em paralelo.

---

## Divisão de trabalho

| Você | Gustavo |
|---|---|
| Configura a Meta (conta, app, número) | Roda o Claude Code e constrói o código |
| Prepara as credenciais | Sobe o ambiente local |
| Testa o fluxo de conversa | Ajusta bugs que surgirem |
| Valida com a Luciana | Faz o deploy final |

---

## AGORA (terça, tarde/noite)

### Você — Conta Meta (40–60 min)

**[ ] 1. Crie a conta Meta for Developers**
- Acesse https://developers.facebook.com
- Login com Facebook pessoal ou conta business
- Aceite os termos de desenvolvedor

**[ ] 2. Crie o App**
- "Criar app" → tipo: **Business**
- Nome: "Lu Milhas Luma"
- Conta comercial: crie uma nova se não tiver

**[ ] 3. Adicione o produto WhatsApp**
- No painel do app → "Adicionar produto" → WhatsApp
- Siga o wizard de configuração

**[ ] 4. Configure o número de WhatsApp Business**
- Opção A (mais rápido): Use o número de teste gratuito que a Meta fornece
  - Serve para desenvolvimento e demonstração
  - Limitado a 5 destinatários verificados
- Opção B (produção): Registre o número real da agência
  - Precisa verificar via SMS/ligação
  - Recomendado para entrega final

**[ ] 5. Anote estas informações (vai precisar para o .env)**
```
Phone Number ID: _______________________
App ID:          _______________________
App Secret:      _______________________  (Configurações → Básico)
```

**[ ] 6. Gere o token permanente**
- Painel Meta Business → Configurações → Usuários do sistema
- Crie um "Usuário do sistema administrador"
- Gere token → selecione o app → permissão: whatsapp_business_messaging
- **Copie e salve em lugar seguro — aparece só uma vez**
```
Token permanente: _______________________
```

**[ ] 7. Adicione números de teste (se usar número de teste)**
- WhatsApp → API Setup → "To" → Manage phone number list
- Adicione o número da Luciana e o seu para testes

---

### Gustavo — Ambiente e código (1–2h)

**[ ] 1. Instala pré-requisitos** (Node, Python, Docker, ngrok)

**[ ] 2. Cria pasta luma-bot e coloca os arquivos do pacote**

**[ ] 3. Abre o Claude Code e cola o PROMPT_INICIAL**
```bash
cd luma-bot
claude
# Cola o prompt e aguarda as 8 etapas
```

**[ ] 4. Enquanto o Claude Code roda** — configure o ambiente Python:
```bash
# Em outro terminal
cd luma-bot
python3 -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate
```

**[ ] 5. Após o Claude Code terminar:**
```bash
pip install -r requirements.txt
docker-compose up -d
alembic upgrade head
```

---

## ESTA NOITE (terça, noite)

### Vocês dois juntos — Integração (30–60 min)

**[ ] 1. Gustavo preenche o .env com as credenciais que você coletou**

**[ ] 2. Testa a IA sem WhatsApp**
```bash
python scripts/check_setup.py
python scripts/seed_test.py
```
Deve gerar uma conversa completa e um briefing. Se funcionar, a IA está ok.

**[ ] 3. Sobe o servidor e o webhook**
```bash
# Terminal 1
uvicorn app.main:app --reload --port 8000

# Terminal 2
ngrok http 8000
```

**[ ] 4. Configura webhook na Meta**
- Meta Developer Console → WhatsApp → Configuration → Webhook
- URL: `https://[url-do-ngrok].ngrok.io/webhook`
- Verify Token: o mesmo do .env
- Clica "Verify and Save"
- Assina o campo `messages`

**[ ] 5. Primeiro teste real**
- Você manda uma mensagem para o número de teste
- Luma deve responder em 5–10 segundos
- Se não responder: verifica logs do uvicorn

---

## AMANHÃ CEDO (quarta, manhã)

### Deploy para produção (30–45 min)

**[ ] 1. Gustavo cria conta no Railway.app**
- https://railway.app → Login com GitHub
- "New Project" → "Deploy from GitHub repo"
- Se o código não está no GitHub ainda:
  ```bash
  git init
  git add .
  git commit -m "luma bot v1"
  gh repo create luma-bot --private --push  # precisa do GitHub CLI
  ```

**[ ] 2. Adiciona serviços no Railway**
- "Add service" → PostgreSQL
- "Add service" → Redis
- Copia as URLs geradas para as variáveis de ambiente

**[ ] 3. Configura variáveis de ambiente no Railway**
- No projeto → Variables → adiciona todas do .env
- Substitui DATABASE_URL e REDIS_URL pelas URLs do Railway

**[ ] 4. Deploy automático**
- Railway detecta o Dockerfile e sobe automaticamente
- Aguarda o build (3–5 min)
- Copia a URL pública gerada, ex: `https://luma-bot.up.railway.app`

**[ ] 5. Atualiza webhook na Meta**
- Troca a URL do ngrok pela URL do Railway
- Formato: `https://luma-bot.up.railway.app/webhook`
- Verifica e salva

**[ ] 6. Teste final de produção**
- Você manda mensagem do seu WhatsApp para o número da agência
- Luma responde
- Completa uma coleta de dados de viagem
- Verifica se Luciana recebeu o briefing no WhatsApp dela

---

## Validação com a Luciana (quarta, tarde)

**[ ] 1. Luciana testa enviando uma mensagem como se fosse cliente**
**[ ] 2. Verifica se o tom da Luma está correto**
**[ ] 3. Verifica se o briefing chegou para ela completo e legível**
**[ ] 4. Ajustes finos se necessário (via Claude Code)**

---

## O que fazer se der problema

| Problema | Solução |
|---|---|
| Claude Code travou | Ctrl+C e recola o prompt a partir da etapa que parou |
| Webhook não verifica | Confirma que WA_VERIFY_TOKEN no .env é idêntico ao da Meta |
| Luma não responde | Verifica logs: `uvicorn app.main:app --reload` mostra os erros |
| Meta retorna 401 | Token expirou — regenera o System User token |
| Briefing não chega para Luciana | Verifica LUCIANA_PHONE no .env (formato: 5511999999999) |
| Railway não sobe | Verifica se o Dockerfile está correto — manda o erro pro Claude Code corrigir |

---

## Resumo do prazo

```
Terça tarde    → Você: cria conta Meta + coleta credenciais
Terça tarde    → Gustavo: roda Claude Code, constrói o projeto
Terça noite    → Vocês dois: integração, webhook, primeiro teste real
Quarta manhã   → Deploy Railway, URL de produção
Quarta tarde   → Teste com Luciana, ajustes, entrega
```

**Total de trabalho estimado: 4–6 horas entre os dois.**
