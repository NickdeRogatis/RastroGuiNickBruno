# What this file is for: it is the "main" of the project.
# `python -m guicredito.djen` lands here. It downloads the TJSP gazettes for
# the chosen days, keeps the collection cases, marks settlements in other
# cases, drops company-only, bank, already-settled and under-one-year cases,
# scores the rest,
# and writes the Excel sheet. Every other file is one step called from here.
"""Run the whole command, from dates to the printed summary.

``__main__.py`` calls ``main``. ``main`` reads ``--inicio``, ``--fim``,
``--limite``, ``--tribunal`` and ``--historico``. With no dates,
``periodo_padrao`` in ``fonte.py`` picks the last five weekdays through
yesterday.

``rodar`` is the sequence. ``fonte.baixar_caderno`` saves one zip per
weekday, plus ``historico`` weekdays before ``inicio`` that are read only
to find settlements. ``leitura.ler_caderno`` yields every publication.
``partes`` keeps only collection classes. ``casos.resumir`` and
``casos.montar_casos`` fold those publications into one case per process
number, and ``casos.marcar_acordos`` adds points for a settlement in the
debtor's other cases. Company-only debtors, bank creditors, cases with
a settlement in force (``Caso.acordo_vigente``) and cases under one year
old are dropped. ``pontuacao`` scores what remains and
keeps the top ``limite`` (300). The zip is read a second time, only for
those winning case numbers, so the Publicações sheet can hold their full
text. ``planilha.escrever_planilha`` writes ``saida/casos_djen_....xlsx``.
``main`` then prints the funnel counts.
"""

import argparse
import sys
from collections.abc import Iterable
from datetime import date, datetime
from pathlib import Path

from guicredito.djen.casos import marcar_acordos, montar_casos, resumir
from guicredito.djen.fonte import (
    ClienteHttp,
    ClienteUrllib,
    baixar_caderno,
    dias_uteis,
    dias_uteis_antes,
    periodo_padrao,
)
from guicredito.djen.leitura import ler_caderno
from guicredito.djen.modelos import (
    CasoPontuado,
    Publicacao,
    ResumoPublicacao,
    ResumoRodada,
    TipoCredor,
)
from guicredito.djen.partes import classe_de_cobranca
from guicredito.djen.planilha import escrever_planilha
from guicredito.djen.pontuacao import ordenar, pontuar, recente


def rodar(
    inicio: date,
    fim: date,
    *,
    sigla: str = "TJSP",
    limite: int = 300,
    historico: int = 0,
    pasta_dados: Path = Path("dados/cadernos"),
    pasta_saida: Path = Path("saida"),
    cliente: ClienteHttp | None = None,
    agora: datetime | None = None,
) -> tuple[Path, ResumoRodada]:
    http = cliente or ClienteUrllib()
    momento = agora or datetime.now()
    cadernos = []
    dias_sem_caderno: list[date] = []
    for dia in dias_uteis(inicio, fim):
        baixado = baixar_caderno(http, sigla, dia, pasta_dados)
        if baixado is None:
            dias_sem_caderno.append(dia)
            print(f"sem caderno em {dia:%d/%m}")
            continue
        cadernos.append(baixado)
    cadernos_historico = []
    for dia in dias_uteis_antes(inicio, historico):
        baixado = baixar_caderno(http, sigla, dia, pasta_dados)
        if baixado is None:
            print(f"sem caderno em {dia:%d/%m}")
            continue
        cadernos_historico.append(baixado)

    publicacoes_lidas = 0
    publicacoes_cobranca = 0
    resumos = []
    for _info, caminho in cadernos:
        for pub in ler_caderno(caminho):
            publicacoes_lidas += 1
            if classe_de_cobranca(pub.classe):
                publicacoes_cobranca += 1
                resumos.append(resumir(pub))
    resumos_historico = list(_resumos_de_cobranca(cadernos_historico))

    casos = montar_casos(resumos)
    casos = marcar_acordos(casos, casos + montar_casos(resumos_historico))
    so_empresa = [caso for caso in casos if caso.so_empresa]
    restantes = [caso for caso in casos if not caso.so_empresa]
    banco = [caso for caso in restantes if caso.tipo_credor is TipoCredor.BANCO]
    restantes = [caso for caso in restantes if caso.tipo_credor is not TipoCredor.BANCO]
    com_acordo = [caso for caso in restantes if caso.acordo_vigente]
    restantes = [caso for caso in restantes if not caso.acordo_vigente]
    recentes = [caso for caso in restantes if recente(caso, momento.year)]
    restantes = [caso for caso in restantes if not recente(caso, momento.year)]
    pontuados = [CasoPontuado(caso, pontuar(caso)) for caso in restantes]
    escolhidos = ordenar(pontuados, limite)
    numeros = {item.caso.numero_processo for item in escolhidos}
    publicacoes = _publicacoes_dos_casos(cadernos, numeros)

    caminho = pasta_saida / f"casos_djen_{inicio:%Y-%m-%d}_a_{fim:%Y-%m-%d}.xlsx"
    resumo = ResumoRodada(
        inicio=inicio,
        fim=fim,
        cadernos=[info for info, _caminho in cadernos],
        dias_sem_caderno=dias_sem_caderno,
        publicacoes_lidas=publicacoes_lidas,
        publicacoes_cobranca=publicacoes_cobranca,
        processos=len(casos),
        processos_so_empresa=len(so_empresa),
        processos_banco=len(banco),
        processos_recentes=len(recentes),
        processos_acordo=len(com_acordo),
        dias_historico=len(cadernos_historico),
        casos_na_planilha=len(escolhidos),
        gerado_em=momento,
    )
    escrever_planilha(caminho, escolhidos, publicacoes, resumo)
    return caminho, resumo


def _resumos_de_cobranca(cadernos: Iterable[tuple[object, Path]]) -> Iterable[ResumoPublicacao]:
    for _info, caminho in cadernos:
        for pub in ler_caderno(caminho):
            if classe_de_cobranca(pub.classe):
                yield resumir(pub)


def _publicacoes_dos_casos(
    cadernos: Iterable[tuple[object, Path]],
    numeros: set[str],
) -> dict[str, list[Publicacao]]:
    publicacoes: dict[str, list[Publicacao]] = {numero: [] for numero in numeros}
    for _info, caminho in cadernos:
        for pub in ler_caderno(caminho):
            if pub.numero_processo in numeros:
                publicacoes[pub.numero_processo].append(pub)
    return publicacoes


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="guicredito.djen")
    parser.add_argument("--inicio", help="AAAA-MM-DD")
    parser.add_argument("--fim", help="AAAA-MM-DD")
    parser.add_argument("--limite", type=int, default=300)
    parser.add_argument("--tribunal", default="TJSP")
    parser.add_argument(
        "--historico",
        type=int,
        default=0,
        help="dias úteis antes de --inicio lidos só para achar acordos",
    )
    parser.add_argument(
        "--mais-de-600-mil",
        action="store_true",
        help="pesquisa avulsa de processos com valor da causa acima de R$ 600.000,00 (use com --help para opções)",
    )
    args = parser.parse_args(argv)
    if (args.inicio is None) != (args.fim is None):
        parser.error("informe --inicio e --fim juntos, ou nenhum dos dois")
    if args.historico < 0:
        parser.error("--historico não pode ser negativo")
    if args.inicio is None:
        args.inicio, args.fim = periodo_padrao(date.today())
    else:
        args.inicio = date.fromisoformat(args.inicio)
        args.fim = date.fromisoformat(args.fim)
    return args


def main(argv: list[str] | None = None) -> int:
    raw_argv = sys.argv[1:] if argv is None else list(argv)
    if "--mais-de-600-mil" in raw_argv:
        from guicredito.dg_mais_de_600_mil.cli import main as main_filtro

        return main_filtro(raw_argv)
    args = parse_args(raw_argv)
    caminho, resumo = rodar(
        args.inicio,
        args.fim,
        sigla=args.tribunal,
        limite=args.limite,
        historico=args.historico,
        cliente=ClienteUrllib(),
    )
    print(f"Dias com caderno: {len(resumo.cadernos)} (sem caderno: {len(resumo.dias_sem_caderno)})")
    if args.historico:
        print(f"Dias de histórico: {resumo.dias_historico}")
    print(f"Publicações lidas: {resumo.publicacoes_lidas}")
    print(f"Publicações de cobrança: {resumo.publicacoes_cobranca}")
    print(
        f"Processos: {resumo.processos} "
        f"(só empresa, fora da planilha: {resumo.processos_so_empresa})"
    )
    print(f"Fora por credor banco: {resumo.processos_banco}")
    print(f"Fora por acordo homologado no próprio processo: {resumo.processos_acordo}")
    print(f"Fora por ter menos de 1 ano: {resumo.processos_recentes}")
    print(f"Casos na planilha: {resumo.casos_na_planilha}")
    print(f"Planilha: {caminho}")
    return 0
