"""Write the three-tab workbook that ``pipeline`` returns a path to.

``escrever_planilha`` creates ``saida/casos_djen_{inicio}_a_{fim}.xlsx``.
Casos is one row per ``CasoPontuado`` from ``pontuacao``, in that order.
The Processo cell uses ``texto.formatar_cnj`` and links to the newest act.
Signal columns print the labels from ``sinais``: wear, then assets
(settlement in another case, real estate, final judgment, vehicle), then
discounts and alerts. Green is 75 points or more. Yellow is 50 to 74.

Publicações is the full text of those same cases, from the second zip
read in ``pipeline``. ``texto.limpar_para_excel`` strips characters Excel
refuses, and a cell that would pass 32,767 characters is cut.

Como ler explains each Casos column, repeats the points from
``pontuacao``, and lists the funnel counts stored on ``ResumoRodada``.
"""

from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.worksheet.worksheet import Worksheet

from guicredito.djen.modelos import (
    Bloco,
    Caso,
    CasoPontuado,
    Publicacao,
    ResumoRodada,
    TipoCredor,
)
from guicredito.djen.texto import formatar_cnj, limpar_para_excel

_LIMITE_EXCEL = 32767
_SUFIXO_CORTE = "[texto cortado]"
_VERDE = PatternFill(fill_type="solid", fgColor="FFC6EFCE")
_AMARELO = PatternFill(fill_type="solid", fgColor="FFFFEB9C")
_QUEBRA = Alignment(wrap_text=True)
_NEGRITO = Font(bold=True)

_COLUNAS = (
    "#",
    "Pontos",
    "Processo",
    "Início",
    "Comarca",
    "Classe",
    "Credor",
    "Tipo de credor",
    "Devedor",
    "Sinais de desgaste",
    "Sinais de patrimônio",
    "Alertas",
    "Última publicação",
    "Publicações no período",
    "Trecho principal",
)
_EXPLICACAO = (
    "Posição na lista, da maior pontuação para a menor.",
    "Soma de 0 a 100. Verde a partir de 75; amarelo de 50 a 74.",
    "Número CNJ com máscara. O link abre a publicação mais recente.",
    "Ano da dívida: o mais antigo entre o processo e os autos de origem citados.",
    "Comarca tirada do órgão. Foro Central e Regionais contam como São Paulo.",
    "Classe processual da publicação mais recente.",
    "Credor de maior precedência: fundo, depois banco, empresa e pessoa.",
    "Fundo ⚑, Pessoa ou Empresa. Vazio se não houver credor. Bancos ficam fora.",
    'Pessoa física. "não identificado" se não houver. "[avalista/sócio]" quando o polo passivo também tem empresa.',
    "Rótulos dos sinais de desgaste.",
    "Acordo em outro processo, imóvel, trânsito em julgado e veículo.",
    "Descontos e alertas (⚠).",
    "Data e tipo da publicação mais recente no período.",
    "Quantas publicações desse processo entraram no período.",
    "Frase do sinal positivo de maior pontuação, entre aspas.",
)
_PONTOS = (
    "Acordo homologado no próprio processo: o caso fica fora da planilha, salvo se uma publicação posterior noticiar o descumprimento.",
    "Acordo em outro processo (máx. 30): o mesmo devedor tem acordo homologado, e não descumprido, em outro processo lido na rodada 30. Só nomes com 3 palavras ou mais.",
    "Imóvel (máx. 25): leilão negativo 20; imóvel penhorado, matrícula ou avaliação 15; bem de família 8; penhora 6. Penhora levantada por decisão apaga a penhora daquela publicação e das anteriores.",
    "Trânsito em julgado (máx. 15): texto cita trânsito em julgado 15; cumprimento de sentença sem essa frase 10.",
    "Desgaste (máx. 15): bloqueio ou pesquisa com resultado negativo 10; acordo frustrado 10; arquivamento provisório 8.",
    "Veículo (máx. 3): Renajud ou veículo 3.",
    "Credor (máx. 5): Empresa, Pessoa ou Fundo 5. Credor banco fica fora da planilha.",
    "Idade: processo com menos de 1 ano fica fora. A idade não soma pontos.",
    "Descontos, sem teto: superendividamento −10; ausência de bens ou art. 921 −10; prescrição intercorrente −10; Defensoria −5; justiça gratuita deferida ao devedor −5; devedor não identificado −15.",
    "Alerta, sem pontos: devedor não localizado; idoso(a); salário ou aposentadoria impenhorável.",
    "O total nunca fica abaixo de 0. Dentro de cada bloco, os pontos somam até o máximo do bloco.",
)


def _texto(valor: object) -> object:
    if not isinstance(valor, str):
        return valor
    limpo = limpar_para_excel(valor)
    if len(limpo) <= _LIMITE_EXCEL:
        return limpo
    return limpo[: _LIMITE_EXCEL - len(_SUFIXO_CORTE)] + _SUFIXO_CORTE


def _escrever(ws: Worksheet, valores: list[object]) -> None:
    ws.append([_texto(valor) for valor in valores])


def _cabecalho(ws: Worksheet, colunas: tuple[str, ...] | list[str]) -> None:
    _escrever(ws, list(colunas))
    for cell in ws[1]:
        cell.font = _NEGRITO
    ultima = ws.cell(1, len(colunas)).column_letter
    ws.auto_filter.ref = f"A1:{ultima}{max(ws.max_row, 1)}"
    ws.freeze_panes = "A2"


def _rotulos(caso: Caso, blocos: tuple[Bloco, ...]) -> str:
    return "; ".join(
        sinal.rotulo
        for bloco in blocos
        for sinal in caso.sinais
        if sinal.bloco is bloco
    )


def _trecho_principal(caso: Caso) -> str:
    escolhido = None
    for sinal in caso.sinais:
        if sinal.pontos <= 0:
            continue
        if escolhido is None or sinal.pontos > escolhido.pontos:
            escolhido = sinal
    if escolhido is None:
        return ""
    return f'"{escolhido.trecho}"'


def _tipo_credor(caso: Caso) -> str:
    if caso.tipo_credor is None:
        return ""
    if caso.tipo_credor is TipoCredor.FUNDO:
        return "Fundo ⚑"
    return caso.tipo_credor.value


def _devedor(caso: Caso) -> str:
    if caso.devedor is None:
        return "não identificado"
    if caso.avalista:
        return f"{caso.devedor} [avalista/sócio]"
    return caso.devedor


def _aba_casos(ws: Worksheet, casos: list[CasoPontuado]) -> None:
    _cabecalho(ws, _COLUNAS)
    for indice, item in enumerate(casos, start=1):
        caso = item.caso
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
            ],
        )
        celula_pontos = ws.cell(indice + 1, 2)
        if item.pontos.total >= 75:
            celula_pontos.fill = _VERDE
        elif item.pontos.total >= 50:
            celula_pontos.fill = _AMARELO
        processo = ws.cell(indice + 1, 3)
        processo.hyperlink = caso.link
        for coluna in (10, 11, 12, 15):
            ws.cell(indice + 1, coluna).alignment = _QUEBRA
    ultima = ws.cell(1, len(_COLUNAS)).column_letter
    ws.auto_filter.ref = f"A1:{ultima}{ws.max_row}"
    larguras = (6, 10, 28, 10, 28, 40, 32, 18, 32, 36, 36, 36, 24, 16, 48)
    for indice, largura in enumerate(larguras, start=1):
        ws.column_dimensions[ws.cell(1, indice).column_letter].width = largura


def _aba_publicacoes(
    ws: Worksheet,
    casos: list[CasoPontuado],
    publicacoes: dict[str, list[Publicacao]],
) -> None:
    _cabecalho(ws, ["Processo", "Data", "Tipo", "Órgão", "Texto"])
    for item in casos:
        pubs = sorted(publicacoes.get(item.caso.numero_processo, []), key=lambda pub: pub.data)
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


def _aba_como_ler(ws: Worksheet, resumo: ResumoRodada) -> None:
    _escrever(ws, ["Coluna", "O que significa"])
    for coluna, explicacao in zip(_COLUNAS, _EXPLICACAO, strict=True):
        _escrever(ws, [coluna, explicacao])
    _escrever(ws, [])
    _escrever(ws, ["Como os pontos são calculados"])
    for linha in _PONTOS:
        _escrever(ws, [linha])
    _escrever(ws, [])
    _escrever(ws, [f"Período: {resumo.inicio:%d/%m/%Y} a {resumo.fim:%d/%m/%Y}"])
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
    _escrever(ws, ["Na planilha", resumo.casos_na_planilha])
    _escrever(ws, [])
    _escrever(ws, [f"Gerado em {resumo.gerado_em:%d/%m/%Y %H:%M}"])
    ws.column_dimensions["A"].width = 42
    ws.column_dimensions["B"].width = 88
    for cell in ws["B"]:
        cell.alignment = _QUEBRA


def escrever_planilha(
    caminho: Path,
    casos: list[CasoPontuado],
    publicacoes: dict[str, list[Publicacao]],
    resumo: ResumoRodada,
) -> None:
    caminho.parent.mkdir(parents=True, exist_ok=True)
    wb = Workbook()
    aba_casos = wb.active
    aba_casos.title = "Casos"
    _aba_casos(aba_casos, casos)
    _aba_publicacoes(wb.create_sheet("Publicações"), casos, publicacoes)
    _aba_como_ler(wb.create_sheet("Como ler"), resumo)
    wb.save(caminho)
