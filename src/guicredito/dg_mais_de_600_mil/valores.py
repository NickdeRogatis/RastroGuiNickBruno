"""Leitura exata de valores monetários brasileiros e heurística de priorização.

A confirmação do critério financeiro (> R$ 600.000,00) usa exclusivamente o
campo ``valor da causa`` extraído da capa do próprio processo (ou de fonte
oficial em lote equivalente) e compara centavos inteiros / ``Decimal``.

Menções a valores no texto do diário (leilão, avaliação, penhora, acordo ou
saldo) servem apenas para priorizar consultas avulsas e nunca confirmam o corte.
"""

import re
from decimal import Decimal

from guicredito.dg_mais_de_600_mil.modelos import CORTE_CENTAVOS, CORTE_REAIS, MotivoPendencia

_AUSENTES = {
    "",
    "-",
    "—",
    "–",
    "n/a",
    "na",
    "nao informado",
    "não informado",
    "nao disponivel",
    "não disponível",
    "sem valor",
}

# Formato monetário brasileiro estrito:
# opcional "R$", seguido de inteiro com grupos de 3 dígitos separados por ponto
# OU inteiro sem separador de milhar, com centavos opcionais ",dd".
_VALOR_BR_ESTRITO = re.compile(
    r"^(?:R\$\s*)?(?P<inteiro>(?:\d{1,3}(?:\.\d{3})+|\d+))(?:,(?P<centavos>\d{2}))?$",
    re.IGNORECASE,
)

# Heurística exclusiva para priorização de fila a partir do texto do diário.
_MENCAO_NUMERICA = re.compile(
    r"R\$\s*(?P<num>\d{1,3}(?:\.\d{3})+|\d+)(?:,(?P<dec>\d{1,2}))?"
    r"(?:\s*(?P<escala>milh(?:ão|ao|ões|oes)|mil))?\b",
    re.IGNORECASE,
)


def interpretar_valor_causa(texto: str | None) -> tuple[Decimal | None, int | None, str | None]:
    """Interpreta o campo ``valor da causa`` em reais e centavos exatos.

    Retorna ``(valor_reais, valor_centavos, erro_motivo)``.
    Valores ausentes retornam ``CAPA_SEM_VALOR``; formatos ambíguos, negativos,
    em outra moeda ou ilegíveis retornam ``VALOR_AMBIGUO``.
    """
    if texto is None:
        return None, None, MotivoPendencia.CAPA_SEM_VALOR

    limpo = texto.replace("\u00a0", " ").strip()
    limpo = re.sub(r"\s+", " ", limpo)
    if limpo.casefold() in _AUSENTES:
        return None, None, MotivoPendencia.CAPA_SEM_VALOR

    casamento = _VALOR_BR_ESTRITO.fullmatch(limpo)
    if casamento is None:
        return None, None, MotivoPendencia.VALOR_AMBIGUO

    inteiro = casamento.group("inteiro").replace(".", "")
    centavos_txt = casamento.group("centavos") or "00"
    valor_reais = Decimal(f"{inteiro}.{centavos_txt}")
    valor_centavos = int(inteiro) * 100 + int(centavos_txt)
    return valor_reais, valor_centavos, None


def acima_do_corte(valor_centavos: int) -> bool:
    """Retorna True somente quando o valor é estritamente maior que R$ 600.000,00."""
    return valor_centavos > CORTE_CENTAVOS


def mencao_valor_alto_no_texto(texto: str) -> Decimal | None:
    """Identifica menção monetária > R$ 600.000,00 no texto do diário.

    Uso restrito à priorização de consultas pendentes. Nunca confirma o valor
    da causa do processo.
    """
    if not texto or "r$" not in texto.casefold():
        return None

    maior: Decimal | None = None
    for m in _MENCAO_NUMERICA.finditer(texto):
        inteiro = m.group("num").replace(".", "")
        dec = m.group("dec")
        escala = (m.group("escala") or "").casefold()
        if escala:
            numero = Decimal(f"{inteiro}.{dec}" if dec else inteiro)
            if escala.startswith("milh"):
                valor = numero * Decimal("1000000")
            else:
                valor = numero * Decimal("1000")
        else:
            if dec is not None and len(dec) != 2:
                continue
            valor = Decimal(f"{inteiro}.{dec or '00'}")
        if valor > CORTE_REAIS and (maior is None or valor > maior):
            maior = valor.quantize(Decimal("0.01"))
    return maior
