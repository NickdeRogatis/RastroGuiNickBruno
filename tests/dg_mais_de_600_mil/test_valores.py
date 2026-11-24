from decimal import Decimal

import pytest

from guicredito.dg_mais_de_600_mil.modelos import MotivoPendencia
from guicredito.dg_mais_de_600_mil.valores import (
    acima_do_corte,
    interpretar_valor_causa,
    mencao_valor_alto_no_texto,
)


@pytest.mark.parametrize(
    ("texto", "reais", "centavos", "esperado_acima"),
    [
        ("R$ 599.999,99", Decimal("599999.99"), 59_999_999, False),
        ("R$ 600.000,00", Decimal("600000.00"), 60_000_000, False),
        ("R$ 600.000,01", Decimal("600000.01"), 60_000_001, True),
        ("R$ 29.761.982,87", Decimal("29761982.87"), 2_976_198_287, True),
        ("R$600.000,01", Decimal("600000.01"), 60_000_001, True),
        ("R$\u00a01.250.000,50", Decimal("1250000.50"), 125_000_050, True),
        ("600000,01", Decimal("600000.01"), 60_000_001, True),
        ("R$ 700.000", Decimal("700000.00"), 70_000_000, True),
        ("R$ 5.523,15", Decimal("5523.15"), 552_315, False),
        ("R$ 0,00", Decimal("0.00"), 0, False),
    ],
)
def test_interpretar_valor_causa_validos(texto, reais, centavos, esperado_acima):
    valor, valor_centavos, erro = interpretar_valor_causa(texto)
    assert erro is None
    assert valor == reais
    assert valor_centavos == centavos
    assert acima_do_corte(valor_centavos) is esperado_acima


@pytest.mark.parametrize(
    "texto",
    [None, "", "   ", "-", "—", "Não informado", "N/A"],
)
def test_interpretar_valor_causa_ausentes(texto):
    valor, centavos, erro = interpretar_valor_causa(texto)
    assert valor is None
    assert centavos is None
    assert erro == MotivoPendencia.CAPA_SEM_VALOR


@pytest.mark.parametrize(
    "texto",
    [
        "US$ 1.000.000,00",
        "€ 700.000,00",
        "600,000.01",
        "R$ 600.000.01",
        "R$ 60.00,00",
        "R$ 600.000,1",
        "R$ 600.000,001",
        "R$ -700.000,00",
        "aproximadamente R$ 700.000,00",
        "R$ 700 mil",
        "R$ 100.000,00 a R$ 700.000,00",
        "inestimável",
    ],
)
def test_interpretar_valor_causa_ambiguos(texto):
    valor, centavos, erro = interpretar_valor_causa(texto)
    assert valor is None
    assert centavos is None
    assert erro == MotivoPendencia.VALOR_AMBIGUO


def test_mencao_valor_alto_no_texto():
    assert mencao_valor_alto_no_texto("Leilão do imóvel avaliado em R$ 2 milhões.") == Decimal(
        "2000000.00"
    )
    assert mencao_valor_alto_no_texto("Penhora no valor de R$ 1,5 milhão.") == Decimal(
        "1500000.00"
    )
    assert mencao_valor_alto_no_texto("Débito atualizado em R$ 750 mil.") == Decimal("750000.00")
    assert mencao_valor_alto_no_texto("Avaliação de R$ 600.000,01.") == Decimal("600000.01")
    assert mencao_valor_alto_no_texto("Acordo no valor de R$ 600.000,00.") is None
    assert mencao_valor_alto_no_texto("Intime-se para pagamento de R$ 50.000,00.") is None
