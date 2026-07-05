"""Testes do extrator/parser de briefing."""

from __future__ import annotations

import pytest

from app.briefing import (
    NAO_INFORMADO,
    ask_missing_fields,
    build_recap,
    extract_briefing,
    extract_customer_name,
    gate_missing_fields,
    indicacao_foi_perguntada,
    lead_columns_from_data,
    merge_ficha,
    normalize_lead_data,
    normalize_temp,
    parse_customer_whatsapp,
    parse_lead_temp,
    render_briefing,
    save_lead,
    split_reply_and_briefing,
    split_reply_and_transfer,
)
from app.models import Lead


class _FakeLeadSession:
    """Sessão falsa que captura os leads inseridos (sem Postgres real)."""

    def __init__(self) -> None:
        self.added: list[Lead] = []

    def add(self, obj: Lead) -> None:
        self.added.append(obj)

    async def flush(self) -> None:
        # Simula o banco gerando o número de protocolo (sequência).
        for i, lead in enumerate(self.added):
            if lead.numero is None:
                lead.numero = 1001 + i

    async def refresh(self, obj: Lead) -> None:  # noqa: ARG002
        pass


@pytest.mark.asyncio
async def test_save_lead_insere_nova_cotacao_a_cada_chamada() -> None:
    """Mesmo cliente, 2 cotações → 2 leads distintos (NÃO sobrescreve)."""
    db = _FakeLeadSession()

    lead1 = await save_lead(
        "5511999998888", db, briefing_md="cotação 1", lead_temp="quente", name="Ana"
    )
    lead2 = await save_lead(
        "5511999998888", db, briefing_md="cotação 2", lead_temp="frio", name="Ana"
    )

    assert lead1 is not lead2  # dois objetos distintos
    assert len(db.added) == 2  # inseriu dois — não fez upsert
    assert lead1.briefing_md == "cotação 1"
    assert lead2.briefing_md == "cotação 2"
    assert lead1.numero != lead2.numero  # números de protocolo diferentes


@pytest.mark.asyncio
async def test_save_lead_ignora_campos_opcionais_vazios() -> None:
    """Campos opcionais vazios não viram colunas (ficam None no lead novo)."""
    db = _FakeLeadSession()
    lead = await save_lead(
        "5511999998888", db, briefing_md="b", lead_temp="morno", destination=""
    )
    assert lead.destination is None
    assert lead.phone == "5511999998888"


BRIEFING_SAMPLE = """Perfeito! Já organizei suas informações.

## Resumo da Solicitação de Cotação

**Nome do cliente:** Wana
**WhatsApp:** 5511987654321
**Tipo de atendimento:** Pacote completo
**Origem:** São Paulo
**Destino:** Salvador
**Temperatura do lead:** Quente
**Observações importantes:** cliente quer hospedagem em Itapuã
"""


def test_extract_briefing_finds_block() -> None:
    out = extract_briefing(BRIEFING_SAMPLE)
    assert out is not None
    assert out.startswith("## Resumo da Solicitação")
    assert "Wana" in out
    assert "Itapuã" in out


def test_extract_briefing_returns_none_when_absent() -> None:
    assert extract_briefing("Olá! Tudo bem?") is None
    assert extract_briefing("") is None


@pytest.mark.parametrize(
    "temp_value,expected",
    [
        ("Frio", "frio"),
        ("Morno", "morno"),
        ("Quente", "quente"),
        ("Urgente", "urgente"),
        ("morno para quente", "morno"),
        ("MUITO QUENTE", "quente"),
    ],
)
def test_parse_lead_temp_variants(temp_value: str, expected: str) -> None:
    briefing = f"## Resumo da Solicitação\n**Temperatura do lead:** {temp_value}\n"
    assert parse_lead_temp(briefing) == expected


def test_parse_lead_temp_default_when_missing() -> None:
    briefing = "## Resumo da Solicitação\n**Nome:** X\n"
    assert parse_lead_temp(briefing) == "morno"


def test_parse_customer_whatsapp_finds_value() -> None:
    assert parse_customer_whatsapp(BRIEFING_SAMPLE) == "5511987654321"


def test_parse_customer_whatsapp_returns_none_when_absent() -> None:
    briefing = "## Resumo da Solicitação\n**Nome:** X\n"
    assert parse_customer_whatsapp(briefing) is None
    assert parse_customer_whatsapp("") is None


def test_parse_customer_whatsapp_value_on_next_line() -> None:
    briefing = "## Resumo da Solicitação\n**WhatsApp:**\n5511912345678\n"
    assert parse_customer_whatsapp(briefing) == "5511912345678"


def test_extract_customer_name_finds_real_name() -> None:
    assert extract_customer_name(BRIEFING_SAMPLE) == "Wana"


def test_extract_customer_name_ignores_placeholders() -> None:
    cases = [
        "## Resumo\n**Nome do cliente:** [Aguardando você me informar]\n",
        "## Resumo\n**Nome do cliente:** N/A\n",
        "## Resumo\n**Nome do cliente:** Não informado\n",
        "## Resumo\n**Nome do cliente:** —\n",
    ]
    for briefing in cases:
        assert extract_customer_name(briefing) is None, f"falhou em: {briefing!r}"


def test_extract_customer_name_returns_none_when_field_missing() -> None:
    briefing = "## Resumo\n**Destino:** Cancún\n"
    assert extract_customer_name(briefing) is None
    assert extract_customer_name("") is None


# ---------------------------------------------------------------------------
# Briefing ESTRUTURADO — render / split / colunas / temperatura
# ---------------------------------------------------------------------------
def test_render_briefing_marks_missing_as_nao_informado() -> None:
    """Campo não informado pela IA NUNCA é inventado — vira 'Não informado'."""
    data = {"destino": "Maceió", "nome_cliente": "Ana", "temperatura_lead": "quente"}
    out = render_briefing(data, "5511999998888")
    assert "**Destino:** Maceió" in out
    assert "**Nome do cliente:** Ana" in out
    # os campos que estouravam (pagamento/motivo) agora ficam Não informado
    assert f"**Forma de pagamento:** {NAO_INFORMADO}" in out
    assert f"**Motivo da viagem:** {NAO_INFORMADO}" in out
    assert "**Temperatura do lead:** Quente" in out
    # WhatsApp cai pro número real do webhook quando a IA não capturou
    assert "**WhatsApp:** 5511999998888" in out


def test_render_briefing_treats_placeholders_as_missing() -> None:
    data = {"forma_pagamento": "Não informado", "destino": "—", "origem": "n/a"}
    out = render_briefing(data)
    assert f"**Forma de pagamento:** {NAO_INFORMADO}" in out
    assert f"**Destino:** {NAO_INFORMADO}" in out
    assert f"**Origem:** {NAO_INFORMADO}" in out


def test_render_briefing_defaults_temp_to_morno() -> None:
    assert "**Temperatura do lead:** Morno" in render_briefing({})
    assert "**Temperatura do lead:** Morno" in render_briefing({"temperatura_lead": "xpto"})


def test_lead_columns_from_data_maps_fields() -> None:
    data = {
        "nome_cliente": "Ana",
        "destino": "Maceió",
        "tipo_atendimento": "Pacote completo",
        "temperatura_lead": "urgente",
    }
    assert lead_columns_from_data(data) == {
        "name": "Ana",
        "destination": "Maceió",
        "travel_type": "Pacote completo",
        "indicado_por": None,
        "lead_temp": "urgente",
    }


def test_lead_columns_captura_indicado_por() -> None:
    """Quem indicou vira coluna própria (programa de indicação)."""
    cols = lead_columns_from_data({"indicado_por": "Tia Lu (5511988887777)"})
    assert cols["indicado_por"] == "Tia Lu (5511988887777)"


def test_render_briefing_inclui_indicado_por() -> None:
    out = render_briefing({"indicado_por": "Maria Silva"})
    assert "**Indicado por:** Maria Silva" in out
    # sem indicação → cai pro "Não informado" como qualquer campo ausente
    assert f"**Indicado por:** {NAO_INFORMADO}" in render_briefing({})


@pytest.mark.asyncio
async def test_save_lead_persiste_indicado_por() -> None:
    db = _FakeLeadSession()
    lead = await save_lead(
        "5511999998888",
        db,
        briefing_md="b",
        lead_temp="morno",
        indicado_por="João",
    )
    assert lead.indicado_por == "João"


def test_lead_columns_nulls_become_none() -> None:
    cols = lead_columns_from_data({"nome_cliente": None, "destino": ""})
    assert cols["name"] is None
    assert cols["destination"] is None
    assert cols["lead_temp"] == "morno"  # default


def test_split_reply_separates_briefing_block() -> None:
    reply = (
        "Perfeito, Ana! Já tenho tudo.\n\n"
        "## Resumo da Solicitação de Cotação\n"
        "**Nome do cliente:** Ana\n"
    )
    customer, block = split_reply_and_briefing(reply)
    assert customer == "Perfeito, Ana! Já tenho tudo."
    assert block is not None and block.startswith("## Resumo da Solicitação")


def test_split_reply_without_block() -> None:
    customer, block = split_reply_and_briefing("Oi! Tudo bem?")
    assert customer == "Oi! Tudo bem?"
    assert block is None


def test_split_reply_ignores_empty_briefing_header() -> None:
    # Modelo escreveu o header no meio da frase, sem os campos → NÃO finaliza
    # (senão vira lead/protocolo espúrio) e o header não vaza pro cliente.
    reply = (
        "Em breve ela entra em contato com o\n\n"
        "## Resumo da Solicitação de Cotação\n"
    )
    customer, block = split_reply_and_briefing(reply)
    assert block is None
    assert "## Resumo" not in customer


def test_split_transfer_detects_marker() -> None:
    reply = "Claro! Já vou chamar a Lu pra te ajudar com isso 🙌\n\n## TRANSFERIR"
    customer, wants = split_reply_and_transfer(reply)
    assert wants is True
    assert "## TRANSFERIR" not in customer
    assert customer == "Claro! Já vou chamar a Lu pra te ajudar com isso 🙌"


def test_split_transfer_case_insensitive() -> None:
    customer, wants = split_reply_and_transfer("Beleza!\n## transferir")
    assert wants is True
    assert customer == "Beleza!"


def test_split_transfer_without_marker() -> None:
    customer, wants = split_reply_and_transfer("Qual a sua cidade de origem?")
    assert wants is False
    assert customer == "Qual a sua cidade de origem?"


def test_split_transfer_empty() -> None:
    customer, wants = split_reply_and_transfer("")
    assert wants is False
    assert customer == ""


def test_normalize_temp_variants() -> None:
    assert normalize_temp("Quente") == "quente"
    assert normalize_temp("muito urgente mesmo") == "urgente"
    assert normalize_temp("xyz") == "morno"
    assert normalize_temp(None) == "morno"


# ---------------------------------------------------------------------------
# Gate de completude — NÃO finaliza lead com coleta furada (mínimo crítico)
# ---------------------------------------------------------------------------
_INDIC_ASKED = [{"role": "assistant", "content": "Alguém indicou a Lu pra você?"}]


def _complete_data() -> dict:
    """Dados normalizados de uma coleta COMPLETA (passa no gate)."""
    return normalize_lead_data(
        {"data_ida": "26/07", "data_volta": "31/07", "qtd_adultos": "1"}
    )


def test_gate_blocks_vague_date() -> None:
    # "mês que vem" → normalize marca pendente → gate barra a data de ida.
    data = normalize_lead_data(
        {"data_ida": "mês que vem", "data_volta": "31/07", "qtd_adultos": "1"}
    )
    missing = gate_missing_fields(data, _INDIC_ASKED)
    assert "a data de ida" in missing


def test_gate_blocks_missing_indicacao() -> None:
    # Tudo concreto, mas a Malu NUNCA perguntou indicação → barra.
    missing = gate_missing_fields(_complete_data(), history=[])
    assert "__indicacao__" in missing


def test_gate_blocks_missing_passengers() -> None:
    data = normalize_lead_data({"data_ida": "26/07", "data_volta": "31/07"})
    missing = gate_missing_fields(data, _INDIC_ASKED)
    assert "quantas pessoas vão viajar" in missing


def test_gate_passes_when_complete() -> None:
    assert gate_missing_fields(_complete_data(), _INDIC_ASKED) == []


def test_gate_accepts_one_way() -> None:
    # Só ida → não exige data de volta (mesmo virando "pendente" no normalize).
    data = normalize_lead_data(
        {"data_ida": "26/07", "data_volta": "somente ida", "qtd_adultos": "1"}
    )
    missing = gate_missing_fields(data, _INDIC_ASKED)
    assert "a data de volta (ou se é só ida)" not in missing
    assert missing == []


def test_gate_accepts_one_way_from_history() -> None:
    """Bug real de produção: o cliente diz 'só ida' e o extrator deixa data_volta
    NULO → o gate NÃO pode exigir data de volta, senão repete o nudge pra sempre
    (loop das conversas UM/DOIS/TRÊS)."""
    data = normalize_lead_data({"data_ida": "10/07", "qtd_adultos": "1"})  # volta nula
    history = _INDIC_ASKED + [
        {"role": "user", "content": "somente ida de SP para RJ, dia 10, 1 pessoa"}
    ]
    missing = gate_missing_fields(data, history)
    assert "a data de volta (ou se é só ida)" not in missing
    assert missing == []


@pytest.mark.parametrize(
    "fala",
    ["só ida", "so ida", "é so ida", "Só ida.", "Somente ida. Dia 08.", "sem volta"],
)
def test_gate_detecta_so_ida_em_variantes(fala: str) -> None:
    data = normalize_lead_data({"data_ida": "10/07", "qtd_adultos": "1"})
    history = _INDIC_ASKED + [{"role": "user", "content": fala}]
    assert "a data de volta (ou se é só ida)" not in gate_missing_fields(data, history)


def test_gate_ainda_exige_volta_sem_marcador() -> None:
    """Regressão: sem sinal de só-ida e sem data_volta → segue exigindo a volta."""
    data = normalize_lead_data({"data_ida": "10/07", "qtd_adultos": "1"})
    history = _INDIC_ASKED + [{"role": "user", "content": "ida de SP pro Rio dia 10"}]
    assert "a data de volta (ou se é só ida)" in gate_missing_fields(data, history)


def test_gate_nao_confunde_malu_perguntando_so_ida() -> None:
    """A Malu perguntar 'é só ida ou tem volta?' NÃO marca a viagem como só-ida —
    só a fala do CLIENTE conta (senão marcaria antes de o cliente confirmar)."""
    data = normalize_lead_data({"data_ida": "10/07", "qtd_adultos": "1"})
    history = _INDIC_ASKED + [
        {"role": "assistant", "content": "É só ida mesmo, sem volta?"},
        {"role": "user", "content": "dia 10"},
    ]
    assert "a data de volta (ou se é só ida)" in gate_missing_fields(data, history)


def test_gate_aceita_indicacao_espontanea() -> None:
    """Cliente conta quem indicou (ou que ninguém indicou) SEM a Malu ter
    perguntado → o gate não exige o ritual da pergunta, senão a Malu repergunta
    o que o cliente acabou de responder (visto no cenário S3 da suíte de
    conformidade de 05/07)."""
    data = normalize_lead_data(
        {
            "data_ida": "10/08",
            "data_volta": "15/08",
            "qtd_adultos": "2",
            "indicado_por": "Ninguém",
        }
    )
    assert gate_missing_fields(data, history=[]) == []


def test_indicacao_foi_perguntada() -> None:
    assert indicacao_foi_perguntada(_INDIC_ASKED) is True
    assert indicacao_foi_perguntada([{"role": "user", "content": "quem indicou?"}]) is False
    assert indicacao_foi_perguntada([]) is False


def test_ask_missing_fields_prioriza_dados_duros() -> None:
    # Falta data + indicação → pede os dados duros primeiro, 1 emoji só.
    msg = ask_missing_fields(["a data de ida", "__indicacao__"])
    assert "data de ida" in msg
    assert "indic" not in msg.lower()  # indicação fica pro próximo turno
    assert msg.count("💛") == 1


def test_ask_missing_fields_so_indicacao() -> None:
    msg = ask_missing_fields(["__indicacao__"])
    assert "indicou" in msg.lower()
    assert msg.count("💛") == 1


def test_gate_blocks_caso_1030_completo() -> None:
    """#1030 no shape exato: 'mês que vem' (ida) + 'fico 5 dias' (volta como
    DURAÇÃO, não data concreta) + menção de valor + indicação nunca perguntada.
    Mesmo com o atalho 'já finalizou?' na conversa, o gate barra o fecho e lista
    os 3 buracos de uma vez. O valor é ruído pro gate (não é campo) — não
    destrava nada. (NÃO valida se a data calculada está correta — isso é o LLM.)
    """
    history = [
        {"role": "user", "content": "quero Paris mês que vem, fico uns 5 dias"},
        {"role": "assistant", "content": "Que delícia, Paris é incrível! 💛"},
        {"role": "user", "content": "uns 8 mil tá bom? já finalizou?"},
    ]
    data = normalize_lead_data(
        {
            "data_ida": "mês que vem",
            "data_volta": "fico 5 dias",  # duração ≠ data de volta concreta
            "qtd_adultos": "2",
            "destino": "Paris",
        }
    )
    # Duração não casa _DATE_CONCRETE_RE → vira pendente (não satisfaz a volta).
    assert data["data_volta"].startswith("pendente (")
    missing = gate_missing_fields(data, history)  # Malu nunca disse "indic..."
    assert "a data de ida" in missing
    assert "a data de volta (ou se é só ida)" in missing
    assert "__indicacao__" in missing
    # Nudge pede os dados duros 1º; indicação fica pro próximo turno; 1 emoji só.
    nudge = ask_missing_fields(missing)
    assert "data de ida" in nudge and "data de volta" in nudge
    assert "indic" not in nudge.lower()
    assert nudge.count("💛") == 1


# ---------------------------------------------------------------------------
# Gate por TIPO — cruzeiro não se cota por data de ida/volta exata (03/07)
# ---------------------------------------------------------------------------
def test_gate_cruzeiro_caso_tia_aceita_periodo_e_ignora_volta() -> None:
    """Caso real (03/07): cruzeiro saindo de Santos, 'primeira quinzena de
    dezembro', 5-7 dias, 2 adultos. Período vago + sem data de volta É COMPLETO
    pra cruzeiro (a naviera define as saídas) — o gate NÃO pode pedir dd/mm exato
    nem volta, senão vira o loop que forçou a cliente a inventar '6/12'."""
    data = normalize_lead_data(
        {
            "tipo_atendimento": "Cruzeiro",
            "data_ida": "primeira quinzena de dezembro",  # vira "pendente"
            "qtd_adultos": "2",
            "origem": "Santos",
            "destino": "Nordeste",
        }
    )
    # Período vago vira pendente no normalize — mas pra cruzeiro isso BASTA.
    assert data["data_ida"].startswith("pendente (")
    missing = gate_missing_fields(data, _INDIC_ASKED)
    assert "a data de ida" not in missing
    assert "o período que você quer viajar" not in missing
    assert "a data de volta (ou se é só ida)" not in missing
    assert missing == []


def test_gate_cruzeiro_detecta_pela_history_no_fail_closed() -> None:
    """Extração sem tipo (data crua), mas o CLIENTE disse 'cruzeiro' → detecta
    pela history — espelha o dispatch, que roda o gate sobre {} no fail-closed."""
    data = normalize_lead_data(
        {"data_ida": "primeira quinzena de dezembro", "qtd_adultos": "2"}
    )
    history = _INDIC_ASKED + [
        {"role": "user", "content": "quero um cruzeiro saindo de Santos"}
    ]
    missing = gate_missing_fields(data, history)
    assert "a data de volta (ou se é só ida)" not in missing
    assert missing == []


def test_gate_cruzeiro_pede_periodo_se_nenhum() -> None:
    """Cruzeiro sem NENHUM período informado → pede o período uma vez (nunca um
    dia de embarque exato, que o cliente não tem como saber)."""
    data = normalize_lead_data({"tipo_atendimento": "Cruzeiro", "qtd_adultos": "2"})
    missing = gate_missing_fields(data, _INDIC_ASKED)
    assert "o período que você quer viajar" in missing
    assert "a data de ida" not in missing


def test_gate_voo_nao_afetado_pela_excecao_cruzeiro() -> None:
    """Regressão: voo comum segue exigindo ida/volta concretas — a exceção de
    data vaga vale SÓ pra cruzeiro, não pode vazar pros outros tipos."""
    data = normalize_lead_data(
        {
            "tipo_atendimento": "Passagens aéreas",
            "data_ida": "primeira quinzena de dezembro",
            "qtd_adultos": "2",
        }
    )
    missing = gate_missing_fields(data, _INDIC_ASKED)
    assert "a data de ida" in missing
    assert "a data de volta (ou se é só ida)" in missing


_MENU_TIPO = (
    "Perfeito! ✈️ O que você está procurando para a sua viagem?\n\n"
    "1. Passagens aéreas\n2. Passagem + hospedagem\n3. Pacote completo\n"
    "4. Seguro viagem\n5. Aluguel de carro\n6. Passeios / Ingressos\n"
    "7. Cruzeiro\n\nVocê pode escolher uma ou mais opções."
)


def test_gate_cruzeiro_detecta_escolha_sete_no_menu() -> None:
    """Caso real (05/07): o cliente escolheu '7'/'sete' no MENU e nunca digitou
    'cruzeiro'; a extração caiu (gate fail-closed sobre {}) → a única pista é a
    escolha de menu na history. Sem ela o gate caía no modo voo e cobrava
    ida/volta exatas — a mensagem das 15:30 do teste ao vivo."""
    history = _INDIC_ASKED + [
        {"role": "assistant", "content": _MENU_TIPO},
        {"role": "user", "content": "sete"},
        {"role": "user", "content": "quero nordeste, sair e voltar de santos"},
    ]
    missing = gate_missing_fields({}, history)
    assert "a data de ida" not in missing
    assert "a data de volta (ou se é só ida)" not in missing
    assert "o período que você quer viajar" in missing


def test_gate_menu_multiplas_opcoes_com_7_vale_cruzeiro() -> None:
    """'quero a 1 e a 7' após o menu inclui cruzeiro → gate leniente de data."""
    history = _INDIC_ASKED + [
        {"role": "assistant", "content": _MENU_TIPO},
        {"role": "user", "content": "quero a 1 e a 7"},
    ]
    missing = gate_missing_fields({}, history)
    assert "a data de volta (ou se é só ida)" not in missing


def test_gate_menu_sete_pessoas_nao_vira_cruzeiro() -> None:
    """'somos sete pessoas' logo após o menu NÃO é escolha da opção 7 (tem
    palavra fora do padrão de escolha) → segue o gate de voo, sem afrouxar."""
    history = _INDIC_ASKED + [
        {"role": "assistant", "content": _MENU_TIPO},
        {"role": "user", "content": "somos sete pessoas"},
    ]
    missing = gate_missing_fields({}, history)
    assert "a data de ida" in missing


# ---------------------------------------------------------------------------
# Recap pro cliente — "Anotei até aqui: ..." (05/07)
# ---------------------------------------------------------------------------
def test_build_recap_compacto_sem_rotulo_pendente() -> None:
    """Recap mostra o que o cliente disse — inclusive período vago SEM o rótulo
    interno 'pendente (...)', que é jargão do sistema, não fala de gente."""
    data = normalize_lead_data(
        {
            "tipo_atendimento": "Cruzeiro",
            "destino": "Nordeste",
            "origem": "Santos",
            "data_ida": "primeira quinzena de agosto",  # vira pendente(...)
            "qtd_adultos": "6",
            "qtd_criancas": "2",
            "idades_criancas": "5 e 12",
            "forma_pagamento": "Pix",
        }
    )
    recap = build_recap(data)
    assert recap is not None
    assert "primeira quinzena de agosto" in recap
    assert "pendente" not in recap
    assert "saindo de Santos" in recap
    assert "6 adultos + 2 crianças (5, 12 anos)" in recap
    assert "Pix" in recap


def test_build_recap_none_com_pouca_coisa() -> None:
    """Menos de 2 itens → recap não acrescenta nada, melhor ficar sem."""
    assert build_recap({}) is None
    assert build_recap({"destino": "Paris"}) is None


def test_ask_missing_fields_com_recap_prefixa_o_anotado() -> None:
    """Com a ficha em mãos, a re-pergunta do gate deixa de ser 'seca': primeiro
    mostra o que JÁ foi anotado (mata o 'já falei!'), depois pede o que falta."""
    data = normalize_lead_data(
        {"tipo_atendimento": "Cruzeiro", "origem": "Santos", "qtd_adultos": "6"}
    )
    msg = ask_missing_fields(["o período que você quer viajar"], data)
    assert msg.startswith("Anotei até aqui: ")
    assert "saindo de Santos" in msg
    assert "só me confirma o período que você quer viajar? 💛" in msg


def test_ask_missing_fields_sem_data_segue_igual() -> None:
    """Compatibilidade: sem ficha, a frase é a mesma de antes (sem prefixo)."""
    msg = ask_missing_fields(["a data de ida"])
    assert msg.startswith("Antes de eu organizar")


# ---------------------------------------------------------------------------
# merge_ficha — campo capturado 1× nunca se perde (oscilação da extração)
# ---------------------------------------------------------------------------
def test_merge_ficha_preserva_campo_que_a_extracao_perdeu() -> None:
    """Caso da sonda (05/07): 'primeira quinzena de dezembro' saiu de data_ida
    num turno e foi parar em Observações no seguinte → sem acumulação o gate
    voltava a pedir o período que a cliente já tinha dado."""
    stored = normalize_lead_data(
        {"tipo_atendimento": "Cruzeiro", "data_ida": "primeira quinzena de dezembro"}
    )
    fresh = normalize_lead_data(
        {"tipo_atendimento": "Cruzeiro", "qtd_adultos": "2", "data_ida": None}
    )
    merged = merge_ficha(stored, fresh)
    assert merged["data_ida"].startswith("pendente (")  # não se perdeu
    assert merged["qtd_adultos"] == "2"  # o novo entrou


def test_merge_ficha_valor_novo_concreto_vence() -> None:
    """Cliente corrigiu a data → o valor novo (concreto) sobrescreve o antigo."""
    stored = normalize_lead_data({"data_ida": "05/12"})
    fresh = normalize_lead_data({"data_ida": "10/12"})
    assert merge_ficha(stored, fresh)["data_ida"] == "10/12"


def test_merge_ficha_pendente_nao_rebaixa_concreto() -> None:
    """Extração oscilou pra vago num turno → o concreto já confirmado fica."""
    stored = normalize_lead_data({"data_ida": "05/12"})
    fresh = normalize_lead_data({"data_ida": "perto do feriado"})  # vira pendente
    assert merge_ficha(stored, fresh)["data_ida"] == "05/12"


def test_merge_ficha_sem_stored_devolve_fresh() -> None:
    fresh = normalize_lead_data({"destino": "Recife"})
    assert merge_ficha(None, fresh) == fresh


# ---------------------------------------------------------------------------
# Aviso pra Lu — deep link pro painel
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_notify_luciana_includes_panel_link(monkeypatch) -> None:
    from app import briefing as b

    captured: dict[str, str] = {}

    async def fake_send(to, text):  # noqa: ANN001, ARG001
        captured["text"] = text
        return True

    monkeypatch.setattr(b, "send_message", fake_send)
    monkeypatch.setattr(b.settings, "panel_base_url", "https://painel.malu.app")

    await b.notify_luciana(
        "## Resumo da Solicitação de Cotação\n**Temperatura do lead:** Quente\n",
        "5511999998888",
    )
    assert "https://painel.malu.app/conversas/5511999998888" in captured["text"]


@pytest.mark.asyncio
async def test_notify_returning_client_includes_panel_link(monkeypatch) -> None:
    from app import briefing as b

    captured: dict[str, str] = {}

    async def fake_send(to, text):  # noqa: ANN001, ARG001
        captured["text"] = text
        return True

    monkeypatch.setattr(b, "send_message", fake_send)
    monkeypatch.setattr(b.settings, "panel_base_url", "https://painel.malu.app")

    await b.notify_luciana_returning_client("5511977776666", "Ana")
    assert "https://painel.malu.app/conversas/5511977776666" in captured["text"]


@pytest.mark.asyncio
async def test_notify_ai_down_includes_panel_link(monkeypatch) -> None:
    from app import briefing as b

    captured: dict[str, str] = {}

    async def fake_send(to, text):  # noqa: ANN001, ARG001
        captured["text"] = text
        return True

    monkeypatch.setattr(b, "send_message", fake_send)
    monkeypatch.setattr(b.settings, "panel_base_url", "https://painel.malu.app")

    await b.notify_luciana_ai_down("5511955554444", "João")
    assert "https://painel.malu.app/conversas/5511955554444" in captured["text"]
    assert "travou" in captured["text"].lower()
