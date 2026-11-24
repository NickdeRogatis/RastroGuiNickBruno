"""Interface de linha de comando para ``python -m guicredito.djen --mais-de-600-mil``."""

import argparse
import sys
from datetime import date
from pathlib import Path

from guicredito.dg_mais_de_600_mil.estado import pasta_rodada
from guicredito.dg_mais_de_600_mil.modelos import rotulo_motivo
from guicredito.dg_mais_de_600_mil.pipeline import rodar_mais_de_600_mil
from guicredito.djen.fonte import periodo_padrao


def parse_args_filtro(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="guicredito.djen --mais-de-600-mil",
        description=(
            "Pesquisa avulsa de processos elegíveis do DJEN cujo valor da causa "
            "seja estritamente maior que R$ 600.000,00 (a partir de R$ 600.000,01). "
            "Toda saída é gravada sob saida/DG__mais_de_600_mil/."
        ),
    )
    parser.add_argument(
        "--mais-de-600-mil",
        action="store_true",
        help="ativa o modo filtrado por valor da causa acima de R$ 600.000,00",
    )
    parser.add_argument("--inicio", help="data inicial AAAA-MM-DD")
    parser.add_argument("--fim", help="data final AAAA-MM-DD")
    parser.add_argument(
        "--limite",
        type=int,
        default=None,
        help="limite opcional de linhas exibidas em Casos após confirmação (padrão: todos os confirmados)",
    )
    parser.add_argument("--tribunal", default="TJSP", help="sigla do tribunal (padrão: TJSP)")
    parser.add_argument(
        "--historico",
        type=int,
        default=0,
        help="dias úteis antes de --inicio lidos só para achar acordos",
    )
    parser.add_argument(
        "--somente-capas-locais",
        action="store_true",
        help="usa apenas cadernos e capas já salvos localmente, sem novas consultas ao e-SAJ",
    )
    parser.add_argument(
        "--so-mencao-diario",
        action="store_true",
        help=(
            "consulta no e-SAJ apenas candidatos que citam valor > R$ 600 mil no texto "
            "do diário e inclui a aba Candidatos (diário) na planilha"
        ),
    )
    parser.add_argument(
        "--sem-cache",
        action="store_true",
        help="força releitura completa dos cadernos zip ignorando cache da rodada",
    )
    parser.add_argument(
        "--max-consultas",
        type=int,
        default=10,
        help="limite de novas consultas avulsas ao e-SAJ por execução (padrão: 10)",
    )
    parser.add_argument(
        "--intervalo",
        type=float,
        default=5.0,
        help="intervalo em segundos entre consultas avulsas ao e-SAJ (mínimo: 3.0)",
    )
    parser.add_argument(
        "--pasta-filtro",
        type=Path,
        default=Path("saida/DG__mais_de_600_mil"),
        help="pasta raiz isolada de saída do modo filtrado (padrão: saida/DG__mais_de_600_mil)",
    )
    parser.add_argument(
        "--pasta-dados",
        type=Path,
        default=Path("dados/cadernos"),
        help="pasta somente leitura de cadernos já baixados (padrão: dados/cadernos)",
    )
    parser.add_argument(
        "--pasta-aprofundamento",
        type=Path,
        default=Path("saida/aprofundamento"),
        help="pasta somente leitura de capas já coletadas (padrão: saida/aprofundamento)",
    )
    args = parser.parse_args(argv)
    if (args.inicio is None) != (args.fim is None):
        parser.error("informe --inicio e --fim juntos, ou nenhum dos dois")
    if args.historico < 0:
        parser.error("--historico não pode ser negativo")
    if args.limite is not None and args.limite < 0:
        parser.error("--limite não pode ser negativo")
    if args.max_consultas < 0:
        parser.error("--max-consultas não pode ser negativo")
    if args.intervalo < 3.0:
        parser.error("--intervalo deve ser de pelo menos 3 segundos")
    if args.inicio is None:
        args.inicio, args.fim = periodo_padrao(date.today())
    else:
        args.inicio = date.fromisoformat(args.inicio)
        args.fim = date.fromisoformat(args.fim)
    return args


def main(argv: list[str] | None = None) -> int:
    args = parse_args_filtro(sys.argv[1:] if argv is None else argv)
    caminho, resumo = rodar_mais_de_600_mil(
        args.inicio,
        args.fim,
        sigla=args.tribunal,
        limite=args.limite,
        historico=args.historico,
        pasta_dados=args.pasta_dados,
        pasta_aprofundamento=args.pasta_aprofundamento,
        pasta_filtro=args.pasta_filtro,
        somente_capas_locais=args.somente_capas_locais,
        so_mencao_diario=args.so_mencao_diario,
        usar_cache_rodada=not args.sem_cache,
        max_consultas=args.max_consultas,
        intervalo=args.intervalo,
    )
    pasta_estado = pasta_rodada(args.pasta_filtro, args.tribunal, args.inicio, args.fim)
    sufixo = " [funil por menção no diário]" if resumo.so_mencao_diario else ""
    print(
        f"Modo: DJEN acima de R$ 600.000,00{sufixo} "
        f"({resumo.inicio:%d/%m/%Y} a {resumo.fim:%d/%m/%Y})"
    )
    print(
        f"Dias com caderno: {len(resumo.cadernos)} "
        f"(sem caderno: {len(resumo.dias_sem_caderno)})"
        + (" [cache da rodada reutilizado]" if resumo.cache_cadernos_reutilizado else "")
    )
    if args.historico:
        print(f"Dias de histórico: {resumo.dias_historico}")
    print(f"Elegíveis (antes do corte de 300): {resumo.elegiveis}")
    print(
        f"Candidatos com menção > R$ 600 mil no diário: {resumo.candidatos_mencao_diario} "
        f"(ainda pendentes de consulta: {resumo.candidatos_mencao_pendentes})"
    )
    print(
        f"Confirmados acima de R$ 600.000,00 (antes do limite): "
        f"{resumo.confirmados_acima_corte}"
    )
    print(f"Confirmados até R$ 600.000,00: {resumo.confirmados_ate_corte}")
    print(f"Pendentes: {resumo.pendentes}")
    for motivo, quantidade in sorted(resumo.pendencias_por_motivo.items()):
        print(f"  - {rotulo_motivo(motivo)}: {quantidade}")
    print(f"Exportados na aba Casos: {resumo.exportados}")
    print(
        f"Capas locais reutilizadas: {resumo.reutilizados_locais} "
        f"| Consultas avulsas nesta rodada: {resumo.consultas_nesta_rodada}"
    )
    if resumo.cobertura_parcial:
        print("Cobertura: cobertura parcial (há processos pendentes de confirmação)")
    else:
        print("Cobertura: cobertura completa")
    if resumo.interrompido_por:
        print(
            f"Consultas interrompidas por: {resumo.interrompido_por} "
            "(repita o mesmo comando para retomar sem repetir capas já verificadas)"
        )
    print(f"Planilha: {caminho}")
    print(f"Estado e pendências: {pasta_estado}")
    return 0
