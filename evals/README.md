# Eval comparativo da Malu: Gemini 2.5 Flash × Llama 3.3 70B

**Estado (16/11/2026): infraestrutura pronta, rodada completa ainda não feita.** Não há número
publicado: um eval pela metade não vira tabela. `report.py` se recusa a gravar o `summary.md`
enquanto faltar algum caso × repetição.

## O que mede

Cada conversa sintética roda pelo **mesmo caminho de produção** (`app.main._process_text_message`:
o prompt real, a extração JSON do briefing, o gate de completude, o anti-loop e o `price_guard`), forçando um único
provedor por vez. O I/O externo é stubbado com os stubs da suíte de conformidade
(`scripts/conformance_probe.py`): nada vai pra Meta nem pra Lu, a sessão roda em fakeredis e
o Postgres é falso. Nenhum código de produção muda; o provedor é forçado só no `settings` do processo.

| Métrica | Definição |
|---|---|
| Acerto por campo | Campo do briefing final × gold, com a normalização abaixo. Só nos casos que deviam fechar; caso que não fechou conta como erro |
| Acerto condicional | O mesmo, só nas conversas que de fato fecharam |
| Briefing completo | % dos casos que deviam fechar e fecharam (o fecho exige passar pelo `gate_missing_fields`) |
| Turnos até o briefing | Média e mediana do turno em que o lead foi finalizado |
| Guardrails | % de pass da regra objetiva de cada caso (`guard` no dataset) |
| Fecho indevido | Casos que não deviam fechar e fecharam |
| Custo por conversa | Tokens de entrada e saída (thinking do Gemini incluso) × `pricing.yaml` |
| Latência | p50/p95 do round-trip de cada chamada de LLM (só a API, sem log nem sleep) e soma por conversa |
| Erro | % de chamadas que falharam depois dos retries; retries por 429 contados à parte |
| Variação | Desvio-padrão do acerto entre as k repetições de um mesmo caso |

### Normalização do gold (`metrics.py`)
- **Texto livre** (destino, origem, região, indicação): minúsculas, sem acento, sem pontuação. Acerta
  se todos os tokens do gold aparecem no extraído (`lisboa` × `Lisboa, Portugal` = acerto).
- **Quantidades:** primeiro número, inclusive por extenso até 10 (`duas pessoas` = 2).
- **Datas:** dia e mês têm que bater. O ano só é comparado quando os dois lados o têm. Aceita
  `dd/mm`, `dd/mm/aaaa`, `aaaa-mm-dd` e `12 de março`.
- **Idades:** conjunto de inteiros. **Sim/não:** negação ("não", "sem", "dispensa") vence.
- `pendente (...)` e `Não informado` contam como vazio.

## Dataset

`dataset/casos.jsonl`: 30 conversas **sintéticas** (nenhum dado de cliente real; telefones gerados
com DDD 00, que não existe). Categorias: `feliz` (8), `incompleto` (4), `ambiguo` (4),
`pede_preco` (4), `prompt_injection` (4), `fora_de_escopo` (3) e `audio_transcrito` (3), este
rodando com `from_audio=True`. Os turnos do cliente são roteirizados: não reagem ao que a Malu pergunta.

## Como rodar

```bash
pip install -r requirements.txt -r evals/requirements.txt
# .env com GEMINI_API_KEY e GROQ_API_KEY (os WA_* podem ser fictícios)
python -m evals.run --provider all --dry-run     # estimativa de chamadas, tokens e custo
python -m evals.run --provider groq --limit 1    # piloto
python -m evals.run --provider all               # rodada (retoma de onde parou)
python -m evals.run --provider all --run 2026-11-16   # continua a rodada de outro dia
python -m evals.report --run 2026-11-16          # gera results/summary.md (só com a rodada completa)
```

Os resultados brutos vão para `results/<run>_<provedor>.jsonl`, uma linha por caso × repetição, com os turnos, as respostas
e cada chamada (tokens, latência, retries, erro).

## Travas (`config.yaml`)
- `max_llm_calls_per_provider` e `max_cost_usd`: a rodada para antes de passar disso.
- Cota diária estourada (429 com "per day") **para a rodada sem gravar o caso em andamento**.
  O `--resume` implícito refaz esse caso depois. Um 429 por minuto ganha retry com backoff (20/40/80 s).

## Limites do free tier (por que a rodada não fechou em 16/11)
Cada chamada de chat leva o prompt inteiro da Malu, ~23,6 mil caracteres (≈7 mil tokens). A estimativa do
`--dry-run` para N=30 e k=1 é ~1,26M tokens de entrada **por provedor**. No free tier, o Llama 3.3 70B do Groq
tem teto de ~100 mil tokens por dia, o que dá umas 2 conversas por dia. Fechar a rodada leva ~2 semanas no
free tier ou poucos dólares no tier pago (estimativa no `--dry-run`).

## Limitações conhecidas (vão pro relatório)
- Dados sintéticos e N pequeno; turnos roteirizados.
- **Os dois caminhos de produção não usam a mesma configuração.** O Groq roda com temperatura 0.2 no chat
  (0.0 na extração) e `max_tokens` 1024/3000. O Gemini roda com o padrão do SDK `google.generativeai`:
  sem temperatura explícita, sem teto de saída e com thinking ligado no 2.5 Flash. O eval mede o caminho
  **como está em produção**, sem igualar.
- Preço na data da consulta (`pricing.yaml`). O preço do Llama 3.3 70B não aparece na página oficial
  do Groq em 16/11/2026.
- O `gemini-2.5-flash` está depreciado: a partir de 01/12/2026 o Google roteia as chamadas para o
  Gemini 3.5 Flash-Lite. Uma rodada depois dessa data mede outro modelo.
- `COLETA_STATE_ENABLED=true` no config (uma extração extra por turno). Confirmar se produção está igual.
