# Migração da conta Meta — Flávio → Gustavo → Lu Milhas

Roteiro pra transferir a propriedade técnica do app WhatsApp Business da Meta sem perder o número, histórico ou configurações. **Faça nesta ordem.**

---

## Por que isso importa

Hoje o app Meta com o número da Malu está no **Business Manager pessoal do Flávio**.
Isso significa:

- Só o Flávio pode gerar token, ver métricas, regenerar app secret, configurar webhook.
- Se a Lu quiser controlar o WhatsApp dela mesma no futuro, precisa virar dona do app.
- Você (Gustavo) depende do Flávio pra qualquer mudança de produção.

**Solução em 2 passos:** primeiro Flávio te adiciona como admin (você ganha acesso sem ele perder). Depois, quando a Lu estiver pronta, transferimos o app inteiro pra um Business Manager dela.

---

## Etapa 1 — Flávio te adiciona como admin (15 min, pra fazer hoje)

### Mensagem pra mandar pro Flávio

> Oi Flávio, pra eu não te incomodar toda vez que precisar mexer na Meta (token, webhook, etc.), me adiciona como admin do Business Manager onde o app da Malu está? São 3 passos:
>
> **1.** Vai em https://business.facebook.com/settings → escolhe a Business Manager onde está o app da Lu Milhas
>
> **2.** No menu lateral: **Usuários → Pessoas → Adicionar**
>   - Email: **gustavomarcelloprf@gmail.com** (confere comigo se for outro)
>   - Acesso: **Acesso administrativo** (pode tudo)
>
> **3.** Depois de me adicionar como pessoa, ainda no menu lateral: **Contas → Aplicativos** → clica no app da Malu → aba **Pessoas** → adiciona meu nome com função **"Administrador"**
>
> Aí eu recebo o convite por email e aceito. Levo uns 5 minutos pra estar tudo pronto. Valeu!

### O que você faz quando o convite chegar

1. Abre o email da Meta no seu Gmail
2. Clica em "Aceitar convite" (você é redirecionado pro business.facebook.com)
3. Loga com sua conta Facebook pessoal
4. Confirma o aceite

**Confirma o sucesso**: vai em https://developers.facebook.com → seus apps. O app da Lu Milhas deve aparecer ali. Se aparecer, deu certo. ✅

### Depois disso, você pode:

- Gerar token permanente próprio (em System Users)
- Ver/regenerar App Secret
- Editar webhook
- Adicionar números à allowed list
- Tudo sem precisar do Flávio

---

## Etapa 2 — Publicar o app (sair do modo Development)

Hoje o app está em **Development Mode**, o que faz a Meta restringir:
- Só números cadastrados na "Allowed phone number list" recebem mensagens
- Limite mais apertado de requests
- Banner "Test mode" em alguns lugares

Pra produção real (qualquer cliente da Lu poder mandar mensagem), precisa **publicar**.

### Como publicar

1. https://developers.facebook.com/apps/ → seleciona o app da Lu Milhas
2. No topo da tela, vai aparecer um toggle **"App Mode"** com opções **Development** e **Live**
3. Clica em **Live**
4. A Meta vai pedir pra você confirmar:
   - Privacy Policy URL (precisa ter — placeholder serve no início: ex. `https://lumilhas.com.br/privacidade`)
   - Categoria do app: **Business and Pages**
   - Confirmação de termos
5. Clica em **Confirm**

✅ **Resultado**: a partir desse momento, qualquer número do mundo pode mandar mensagem pro WhatsApp da Malu e a resposta chega.

> **NÃO exige App Review pra WhatsApp Business Messaging.** É a categoria "Standard Access" que sai automaticamente.

### Pegadinhas a evitar

- **Não muda o número** depois de publicado. O número fica linkado à app/Business.
- **Privacy Policy URL** precisa existir (mesmo que seja uma página simples). Sem isso, a Meta bloqueia a publicação. Se a Lu Milhas ainda não tem uma página de privacidade, criamos uma estática em 10 min.
- **Verificação de negócio** (Business Verification) — pra alguns recursos avançados a Meta pede comprovação de empresa (cartão CNPJ, conta bancária). Pro envio básico de mensagens NÃO precisa.

---

## Etapa 3 — Transferir o app pra Business Manager da Lu (quando ela criar)

Isso só faz sentido quando a Lu quiser ser dona técnica do app. Pode ser daqui a 1, 3 ou 6 meses, sem urgência.

### Pré-requisito: a Lu cria conta de Business Manager dela

1. Lu acessa https://business.facebook.com/
2. Loga com Facebook pessoal dela
3. Clica em **Criar Conta**
4. Preenche: nome da empresa (Lu Milhas & Viagens), email comercial, etc.
5. Confirma o email
6. ✅ Tem a Business Manager dela

### Transferência do app

1. Flávio (ou você, se for admin até lá) entra no Business Manager **atual** (do Flávio)
2. **Configurações → Contas → Aplicativos**
3. Seleciona o app da Lu Milhas
4. Botão **"Solicitar transferência de propriedade"**
5. Insere o ID da Business Manager da Lu
6. A Lu recebe um convite, aceita
7. ✅ A partir desse momento, o app é dela. Vocês continuam como admins.

> **O número, configurações, webhook, tokens NÃO mudam.** Só a "dona" da conta muda. Zero downtime.

---

## Checklist resumido

- [ ] Mandar mensagem pro Flávio (Etapa 1)
- [ ] Esperar convite no email
- [ ] Aceitar convite
- [ ] Confirmar que vê o app em developers.facebook.com
- [ ] Gerar seu próprio token permanente (System Users)
- [ ] Atualizar `WA_TOKEN` no `.env` com o seu novo token
- [ ] **(Opcional, mas recomendado antes de lançar)** Publicar o app (Etapa 2)
- [ ] **(Quando Lu estiver pronta)** Transferir Business pra ela (Etapa 3)

---

## Dúvidas comuns

**Vai cair a Malu enquanto migra?**
Não. Etapas 1 e 3 são mudança de "quem é dono", não de configuração. Etapa 2 (publicar)
também não derruba — só destrava recursos.

**E se o Flávio sair sem me adicionar?**
Risco real. Por isso a Etapa 1 é prioridade hoje. Sem isso, qualquer mudança fica refém dele.

**A Lu precisa entender de tecnologia pra ser admin?**
Não. O Business Manager é uma interface visual da Meta. Ela cria conta, aceita convites
e pronto. Quem mexe nas configurações técnicas é você.

**E se a Meta pedir verificação de negócio (CNPJ)?**
Pra envio de mensagens básico não pede. Se pedir em algum momento (provavelmente quando
chegarmos a 10k+ mensagens/mês), aí pegamos o CNPJ da Lu Milhas e fazemos.

---

## Atualizações no projeto depois da migração

Quando o token Meta mudar (Etapa 1 ou 3), só preciso:

```bash
# No Mac
cd /Users/gustavomarcello/Documents/chatbot-agencia
# Edita o .env e troca o WA_TOKEN
# Reinicia o uvicorn
```

Em produção (Railway), trocar o valor da variável `WA_TOKEN` no painel do Railway e fazer
redeploy. 2 cliques, sem mexer em código.
