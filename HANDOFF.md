# HANDOFF: chatbot-agencia (Malu / Lu Milhas)

Doc de estado. Atualizar números e pendências; não narrar sessão.

## Estado (16/11/2026)
- Repo restaurado no PC novo a partir do fork público (`main@e17e079`, 06/07/2026). O que não tinha
  sido enviado pro GitHub do PC antigo **não está aqui** (o `.env` inclusive).
- Suíte: **392 testes** coletados, 392 passando no Windows/Python 3.12 (precisou do `tzdata`).
  Com os testes do eval (`tests/test_evals.py`): 419.
- Prompt em produção: `app/prompts/malu_v4.md`, conteúdo **v5.0**.
- `docs/origem-autoria` (README com "Origem e autoria" + `tzdata`) e `feat/evals` (infraestrutura do
  eval) mergeadas na `main` e publicadas no GitHub em 16/11/2026. Nenhum código de `app/` mudou.

## Pendências do contexto do eval (respondidas lendo o código)
1. **Fallback automático.** `app/ai.py::route_and_ask` percorre `_build_attempts()`: groq/llama-3.3-70b
   → cerebras/gpt-oss-120b → mistral (piso pago, `PAID_FLOOR_ENABLED` + teto mensal em `app/budget.py`)
   → gemini. Pula a perna por exceção ou resposta vazia. Produção usa `AI_PRIMARY=groq` e `AI_FALLBACK=gemini`
   (o Groq é o primário, não o Gemini). A ordem segue a LGPD.
2. **Testes:** 392 coletados (314 funções; 244 delas do Flávio por `git blame`). O README antigo dizia 27.
3. **Schema do briefing:** `app/briefing.py::BRIEFING_FIELDS` (29 campos) + `temperatura_lead`.
   `normalize_lead_data` coage datas e quantidades; `gate_missing_fields` define o mínimo pra fechar
   (datas cotáveis, ≥1 adulto, indicação tratada; o cruzeiro é mais frouxo).
4. **Entrada do turno sem webhook:** `app/main.py::_process_text_message(phone, text, name, from_audio=)`.
   Os stubs de I/O estão em `scripts/conformance_probe.py::_install_stubs`.

## Arquitetura do eval (`evals/`)
- `harness.py`: stubs da sonda + provedor forçado no `settings` em memória + monkeypatch em
  `ai._ask_provider` (latência e retry) e `ai._log_usage` (tokens). `QuotaExhausted` herda de
  BaseException pra atravessar os `except Exception` de produção e parar a rodada.
- `run.py`: CLI, estimativa (`--dry-run`), travas de chamada e custo, retomada por `--run`.
- `metrics.py`: normalização e métricas puras. `report.py` gera o `summary.md` só com a rodada completa.
- `dataset/casos.jsonl`: 30 casos sintéticos em 7 categorias.

## Piloto (16/11/2026, caso `feliz-05`, k=1). Valida o encanamento, não é resultado
- **Gemini 2.5 Flash:** fechou o briefing no turno 2, com 3 chamadas (2 de chat, 1 de extração) e 14.179 + 883 tokens
  (≈ US$ 0,0065). Chat em ~6–7 s, extração em ~3,9 s. Acertou 6 de 7 campos; errou a `origem`
  ("saindo de Porto Alegre" veio nula na extração). O SDK reportou 0 token de thinking (não confirmado).
  Bruto em `evals/results/piloto-2026-11-16_gemini.jsonl`.
- **Llama 3.3 70B no Groq:** a chave nova (free) responde **404 `model_not_found`**. A conta só enxerga
  `openai/gpt-oss-120b`, `openai/gpt-oss-20b`, `qwen/qwen3.8-27b`, `allam-2-7b`, Whisper e guards. A
  página oficial mostra o 70B como "Enterprise / Contact Sales". **Decisão (16/11): o 2º modelo do eval
  passa a ser `openai/gpt-oss-120b` no Groq**, o mesmo da perna Cerebras de produção.
- **gpt-oss-120b (Groq):** fechou no turno 2, com 3 chamadas e 13.690 + 2.860 tokens (≈ US$ 0,0038).
  Chat p50 em ~4,6 s. Acertou 7 de 7 campos. **Bug de produção achado:** a 1ª resposta bateu o teto
  `_MAX_TOKENS=1024` com 958 tokens de raciocínio, e o texto pro cliente saiu cortado ("…2 adultos, hotel").
  A perna Cerebras usava o mesmo teto. **Corrigido em 16/11:** modelo de raciocínio (`gpt-oss`) usa
  `_MAX_TOKENS_REASONING=4096` no chat, e `finish_reason=length` no chat vira `TruncatedReplyError`
  (a cadeia segue pra próxima perna; no Mistral os tokens cortados ainda contam na trava). Prova real
  (`results/prova-corte-2026-11-16_groq.jsonl`): o turno 3 usou 1.438 tokens de saída (1.114 de
  raciocínio), passou do teto antigo e chegou inteiro. 7/7 campos, 0 corte.
- **Indicação reperguntada, corrigida em 16/11:** o cliente dizia "ninguém me indicou" no 1º turno e o gate
  perguntava de novo, porque "ninguém" vira `indicado_por` nulo. `indicacao_respondida_pelo_cliente()`
  reconhece formas de resposta; pedido de dica ("me indica um hotel?") não conta. Prova real
  (`results/prova-indicacao-2026-11-16_groq.jsonl`, código `031d668`): fechou no turno 2, não no 3, com 7/7 campos.
- **Rodada `2026-11-17` (iniciada em 16/11 às 17:40) é descartável:** rodou com o código anterior às duas
  correções e sem `code_version`. O Gemini parou no caso 3 com **429 de cota DIÁRIA do free tier**, por volta
  da 20ª chamada do dia. Pelo observado, o free tier do 2.5 Flash fica em ~20 req/dia (a doc manda ver em
  https://aistudio.google.com/rate-limit). No Groq, uma falha de DNS local quebrou o caso 1: agora a falha
  de rede ganha retry e, se persistir, para a rodada.
- **2º braço trocado em 16/11: Gemini 2.5 Flash → `openai/gpt-oss-20b` (Groq).** O Gemini free dá ~20 req/dia,
  a rodada pede ~180 chamadas por braço (6 por conversa, medido em 4 casos) e o billing pede cartão (o Flávio não
  vai ativar). Os braços agora são `groq` (120b) e `groq-20b` em `evals/config.yaml` (`provider` + `model`).
  **Bloqueio atual:** o 20b responde 403 `model_permission_blocked_org`; o Flávio libera em
  https://console.groq.com/settings/limits. Depois disso: piloto
  `python -m evals.run --provider groq-20b --run piloto-2026-11-16 --cases feliz-05`.
- O piloto achou 2 bugs do eval, já corrigidos: o booleano `True` vindo do extrator não era reconhecido, e
  um 404 de modelo gravava o caso em vez de parar a rodada.
- Projeção da rodada completa (N=30, k=1): ~180 chamadas e ~1M de tokens por braço; 120b ≈ US$ 0,20 no preço
  pago, 20b ≈ metade. Cada modelo do Groq tem a própria cota (200k tokens/dia, 8k/min): **~7 dias** pros dois,
  rodando em sequência no mesmo comando.

## Próximos passos
1. **Conferir o deploy da correção do corte** no Railway (se o auto-deploy da `main` estiver ligado, sobe
   sozinho) e procurar `resposta de chat cortada` nos logs.
2. **Conferir produção:** se a chave do Railway também perdeu o 70B, toda mensagem cai na perna
   Cerebras (procurar `model_not_found` nos logs do Railway).
   Se perdeu, trocar o `GROQ_MODEL` (o `gpt-oss-120b` está no free).
3. Rodada completa, fatiada por dia: `python -m evals.run --provider all --run 2026-11-17`, repetindo com o
   mesmo `--run` (roda o 120b até a cota do dia e depois o 20b).
4. `python -m evals.report --run <id>` → seção "Avaliação" no README com tabela, N, k, data e limitações.
5. Só então a linha do eval entra no CV.

## Perguntas abertas
- O deploy do Railway vinha do GitHub ou de `railway up` no PC antigo? Se foi pela CLI, produção pode
  estar à frente do `e17e079`.
- `COLETA_STATE_ENABLED` está ligado no Railway? O eval assume que sim.
- A última perna de produção (Gemini 2.5 Flash) muda de modelo em 01/12/2026. Decidir se fixa outro modelo.
