# Eval comparativo da Malu: gpt-oss-120b × gpt-oss-20b (Groq)

**Estado (16/11/2026): infraestrutura pronta e piloto feito; rodada completa ainda não feita.** Não há
número publicado: um eval pela metade não vira tabela. `report.py` se recusa a gravar o `summary.md`
enquanto faltar algum caso × repetição.

**Por que gpt-oss-120b e não Llama 3.3 70B:** o plano era comparar com o Llama 3.3 70B, o primário
da cadeia de produção. Em 16/11/2026 a conta free do Groq respondeu `404 model_not_found` pra ele, e a
página oficial passou a listá-lo como "Enterprise / Contact Sales". O `openai/gpt-oss-120b` está
disponível no free tier e é o mesmo modelo da perna Cerebras de produção, que assume quando o
Groq falha.

**Por que gpt-oss-20b e não Gemini 2.5 Flash:** o 2º braço era o Gemini, a última perna da cadeia de
produção. No free tier ele parou com 429 de cota diária por volta da 20ª chamada (16/11/2026), e a
rodada pede ~180 chamadas por braço (6 por conversa, medido). Seriam 9 ou 10 dias sem falhar nenhum,
colado no 01/12/2026, quando o Google passa a rotear o `gemini-2.5-flash` pro 3.5 Flash-Lite. Ativar
billing exige cartão. O `openai/gpt-oss-20b` roda no mesmo provedor e pelo mesmo caminho de código do
120b, então a comparação isola uma pergunta só: **o modelo menor, pela metade do preço, segura a
qualidade do briefing?** O piloto do Gemini (`results/piloto-2026-11-16_gemini.jsonl`) fica como registro.

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
| Custo por conversa | Tokens de entrada e saída (raciocínio incluso) × `pricing.yaml` |
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

Publicado no Hugging Face (CC-BY-4.0), com card descrevendo campos, categorias e pontuação:
[Flaviortw/malu-briefing-eval-ptbr](https://huggingface.co/datasets/Flaviortw/malu-briefing-eval-ptbr).

## Como rodar

```bash
pip install -r requirements.txt -r evals/requirements.txt
# .env com GROQ_API_KEY (os WA_* podem ser fictícios); os braços estão em config.yaml
python -m evals.run --provider all --dry-run     # estimativa de chamadas, tokens e custo
python -m evals.run --provider groq-20b --limit 1    # piloto de um braço
python -m evals.run --provider all               # rodada (retoma de onde parou)
python -m evals.run --provider all --run 2026-11-16   # continua a rodada de outro dia
python -m evals.report --run 2026-11-16          # gera results/summary.md (só com a rodada completa)
```

Os resultados brutos vão para `results/<run>_<provedor>.jsonl`, uma linha por caso × repetição, com os turnos, as respostas
e cada chamada (tokens, latência, retries, erro).

## O que já está em `results/` (piloto e prova de bug, não é resultado)

Nenhum arquivo abaixo é amostra da comparação: são 1 a 3 conversas cada, rodadas pra validar o
encanamento ou provar uma correção. Não tirar média nem taxa deles.

| Arquivo | O que é | Como ler |
|---|---|---|
| `piloto-2026-11-16_gemini.jsonl` | Piloto do Gemini 2.5 Flash, antes de ele sair do eval | Registro histórico |
| `piloto-2026-11-16_groq.jsonl` | Piloto do gpt-oss-120b | Mostra o bug do corte: a 1ª resposta bateu o teto antigo de 1024 tokens |
| `prova-corte-2026-11-16_groq.jsonl` | Prova da correção do corte | O turno 3 passou do teto antigo e chegou inteiro |
| `prova-indicacao-2026-11-16_groq.jsonl` | Prova da correção da indicação reperguntada | Fechou no turno 2, não no 3 |
| `piloto-2026-11-16_groq-20b.jsonl` | Piloto do gpt-oss-20b (5 linhas) | Ver abaixo |

No piloto do 20b:
- **`feliz-05`:** `field_scores` todo `false` e `truncated_chat: 1` **não** querem dizer que o modelo
  errou os campos. O 1º turno gastou 4.094 tokens de raciocínio e bateu o teto de 4096. A proteção de
  produção (`TruncatedReplyError`) recusou mandar a frase cortada e passou a conversa pra atendente
  humana, então não houve briefing para pontuar. Isso é o comportamento certo da Malu diante de um
  modelo que travou no raciocínio.
- **`ambiguo-02` e `feliz-02` aparecem duas vezes.** A 1ª gravação quebrou com 413 "tokens per minute"
  do Groq free, um limite da conta e não do modelo. Depois da correção do harness (retry + refazer linha
  com erro de cota), os dois foram refeitos com 0 erro. O relatório usa sempre a gravação mais nova.

A rodada de verdade sai em `<run>_<braço>.jsonl` e só vira tabela no `summary.md`, quando estiver completa.

## Travas (`config.yaml`)
- `max_llm_calls_per_provider` e `max_cost_usd`: a rodada para antes de passar disso.
- Cota diária estourada (429 com "per day") **para a rodada sem gravar o caso em andamento**.
  O `--resume` implícito refaz esse caso depois. Um 429 por minuto ganha retry com backoff (20/40/80 s).

## Limites do free tier
Cada chamada de chat leva o prompt inteiro da Malu, ~23,6 mil caracteres (≈6,5 mil tokens). No Groq, a
conta free do `gpt-oss-120b` tem **8.000 tokens/min** e 1.000 requisições/dia (medido nos cabeçalhos
`x-ratelimit` em 16/11/2026); a página de rate limits lista 200 mil tokens/dia. Por isso o config usa
60 s entre turnos no Groq, e a rodada se fatia em dias com `--run`. A estimativa por provedor sai do
`--dry-run`, que usa a média de tokens observada depois do piloto.

## Limitações conhecidas (vão pro relatório)
- Dados sintéticos e N pequeno; turnos roteirizados.
- Os dois braços usam o mesmo caminho de produção (`_ask_malu_groq`): temperatura 0.2 no chat, 0.0 na
  extração; teto de saída de 4096 tokens no chat pra modelo de raciocínio (`gpt-oss`) e 3000 na extração.
  O raciocínio entra em `completion_tokens` e é cobrado como saída.
- O gpt-oss-120b no Groq não é exatamente a perna de produção, que roda o mesmo modelo na Cerebras
  (outro hardware, outra latência). Qualidade e tokens devem ser próximos; a latência não se transfere.
- Preço na data da consulta (`pricing.yaml`).
- A última perna de produção (Gemini) fica fora do eval: free tier curto demais (ver acima).
- `COLETA_STATE_ENABLED=true` no config (uma extração extra por turno). Confirmar se produção está igual.
