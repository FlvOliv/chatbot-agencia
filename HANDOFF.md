# HANDOFF: chatbot-agencia (Malu / Lu Milhas)

Doc de estado. Atualizar números e pendências; não narrar sessão.

## Estado (16/11/2026)
- Repo restaurado no PC novo a partir do fork público (`main@e17e079`, 06/07/2026). O que não tinha
  sido enviado pro GitHub do PC antigo **não está aqui** (o `.env` inclusive).
- Suíte: **392 testes** coletados, 392 passando no Windows/Python 3.12 (precisou do `tzdata`).
  Com os testes do eval (`tests/test_evals.py`): 419.
- Prompt em produção: `app/prompts/malu_v4.md`, conteúdo **v5.0**.
- Branches locais: `docs/origem-autoria` (README com "Origem e autoria" + `tzdata`) e `feat/evals`
  (infraestrutura do eval). **Nada enviado pro GitHub ainda.**

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

## Próximos passos
1. O Flávio cola `GEMINI_API_KEY` e `GROQ_API_KEY` no `.env` (local, gitignored).
2. Piloto: `python -m evals.run --provider all --limit 1`. Confere o `.jsonl` e o `--dry-run` passa a usar
   a média de tokens observada.
3. Rodada completa: ~2 semanas no free tier (Groq 70B ≈ 100k tokens/dia) ou tier pago com teto em
   `config.yaml`. **Antes de 01/12/2026**, quando o `gemini-2.5-flash` passa a rotear pro 3.5 Flash-Lite.
4. `python -m evals.report --run <id>` → seção "Avaliação" no README com tabela, N, k, data e limitações.
5. Só então a linha do eval entra no CV.

## Perguntas abertas
- O deploy do Railway vinha do GitHub ou de `railway up` no PC antigo? Se foi pela CLI, produção pode
  estar à frente do `e17e079`.
- `COLETA_STATE_ENABLED` está ligado no Railway? O eval assume que sim.
- A última perna de produção (Gemini 2.5 Flash) muda de modelo em 01/12/2026. Decidir se fixa outro modelo.
