from datetime import date

import pytest

from guicredito.djen.casos import anos_citados, comarca, marcar_acordos, montar_casos, resumir
from guicredito.djen.modelos import (
    Bloco,
    Destinatario,
    Parte,
    Publicacao,
    ResumoPublicacao,
    Sinal,
    TipoCredor,
)

NUMERO_2022 = "10034641820228260269"
NUMERO_2015 = "10308309820158260100"


def resumo(**alteracoes) -> ResumoPublicacao:
    dados = dict(
        numero_processo=NUMERO_2022,
        data=date(2026, 11, 6),
        tipo="Intimação",
        orgao="UPJ da 1ª a 4ª Varas Civeis da Comarca de Itapetininga",
        classe="EXECUÇÃO DE TÍTULO EXTRAJUDICIAL",
        link="https://exemplo/1",
        credores=(),
        devedores=(),
        sinais=(),
        anos_citados=(),
    )
    dados.update(alteracoes)
    return ResumoPublicacao(**dados)


@pytest.mark.parametrize(
    "orgao,esperado",
    [
        ("UPJ da 1ª a 4ª Varas Civeis da Comarca de Itapetininga", "Itapetininga"),
        ("1ª Vara Cível da Comarca de São Bernardo do Campo", "São Bernardo do Campo"),
        ("UPJ da 11ª a 15ª Varas Cíveis - Foro Central Cível", "São Paulo"),
        ("UPJ da 9ª a 14ª Varas Cíveis - Regional II - Santo Amaro", "São Paulo"),
        ("Central de Mandados - Taubaté", "Central de Mandados - Taubaté"),
    ],
)
def test_comarca(orgao, esperado):
    assert comarca(orgao) == esperado


def test_anos_citados():
    assert anos_citados(
        "Conforme fls. 304 dos autos de n. 1030830-98.2015.8.26.0100, o trânsito"
    ) == (2015,)
    assert anos_citados("processo principal nº 0001234-56.2012.8.26.0100") == (2012,)
    assert anos_citados("(TJSP, Apelação Cível 1000001-11.2019.8.26.0001, Rel. Fulano)") == ()
    assert anos_citados("autos n. 0000001-11.2010.5.02.0001") == ()


def test_junta_publicacoes_do_mesmo_processo():
    casos = montar_casos(
        [
            resumo(data=date(2026, 11, 6)),
            resumo(data=date(2026, 11, 7), tipo="Citação"),
        ]
    )
    assert len(casos) == 1
    assert casos[0].n_publicacoes == 2
    assert casos[0].ultima_data == date(2026, 11, 7)


def test_devedor_vem_de_qualquer_publicacao():
    casos = montar_casos(
        [
            resumo(),
            resumo(devedores=(Parte("JOÃO EXEMPLO", False),)),
        ]
    )
    assert casos[0].devedor == "JOÃO EXEMPLO"


def test_devedor_nao_identificado():
    caso = montar_casos([resumo()])[0]
    assert caso.devedor is None
    assert caso.so_empresa is False
    assert caso.avalista is False


def test_so_empresa():
    caso = montar_casos([resumo(devedores=(Parte("LOJA EXEMPLO LTDA", True),))])[0]
    assert caso.so_empresa is True


def test_avalista():
    caso = montar_casos(
        [
            resumo(
                devedores=(
                    Parte("LOJA EXEMPLO LTDA", True),
                    Parte("JOÃO EXEMPLO", False),
                )
            )
        ]
    )[0]
    assert caso.devedor == "JOÃO EXEMPLO"
    assert caso.avalista is True


def test_fundo_prevalece_sobre_banco():
    caso = montar_casos(
        [resumo(credores=("BANCO EXEMPLO S.A.", "FIDC EXEMPLO NPL I"))]
    )[0]
    assert caso.tipo_credor is TipoCredor.FUNDO
    assert caso.credor == "FIDC EXEMPLO NPL I"


def test_ano_divida_usa_o_mais_antigo():
    caso = montar_casos([resumo(anos_citados=(2015,))])[0]
    assert caso.ano_divida == 2015


def test_ano_citado_posterior_e_ignorado():
    caso = montar_casos(
        [resumo(numero_processo=NUMERO_2015, anos_citados=(2020,))]
    )[0]
    assert caso.ano_divida == 2015


def test_resumir_junta_destinatarios_e_cabecalho():
    pub = Publicacao(
        id=1,
        data=date(2026, 11, 6),
        tipo="Intimação",
        orgao="1ª Vara Cível da Comarca de São Bernardo do Campo",
        numero_processo=NUMERO_2022,
        classe="EXECUÇÃO DE TÍTULO EXTRAJUDICIAL",
        texto="EXECUTADO : JOÃO EXEMPLO ADVOGADO(A) :",
        link="https://exemplo/1",
        destinatarios=(Destinatario("BANCO EXEMPLO S.A.", "A"),),
    )
    obtido = resumir(pub)
    assert obtido.credores == ("BANCO EXEMPLO S.A.",)
    assert obtido.devedores == (Parte("JOÃO EXEMPLO", False),)


PROC_ACORDO = "10000011820238260001"
PROC_OUTRO = "10000021820228260002"
ACORDO = Sinal("acordo_homologado", Bloco.ACORDO, 0, "acordo homologado neste processo", "Homologo o acordo.")


def caso_de(numero: str, devedor: str | None, *sinais: Sinal):
    nomes = devedor.split("; ") if devedor else []
    (caso,) = montar_casos(
        [
            resumo(
                numero_processo=numero,
                devedores=tuple(Parte(nome, False) for nome in nomes),
                sinais=sinais,
            )
        ]
    )
    return caso


def _acordos(caso) -> list[Sinal]:
    return [s for s in caso.sinais if s.chave == "acordo_outro_processo"]


def test_acordo_em_a_pontua_b_e_nao_a():
    a = caso_de(PROC_ACORDO, "JOSÉ CARLOS DA SILVA", ACORDO)
    b = caso_de(PROC_OUTRO, "JOSÉ CARLOS DA SILVA")
    marcado_a, marcado_b = marcar_acordos([a, b], [a, b])
    assert _acordos(marcado_a) == []
    (sinal,) = _acordos(marcado_b)
    assert (sinal.bloco, sinal.pontos, sinal.rotulo) == (Bloco.ACORDO, 30, "acordo em outro processo")
    assert sinal.trecho == "Acordo homologado no processo 1000001-18.2023.8.26.0001"


def test_nome_com_acento_e_espaco_diferentes_casa():
    a = caso_de(PROC_ACORDO, "JOSÉ CARLOS DA SILVA", ACORDO)
    b = caso_de(PROC_OUTRO, "Jose Carlos da  Silva")
    (marcado_b,) = marcar_acordos([b], [a, b])
    assert len(_acordos(marcado_b)) == 1


def test_nome_de_duas_palavras_nao_casa():
    a = caso_de(PROC_ACORDO, "JOSÉ SILVA", ACORDO)
    b = caso_de(PROC_OUTRO, "JOSÉ SILVA")
    (marcado_b,) = marcar_acordos([b], [a, b])
    assert _acordos(marcado_b) == []


def test_segundo_devedor_conta():
    a = caso_de(PROC_ACORDO, "JOSÉ CARLOS DA SILVA", ACORDO)
    b = caso_de(PROC_OUTRO, "MARIA EXEMPLO FICTÍCIA; JOSÉ CARLOS DA SILVA")
    (marcado_b,) = marcar_acordos([b], [a, b])
    assert len(_acordos(marcado_b)) == 1


def test_mesmo_numero_no_historico_nao_conta():
    a = caso_de(PROC_ACORDO, "JOSÉ CARLOS DA SILVA")
    a_historico = caso_de(PROC_ACORDO, "JOSÉ CARLOS DA SILVA", ACORDO)
    (marcado,) = marcar_acordos([a], [a, a_historico])
    assert _acordos(marcado) == []


def test_devedor_none_nao_quebra():
    a = caso_de(PROC_ACORDO, "JOSÉ CARLOS DA SILVA", ACORDO)
    sem = caso_de(PROC_OUTRO, None)
    assert marcar_acordos([sem], [a, sem]) == [sem]
