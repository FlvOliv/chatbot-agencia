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
  A perna Cerebras usa o mesmo teto (`app/ai.py:354`). O eval agora conta isso (`truncated_chat`).
- O piloto achou 2 bugs do eval, já corrigidos: o booleano `True` vindo do extrator não era reconhecido, e
  um 404 de modelo gravava o caso em vez de parar a rodada.
- Projeção da rodada completa (N=30, k=1, médias do piloto): Gemini ≈ 1,15M + 72k tokens (US$ 0,53 no
  preço pago); gpt-oss ≈ 1,11M + 233k tokens (US$ 0,31). No free tier do Groq (200k tokens/dia, 8k/min),
  são **~7 dias**.

## Próximos passos
1. **Corrigir o corte em produção:** teto de saída maior pros modelos de raciocínio na perna
   OpenAI-compatible e no Groq, ou `reasoning_effort` baixo. Hoje o cliente pode receber frase pela metade.
2. **Conferir produção:** se a chave do Railway também perdeu o 70B, toda mensagem cai na perna
   Cerebras (procurar `model_not_found` nos logs do Railway). Somado ao item 1, isso pode cortar respostas reais.
3. Rodada completa **antes de 01/12/2026**, quando o `gemini-2.5-flash` passa a rotear pro 3.5 Flash-Lite.
   Fatiar por dia: `python -m evals.run --provider all --run 2026-11-17` e repetir com o mesmo `--run`.
4. `python -m evals.report --run <id>` → seção "Avaliação" no README com tabela, N, k, data e limitações.
5. Só então a linha do eval entra no CV.

## Perguntas abertas
- O deploy do Railway vinha do GitHub ou de `railway up` no PC antigo? Se foi pela CLI, produção pode
  estar à frente do `e17e079`.
- `COLETA_STATE_ENABLED` está ligado no Railway? O eval assume que sim.
- A última perna de produção (Gemini 2.5 Flash) muda de modelo em 01/12/2026. Decidir se fixa outro modelo.
