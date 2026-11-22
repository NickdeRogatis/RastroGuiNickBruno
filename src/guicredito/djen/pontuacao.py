"""Turn one case into a score, then rank the list.

``pipeline`` calls ``pontuar`` on each case that is left after dropping
company-only debtors, bank creditors and cases under one year old
(``recente``). Points follow the order set at the 13/11 meeting: a
settlement in another case (added by ``casos.marcar_acordos``), then real
estate, then a final judgment, then wear and vehicle, from the ``Sinal``
list built by ``sinais``. Each block stops at its cap. Discounts do not.
A missing debtor subtracts 15 more. The total never goes below 0. Age
adds no points.

``ordenar`` sorts by total (highest first), then by older debt, then by
process number, and cuts the list at ``limite``. ``planilha`` writes that
cut, in that order, as the Casos sheet.
"""

from collections.abc import Iterable

from guicredito.djen.modelos import Bloco, Caso, CasoPontuado, Pontuacao, TipoCredor
from guicredito.djen.partes import eh_cumprimento

PONTOS_CREDOR = {
    TipoCredor.FUNDO: 5,
    TipoCredor.PESSOA: 5,
    TipoCredor.EMPRESA: 5,
}
TETO_BLOCO = {
    Bloco.ACORDO: 30,
    Bloco.IMOVEL: 25,
    Bloco.TRANSITO: 15,
    Bloco.DESGASTE: 15,
    Bloco.VEICULO: 3,
}
PONTOS_CUMPRIMENTO = 10
DESCONTO_SEM_DEVEDOR = 15


def _soma_bloco(caso: Caso, bloco: Bloco) -> int:
    soma = sum(sinal.pontos for sinal in caso.sinais if sinal.bloco is bloco)
    teto = TETO_BLOCO.get(bloco)
    if teto is None:
        return soma
    return min(soma, teto)


def recente(caso: Caso, ano_atual: int) -> bool:
    return caso.ano_divida != 0 and ano_atual - caso.ano_divida < 1


def pontuar(caso: Caso) -> Pontuacao:
    acordo = _soma_bloco(caso, Bloco.ACORDO)
    imovel = _soma_bloco(caso, Bloco.IMOVEL)
    transito = _soma_bloco(caso, Bloco.TRANSITO)
    if transito == 0 and eh_cumprimento(caso.classe):
        transito = PONTOS_CUMPRIMENTO
    desgaste = _soma_bloco(caso, Bloco.DESGASTE)
    veiculo = _soma_bloco(caso, Bloco.VEICULO)
    credor = PONTOS_CREDOR.get(caso.tipo_credor, 0) if caso.tipo_credor is not None else 0
    descontos = _soma_bloco(caso, Bloco.DESCONTO)
    if caso.devedor is None:
        descontos -= DESCONTO_SEM_DEVEDOR
    total = max(0, acordo + imovel + transito + desgaste + veiculo + credor + descontos)
    return Pontuacao(acordo, imovel, transito, desgaste, veiculo, credor, descontos, total)


def ordenar(casos: Iterable[CasoPontuado], limite: int) -> list[CasoPontuado]:
    return sorted(
        casos,
        key=lambda item: (-item.pontos.total, item.caso.ano_divida, item.caso.numero_processo),
    )[:limite]
