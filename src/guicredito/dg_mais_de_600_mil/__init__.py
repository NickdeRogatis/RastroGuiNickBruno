"""Pesquisa avulsa DJEN para processos do TJSP com valor da causa > R$ 600.000,00.

Este pacote implementa o modo ``--mais-de-600-mil`` de ``python -m guicredito.djen``
como módulo irmão de ``djen``, ``aprofundamento`` e ``pessoas``. Todas as escritas
da execução filtrada permanecem isoladas sob ``saida/DG__mais_de_600_mil/``.
"""

from guicredito.dg_mais_de_600_mil.modelos import (
    CORTE_CENTAVOS,
    CORTE_REAIS,
    CasoConfirmado,
    CasoPendente,
    MotivoPendencia,
    ResumoRodadaFiltrada,
    StatusValor,
    VerificacaoValor,
)
from guicredito.dg_mais_de_600_mil.pipeline import rodar_mais_de_600_mil

__all__ = [
    "CORTE_CENTAVOS",
    "CORTE_REAIS",
    "CasoConfirmado",
    "CasoPendente",
    "MotivoPendencia",
    "ResumoRodadaFiltrada",
    "StatusValor",
    "VerificacaoValor",
    "rodar_mais_de_600_mil",
]
