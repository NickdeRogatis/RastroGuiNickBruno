"""Planilha da pesquisa DJEN acima de R$ 600.000,00.

Gera quatro abas em ``saida/DG__mais_de_600_mil/casos_djen_<inicio>_a_<fim>.xlsx``:
- ``Casos``: somente confirmados com valor da causa > R$ 600.000,00, preservando
  as 15 colunas habituais do DJEN e acrescentando valor numérico em reais, fonte
  verificável e data da consulta.
- ``Publicações``: publicações do período ligadas aos casos exibidos.
- ``Pendentes``: CNJ, score e motivo pelo qual o valor ainda precisa de confirmação.
- ``Como ler``: guia das colunas, regras de pontuação, cobertura e contagens.

A gravação usa arquivo temporário na mesma pasta + ``os.replace`` para preservar
a planilha anterior em caso de falha no meio da escrita.
"""

import os
import tempfile
from datetime import date
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.worksheet.worksheet import Worksheet

from guicredito.dg_mais_de_600_mil.modelos import (
    CandidatoDiario,
    CasoConfirmado,
    CasoPendente,
    ResumoRodadaFiltrada,
    StatusValor,
    rotulo_motivo,
)
from guicredito.djen.modelos import Bloco, Publicacao
from guicredito.djen.planilha import (
    _COLUNAS as _COLUNAS_BASE,
    _EXPLICACAO as _EXPLICACAO_BASE,
    _PONTOS,
    _devedor,
    _rotulos,
    _texto,
    _tipo_credor,
    _trecho_principal,
)
from guicredito.djen.texto import formatar_cnj

_VERDE = PatternFill(fill_type="solid", fgColor="FFC6EFCE")
_AMARELO = PatternFill(fill_type="solid", fgColor="FFFFEB9C")
_QUEBRA = Alignment(wrap_text=True)
_NEGRITO = Font(bold=True)
_LIMITE_LINHAS_EXCEL = 1_048_575

_COLUNAS_EXTRAS = (
    "Valor da causa (R$)",
    "Fonte do valor",
    "Data da consulta",
)
_EXPLICACAO_EXTRAS = (
    "Valor da causa confirmado na capa do próprio processo (estritamente acima de R$ 600.000,00).",
    "Origem verificável do valor aceito (portal/fonte e evidência local; clique se houver link).",
    "Data em que a capa foi consultada ou importada.",
)
_COLUNAS_FILTRO = _COLUNAS_BASE + _COLUNAS_EXTRAS
_EXPLICACAO_FILTRO = _EXPLICACAO_BASE + _EXPLICACAO_EXTRAS


def _escrever(ws: Worksheet, valores: list[object]) -> None:
    ws.append([_texto(valor) for valor in valores])


def _cabecalho(ws: Worksheet, colunas: tuple[str, ...] | list[str]) -> None:
    _escrever(ws, list(colunas))
    for cell in ws[1]:
        cell.font = _NEGRITO
    ultima = ws.cell(1, len(colunas)).column_letter
    ws.auto_filter.ref = f"A1:{ultima}{max(ws.max_row, 1)}"
    ws.freeze_panes = "A2"


def _data_consulta(consultado_em: str | None) -> date | str:
    if not consultado_em:
        return ""
    try:
        return date.fromisoformat(consultado_em[:10])
    except ValueError:
        return consultado_em[:10]


def _texto_fonte(verificacao) -> str:
    base = verificacao.fonte or "TJSP e-SAJ — consulta pública de 1º grau"
    if verificacao.evidencia_sha256:
        return f"{base} [sha256:{verificacao.evidencia_sha256[:12]}]"
    return base


def _aba_casos(ws: Worksheet, casos: list[CasoConfirmado]) -> None:
    _cabecalho(ws, _COLUNAS_FILTRO)
    for indice, confirmado in enumerate(casos, start=1):
        item = confirmado.caso_pontuado
        caso = item.caso
        ver = confirmado.verificacao
        valor_num = float(ver.valor_reais) if ver.valor_reais is not None else None
        _escrever(
            ws,
            [
                indice,
                item.pontos.total,
                formatar_cnj(caso.numero_processo),
                caso.ano_divida,
                caso.comarca,
                caso.classe,
                caso.credor or "",
                _tipo_credor(caso),
                _devedor(caso),
                _rotulos(caso, (Bloco.DESGASTE,)),
                _rotulos(caso, (Bloco.ACORDO, Bloco.IMOVEL, Bloco.TRANSITO, Bloco.VEICULO)),
                _rotulos(caso, (Bloco.DESCONTO, Bloco.ALERTA)),
                f"{caso.ultima_data:%d/%m} · {caso.ultimo_tipo}",
                caso.n_publicacoes,
                _trecho_principal(caso),
                valor_num,
                _texto_fonte(ver),
                _data_consulta(ver.consultado_em),
            ],
        )
        linha = indice + 1
        celula_pontos = ws.cell(linha, 2)
        if item.pontos.total >= 75:
            celula_pontos.fill = _VERDE
        elif item.pontos.total >= 50:
            celula_pontos.fill = _AMARELO
        celula_proc = ws.cell(linha, 3)
        if caso.link:
            celula_proc.hyperlink = caso.link
        for coluna in (10, 11, 12, 15, 17):
            ws.cell(linha, coluna).alignment = _QUEBRA
        celula_valor = ws.cell(linha, 16)
        celula_valor.number_format = "#,##0.00"
        celula_fonte = ws.cell(linha, 17)
        if ver.url_fonte:
            celula_fonte.hyperlink = ver.url_fonte
        celula_data = ws.cell(linha, 18)
        if isinstance(celula_data.value, date):
            celula_data.number_format = "dd/mm/yyyy"

    ultima = ws.cell(1, len(_COLUNAS_FILTRO)).column_letter
    ws.auto_filter.ref = f"A1:{ultima}{ws.max_row}"
    larguras = (6, 10, 28, 10, 28, 40, 32, 18, 32, 36, 36, 36, 24, 16, 48, 20, 44, 16)
    for indice, largura in enumerate(larguras, start=1):
        ws.column_dimensions[ws.cell(1, indice).column_letter].width = largura


def _aba_publicacoes(
    ws: Worksheet,
    casos: list[CasoConfirmado],
    publicacoes: dict[str, list[Publicacao]],
) -> None:
    _cabecalho(ws, ["Processo", "Data", "Tipo", "Órgão", "Texto"])
    for confirmado in casos:
        numero = confirmado.caso_pontuado.caso.numero_processo
        pubs = sorted(publicacoes.get(numero, []), key=lambda pub: pub.data)
        for pub in pubs:
            _escrever(
                ws,
                [
                    formatar_cnj(pub.numero_processo),
                    pub.data,
                    pub.tipo,
                    pub.orgao,
                    pub.texto,
                ],
            )
            ws.cell(ws.max_row, 5).alignment = _QUEBRA
    ws.auto_filter.ref = f"A1:E{ws.max_row}"
    for letra, largura in zip("ABCDE", (28, 14, 18, 40, 80), strict=True):
        ws.column_dimensions[letra].width = largura


def _aba_candidatos_diario(ws: Worksheet, candidatos: list[CandidatoDiario]) -> None:
    colunas = [
        "#",
        "Pontos",
        "Processo",
        "Início",
        "Comarca",
        "Classe",
        "Credor",
        "Devedor",
        "Maior menção no diário (R$)",
        "Situação na capa",
        "Valor da causa confirmado (R$)",
        "Detalhe",
    ]
    _cabecalho(ws, colunas)
    for indice, candidato in enumerate(candidatos, start=1):
        item = candidato.caso_pontuado
        caso = item.caso
        ver = candidato.verificacao
        if ver.status is StatusValor.CONFIRMADO_ACIMA:
            situacao = "Confirmado acima de R$ 600.000,00"
        elif ver.status is StatusValor.CONFIRMADO_ATE:
            situacao = "Confirmado até R$ 600.000,00"
        else:
            situacao = rotulo_motivo(ver.motivo)
        valor_conf = float(ver.valor_reais) if ver.valor_reais is not None else None
        _escrever(
            ws,
            [
                indice,
                item.pontos.total,
                formatar_cnj(caso.numero_processo),
                caso.ano_divida,
                caso.comarca,
                caso.classe,
                caso.credor or "",
                _devedor(caso),
                float(candidato.mencao_valor_alto),
                situacao,
                valor_conf,
                ver.detalhe,
            ],
        )
        linha = indice + 1
        celula_pontos = ws.cell(linha, 2)
        if item.pontos.total >= 75:
            celula_pontos.fill = _VERDE
        elif item.pontos.total >= 50:
            celula_pontos.fill = _AMARELO
        if caso.link:
            ws.cell(linha, 3).hyperlink = caso.link
        ws.cell(linha, 9).number_format = "#,##0.00"
        if valor_conf is not None:
            ws.cell(linha, 11).number_format = "#,##0.00"
    ws.auto_filter.ref = f"A1:L{ws.max_row}"
    larguras = (6, 10, 28, 10, 26, 36, 30, 30, 24, 32, 24, 48)
    for indice, largura in enumerate(larguras, start=1):
        ws.column_dimensions[ws.cell(1, indice).column_letter].width = largura


def _aba_pendentes(ws: Worksheet, pendentes: list[CasoPendente]) -> None:
    _cabecalho(ws, ["Processo", "Pontos", "Motivo", "Detalhe"])
    for item in pendentes[:_LIMITE_LINHAS_EXCEL]:
        caso = item.caso_pontuado.caso
        ver = item.verificacao
        detalhe = ver.detalhe
        if item.mencao_valor_alto is not None:
            aviso = (
                f"Menção no diário (> R$ 600 mil: R$ {item.mencao_valor_alto:,.2f} — "
                "apenas prioridade, não confirma)"
            ).replace(",", "X").replace(".", ",").replace("X", ".")
            detalhe = f"{detalhe}; {aviso}" if detalhe else aviso
        ws.append(
            [
                formatar_cnj(caso.numero_processo),
                item.caso_pontuado.pontos.total,
                rotulo_motivo(ver.motivo),
                _texto(detalhe),
            ]
        )
    ws.auto_filter.ref = f"A1:D{ws.max_row}"
    for letra, largura in zip("ABCD", (28, 10, 38, 60), strict=True):
        ws.column_dimensions[letra].width = largura


def _aba_como_ler(ws: Worksheet, resumo: ResumoRodadaFiltrada) -> None:
    _escrever(ws, ["Coluna", "O que significa"])
    for coluna, explicacao in zip(_COLUNAS_FILTRO, _EXPLICACAO_FILTRO, strict=True):
        _escrever(ws, [coluna, explicacao])
    _escrever(ws, [])
    _escrever(ws, ["Como os pontos são calculados"])
    for linha in _PONTOS:
        _escrever(ws, [linha])
    _escrever(ws, [])
    _escrever(ws, ["Critério do modo filtrado"])
    _escrever(
        ws,
        [
            "Somente entram na aba Casos os processos elegíveis com valor da causa "
            "estritamente maior que R$ 600.000,00 (a partir de R$ 600.000,01) "
            "confirmado na capa do próprio processo."
        ],
    )
    _escrever(
        ws,
        [
            "Menções a leilão, avaliação, penhora, acordo ou saldo no texto do diário "
            "não confirmam o critério; servem apenas para priorizar consultas pendentes."
        ],
    )
    _escrever(ws, [])
    _escrever(ws, ["Período", f"{resumo.inicio:%d/%m/%Y} a {resumo.fim:%d/%m/%Y}"])
    _escrever(
        ws,
        ["Cobertura", "Cobertura parcial" if resumo.cobertura_parcial else "Cobertura completa"],
    )
    if resumo.so_mencao_diario:
        _escrever(
            ws,
            [
                "Funil de consulta",
                "Ativado (--so-mencao-diario): consultas avulsas restritas aos candidatos com menção > R$ 600 mil no diário",
            ],
        )
    if resumo.interrompido_por:
        _escrever(ws, ["Interrupção de consultas", resumo.interrompido_por])
    _escrever(ws, ["Cadernos usados"])
    if resumo.cadernos:
        for caderno in resumo.cadernos:
            _escrever(
                ws,
                [
                    (
                        f"{caderno.data:%d/%m/%Y} versão {caderno.versao}, "
                        f"{caderno.total_comunicacoes} publicações"
                    )
                ],
            )
    else:
        _escrever(ws, ["Nenhum caderno usado."])
    if resumo.dias_sem_caderno:
        dias = ", ".join(dia.strftime("%d/%m/%Y") for dia in resumo.dias_sem_caderno)
        _escrever(ws, [f"Dias sem caderno: {dias}"])
    else:
        _escrever(ws, ["Dias sem caderno: nenhum"])
    _escrever(ws, [])
    _escrever(ws, ["Publicações lidas", resumo.publicacoes_lidas])
    _escrever(ws, ["Publicações de cobrança", resumo.publicacoes_cobranca])
    _escrever(ws, ["Processos", resumo.processos])
    _escrever(ws, ["Fora por serem só empresa", resumo.processos_so_empresa])
    _escrever(ws, ["Fora por credor banco", resumo.processos_banco])
    _escrever(ws, ["Fora por acordo homologado no próprio processo", resumo.processos_acordo])
    _escrever(ws, ["Fora por ter menos de 1 ano", resumo.processos_recentes])
    _escrever(ws, ["Dias de histórico lidos", resumo.dias_historico])
    _escrever(ws, ["Elegíveis antes do corte financeiro", resumo.elegiveis])
    _escrever(
        ws,
        ["Candidatos com menção > R$ 600 mil no diário", resumo.candidatos_mencao_diario],
    )
    _escrever(
        ws,
        [
            "Candidatos com menção ainda pendentes de consulta",
            resumo.candidatos_mencao_pendentes,
        ],
    )
    _escrever(
        ws,
        [
            "Confirmados acima de R$ 600.000,00 (antes do limite de exibição)",
            resumo.confirmados_acima_corte,
        ],
    )
    _escrever(ws, ["Confirmados até R$ 600.000,00", resumo.confirmados_ate_corte])
    _escrever(ws, ["Pendentes de confirmação", resumo.pendentes])
    for motivo, quantidade in sorted(resumo.pendencias_por_motivo.items()):
        _escrever(ws, [f"  Pendentes — {rotulo_motivo(motivo)}", quantidade])
    _escrever(ws, ["Exportados na aba Casos", resumo.exportados])
    _escrever(
        ws,
        [
            "Limite de exibição",
            resumo.limite_exibicao
            if resumo.limite_exibicao is not None
            else "Sem limite (todos os confirmados)",
        ],
    )
    _escrever(ws, ["Capas locais reutilizadas", resumo.reutilizados_locais])
    _escrever(ws, ["Consultas avulsas nesta rodada", resumo.consultas_nesta_rodada])
    _escrever(ws, [])
    _escrever(ws, [f"Gerado em {resumo.gerado_em:%d/%m/%Y %H:%M}"])
    ws.column_dimensions["A"].width = 56
    ws.column_dimensions["B"].width = 88
    for cell in ws["B"]:
        cell.alignment = _QUEBRA


def escrever_planilha_filtrada(
    caminho: Path,
    casos: list[CasoConfirmado],
    publicacoes: dict[str, list[Publicacao]],
    pendentes: list[CasoPendente],
    resumo: ResumoRodadaFiltrada,
    *,
    candidatos_diario: list[CandidatoDiario] | None = None,
) -> None:
    """Escreve a planilha filtrada de forma atômica dentro de ``caminho.parent``."""
    caminho.parent.mkdir(parents=True, exist_ok=True)
    wb = Workbook()
    aba_casos = wb.active
    aba_casos.title = "Casos"
    _aba_casos(aba_casos, casos)
    _aba_publicacoes(wb.create_sheet("Publicações"), casos, publicacoes)
    if candidatos_diario is not None:
        _aba_candidatos_diario(wb.create_sheet("Candidatos (diário)"), candidatos_diario)
    _aba_pendentes(wb.create_sheet("Pendentes"), pendentes)
    _aba_como_ler(wb.create_sheet("Como ler"), resumo)

    fd, temporario = tempfile.mkstemp(dir=caminho.parent, suffix=".tmp.xlsx")
    os.close(fd)
    try:
        wb.save(temporario)
        os.replace(temporario, caminho)
    finally:
        Path(temporario).unlink(missing_ok=True)
