from datetime import date

import pytest

from guicredito.djen.modelos import (
    Bloco,
    Caso,
    CasoPontuado,
    Pontuacao,
    Sinal,
    TipoCredor,
)
from guicredito.djen.pontuacao import ordenar, pontuar, recente

AC = Bloco.ACORDO
I = Bloco.IMOVEL
T = Bloco.TRANSITO
D = Bloco.DESGASTE
VE = Bloco.VEICULO
X = Bloco.DESCONTO
A = Bloco.ALERTA


def caso(**kw) -> Caso:
    dados = dict(
        numero_processo="10034641820228260269",
        classe="EXECUÇÃO DE TÍTULO EXTRAJUDICIAL",
        orgao="1ª Vara Cível",
        comarca="São Paulo",
        link="https://exemplo/1",
        credor="EMPRESA EXEMPLO LTDA",
        tipo_credor=TipoCredor.EMPRESA,
        devedor="JOÃO EXEMPLO",
        avalista=False,
        so_empresa=False,
        ano_divida=2016,
        sinais=(),
        ultima_data=date(2026, 11, 6),
        ultimo_tipo="Intimação",
        n_publicacoes=1,
    )
    dados.update(kw)
    return Caso(**dados)


def s(chave: str, bloco: Bloco, pts: int) -> Sinal:
    return Sinal(chave, bloco, pts, chave, "trecho")


def test_exemplo_completo():
    c = caso(
        sinais=(
            s("acordo_outro_processo", AC, 30),
            s("imovel_penhorado", I, 15),
            s("bloqueio_negativo", D, 10),
            s("veiculo", VE, 3),
            s("gratuidade_devedor", X, -5),
        )
    )
    assert pontuar(c) == Pontuacao(30, 15, 0, 10, 3, 5, -5, 58)


def test_acordo_homologado_no_proprio_caso_vale_zero():
    assert pontuar(caso(sinais=(s("acordo_homologado", AC, 0),))).acordo_anterior == 0


def test_tetos_por_bloco():
    p = pontuar(
        caso(
            sinais=(
                s("a", I, 20),
                s("b", I, 15),
                s("c", D, 10),
                s("d", D, 10),
                s("e", D, 8),
                s("f", T, 15),
            )
        )
    )
    assert (p.imovel, p.desgaste, p.transito) == (25, 15, 15)


def test_cumprimento_sem_frase_vale_10():
    assert pontuar(caso(classe="CUMPRIMENTO DE SENTENçA")).transito == 10


def test_cumprimento_com_frase_vale_15():
    c = caso(classe="CUMPRIMENTO DE SENTENçA", sinais=(s("transito_em_julgado", T, 15),))
    assert pontuar(c).transito == 15


def test_execucao_sem_frase_vale_0():
    assert pontuar(caso()).transito == 0


@pytest.mark.parametrize(
    "tipo,pts",
    [
        (TipoCredor.FUNDO, 5),
        (TipoCredor.PESSOA, 5),
        (TipoCredor.EMPRESA, 5),
        (None, 0),
    ],
)
def test_credor(tipo, pts):
    assert pontuar(caso(tipo_credor=tipo)).credor == pts


@pytest.mark.parametrize("ano,esperado", [(2026, True), (2025, False), (2010, False), (0, False)])
def test_recente(ano, esperado):
    assert recente(caso(ano_divida=ano), 2026) is esperado


def test_descontos_e_alerta():
    p = pontuar(
        caso(
            devedor=None,
            sinais=(
                s("sem_bens", X, -10),
                s("prescricao_intercorrente", X, -10),
                s("devedor_nao_localizado", A, 0),
            ),
        )
    )
    assert p.descontos == -35


def test_total_nunca_negativo():
    assert (
        pontuar(
            caso(
                tipo_credor=None,
                devedor=None,
                sinais=(s("sem_bens", X, -10),),
            )
        ).total
        == 0
    )


def test_ordenar_por_pontos_depois_ano_e_corta():
    ranked = [
        CasoPontuado(
            caso(numero_processo="10000000020208260001", ano_divida=2020),
            Pontuacao(0, 0, 0, 0, 0, 0, 0, 80),
        ),
        CasoPontuado(
            caso(numero_processo="90000000020158260001", ano_divida=2015),
            Pontuacao(0, 0, 0, 0, 0, 0, 0, 80),
        ),
        CasoPontuado(
            caso(numero_processo="30000000020108260001", ano_divida=2010),
            Pontuacao(0, 0, 0, 0, 0, 0, 0, 50),
        ),
    ]
    ordenados = ordenar(ranked, 2)
    assert [(item.pontos.total, item.caso.ano_divida) for item in ordenados] == [
        (80, 2015),
        (80, 2020),
    ]
