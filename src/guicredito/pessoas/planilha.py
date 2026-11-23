"""Planilha privada. Apenas as colunas de decisão são importadas do Excel."""

from collections import defaultdict
from datetime import date, datetime
from pathlib import Path
from tempfile import NamedTemporaryFile
from zipfile import BadZipFile

from openpyxl import Workbook, load_workbook
from openpyxl.cell.cell import Cell
from openpyxl.styles import Font, PatternFill
from openpyxl.worksheet.datavalidation import DataValidation

from guicredito.djen.texto import limpar_para_excel
from guicredito.pessoas.contatos import validar_cpf


CABECALHOS = {
    "Candidatos": ("Lote", "Alvo ID", "Candidato ID", "Processo", "Papel", "Tipo", "Nome",
                   "Confiança", "Cidade", "Empregador", "Faixa etária", "Evidências IDs", "URLs",
                   "Verificação", "Confirmado", "CPF", "Autorizar consulta paga"),
    "Provedor": ("Alvo ID", "Candidato ID de origem", "Provedor ID", "Nome candidato",
                 "Indícios mínimos", "Confirmado"),
    "Evidências": ("ID", "Candidato ID", "Categoria", "Fonte", "URL", "Data", "Trecho", "SHA-256", "Estado"),
    "Contatos": ("Candidato ID", "Origem", "Tipo", "Valor", "Data da fonte", "Data da consulta"),
    "Casos": ("Código de revisão", "Processo", "Descartar"),
    "Vínculos": ("Caso ID", "Candidato ID", "Vínculo ID", "Nome da empresa", "Evidências IDs", "Capital declarado"),
    "OAB": ("Alvo ID", "Nome encontrado", "OAB/UF disponível", "Link do cadastro", "Estado",
            "OAB/UF conferida", "Dados profissionais conferidos", "Data da conferência"),
    "Como ler": ("Campo", "Descrição"),
}
# Cada aba editável tem um sufixo de colunas manuais e uma chave no mapa de decisões.
_MANUAIS = {"Candidatos": ("candidatos", 3), "Provedor": ("provedor", 1),
            "Casos": ("casos", 1), "OAB": ("oab", 3)}
_MARCACOES = {"Confirmado": ("sim", "não"), "Autorizar consulta paga": ("sim", "não"), "Descartar": ("sim",)}
CATEGORIAS_SOCIETARIAS = {"participação empresarial", "vínculo empresarial", "quadro societário", "registro empresarial"}


def _texto(valor):
    if valor is None:
        return ""
    if isinstance(valor, dict):
        return "\n".join(f"{chave}: {_texto(v)}" for chave, v in valor.items())
    if isinstance(valor, (tuple, list)):
        return "\n".join(map(_texto, valor))
    return limpar_para_excel(str(valor))[:32767]


def _campos(registro, *chaves):
    return tuple(registro.get(c) for c in chaves)


def linhas_do_caso(lote, caso):
    """Linhas de leitura e suas chaves no manifesto, antes de incorporar decisões."""
    processo = caso["processo"]
    yield "Casos", processo, (caso["rotulo"], processo)
    alvos = {a["id"]: a for a in caso.get("alvos", [])}
    candidatos = {c["id"]: c for c in caso.get("candidatos", [])}
    por_candidato = defaultdict(list)
    for e in caso.get("evidencias", []):
        por_candidato[e["candidato_id"]].append(e)
        yield "Evidências", e["id"], _campos(e, "id", "candidato_id", "categoria", "fonte", "url", "data",
                                               "trecho", "sha256", "estado")
    for c in caso.get("candidatos", []):
        cid = c["id"]
        alvo = alvos[c["alvo_id"]]
        evidencias = por_candidato[cid]
        yield "Candidatos", cid, (lote, alvo["id"], cid, processo, alvo.get("papel"), alvo.get("tipo"),
                                  c.get("nome"), c.get("confianca"), c.get("cidade"),
                                  c.get("empregador"), c.get("faixa_etaria"), [e["id"] for e in evidencias],
                                  [e["url"] for e in evidencias if e.get("url")], c.get("verificacao"))
        if c.get("empresa") and alvo.get("tipo") == "PF":
            vinculo = "vinculo-" + cid
            registros = [e["id"] for e in evidencias if e.get("categoria") in CATEGORIAS_SOCIETARIAS]
            yield "Vínculos", vinculo, (caso["rotulo"], cid, vinculo, c["empresa"], registros, c.get("capital_social"))
    for p in caso.get("provedor", []):
        c = candidatos[p["candidato_id"]]
        yield "Provedor", p["id"], (c["alvo_id"], c["id"], p["id"], p.get("nome"), p.get("indicios"))
    for o in caso.get("oab", []):
        inscricao = "/".join(str(v) for v in _campos(o, "oab", "uf") if v)
        estado = " · ".join(v for v in _campos(o, "estado", "motivo") if v)
        yield "OAB", o["id"], (o["alvo_id"], o.get("nome"), inscricao, o.get("url"), estado)
    for contato in caso.get("contatos", []):
        yield "Contatos", None, _campos(contato, "candidato_id", "origem", "tipo", "valor", "data_fonte", "data_consulta")


def _linhas(dados):
    contagens = defaultdict(int)
    for caso in dados["casos"]:
        for aba, chave, valores in linhas_do_caso(dados["lote"], caso):
            yield aba, chave, valores
            contagens[aba] += 1
        for l in caso.get("limitacoes", []):
            yield "Como ler", None, (caso["rotulo"], l)
        for consulta in caso.get("consultas", []):
            yield "Como ler", None, (caso["rotulo"], " · ".join(str(v) for v in
                                      _campos(consulta, "fonte", "estado", "motivo") if v))
    yield "Como ler", None, ("Lote", dados["lote"])
    yield "Como ler", None, ("Revisão de identidade", "Marque sim ou não em Confirmado. O CPF é opcional e deve ser texto.")
    yield "Como ler", None, ("Consulta paga", "Autorize o gasto em cada candidato confirmado e execute contatos separadamente.")
    yield "Como ler", None, ("Provedor", "Em caso de homônimos, confirme uma única opção para o candidato de origem.")
    yield "Como ler", None, ("Vínculos", "A confirmação vem da aba Candidatos. Capital social declarado pertence à empresa.")
    yield "Como ler", None, ("OAB", "Registre os dados profissionais conferidos e a data da conferência no cadastro indicado.")
    yield "Como ler", None, ("Descartar", "Marque sim para incluir o caso na prévia de descarte.")
    yield "Como ler", None, ("Reexecução", "Salve e feche o Excel antes de executar novamente.")
    for aba in CABECALHOS:
        if aba != "Como ler":
            yield "Como ler", None, ("Linhas em " + aba, str(contagens[aba]))


def campos_manuais(aba):
    if aba not in _MANUAIS:
        return ()
    return CABECALHOS[aba][-_MANUAIS[aba][1]:]


def valores_manuais(aba, chave, decisoes):
    if aba not in _MANUAIS:
        return ()
    secao, _ = _MANUAIS[aba]
    decisao = decisoes.get(secao, {}).get(chave, {})
    return tuple(decisao.get(c, "") for c in campos_manuais(aba))


def _fechado(caminho):
    if any((caminho.parent / n).exists() for n in ("~$" + caminho.name, ".~lock." + caminho.name + "#")):
        raise ValueError("Salve e feche a planilha antes de continuar.")


def _escrever(aba, valores):
    linha = []
    for valor in valores:
        cell = Cell(aba, value=_texto(valor))
        cell.data_type = "s"  # XML de texto literal, inclusive para =, +, -, @ e valores de erro.
        cell.number_format = "@"
        linha.append(cell)
    aba.append(linha)


def gravar_planilha(caminho: Path, dados: dict, decisoes: dict) -> None:
    _fechado(caminho)
    wb = Workbook()
    wb.remove(wb.active)
    for nome, titulos in CABECALHOS.items():
        ws = wb.create_sheet(nome)
        _escrever(ws, titulos)
        ws.freeze_panes = "A2"
        for cell in ws[1]:
            manual = cell.value in campos_manuais(nome)
            cell.font = Font(color="FFFFFF", bold=True)
            cell.fill = PatternFill("solid", fgColor="276641" if manual else "284661")
            ws.column_dimensions[cell.column_letter].width = max(17, min(64, len(cell.value) + 9))
    for aba, chave, valores in _linhas(dados):
        _escrever(wb[aba], (*valores, *valores_manuais(aba, chave, decisoes)))
    for ws in wb:
        ws.auto_filter.ref = ws.dimensions
        for cell in ws[1]:
            if cell.value in _MARCACOES and ws.max_row > 1:
                opcoes = ",".join(_MARCACOES[cell.value])
                validacao = DataValidation(type="list", formula1=f'"{opcoes}"', allow_blank=True, showErrorMessage=True)
                ws.add_data_validation(validacao)
                validacao.add(f"{cell.column_letter}2:{cell.column_letter}{ws.max_row}")
    wb["Como ler"].column_dimensions["B"].width = 95
    caminho.parent.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile(dir=caminho.parent, prefix=".pessoas-", suffix=".xlsx", delete=False) as arquivo:
        temp = Path(arquivo.name)
    try:
        wb.save(temp)
        _fechado(caminho)
        temp.replace(caminho)
    finally:
        wb.close()
        temp.unlink(missing_ok=True)


def _manual(coluna, celula):
    valor = celula.value
    if valor is None:
        return ""
    if coluna == "Data da conferência":
        if isinstance(valor, datetime):
            return valor.date().isoformat()
        if isinstance(valor, date):
            return valor.isoformat()
        if isinstance(valor, str):
            for formato in ("%Y-%m-%d", "%d/%m/%Y"):
                try:
                    return datetime.strptime(valor.strip(), formato).date().isoformat()
                except ValueError:
                    continue
        raise ValueError("Data da conferência inválida.")
    if not isinstance(valor, str) or celula.data_type != "s":
        raise ValueError("Campo manual exige texto.")
    valor = valor.strip()
    if coluna in _MARCACOES:
        valor = valor.lower()
        if valor and valor not in _MARCACOES[coluna]:
            raise ValueError("Marcação inválida.")
    if coluna == "CPF" and valor:
        validar_cpf(valor)
    return valor


def ler_decisoes(caminho: Path, dados: dict) -> dict:
    _fechado(caminho)
    try:
        wb = load_workbook(caminho, read_only=True, data_only=False, keep_links=False)
    except (BadZipFile, KeyError, OSError):
        raise ValueError("Planilha inválida ou indisponível.") from None
    try:
        return _conferir(wb, dados)
    finally:
        wb.close()


def _conferir(wb, dados):
    if set(wb.sheetnames) != set(CABECALHOS):
        raise ValueError("Abas da planilha incompatíveis com o lote.")
    decisoes = {secao: {} for secao, _ in _MANUAIS.values()}
    esperadas = {aba: defaultdict(list) for aba in CABECALHOS}
    for aba, chave, valores in _linhas(dados):
        assinatura = tuple(_texto(v) for v in valores)
        esperadas[aba][assinatura].append(chave)

    confirmados_provedor = set()
    for nome, titulos in CABECALHOS.items():
        linhas = iter(wb[nome].rows)
        if tuple(c.value for c in next(linhas, ())) != titulos:
            raise ValueError("Colunas da planilha incompatíveis com o lote.")
        campos = campos_manuais(nome)
        n_leitura = len(titulos) - len(campos)
        for linha in linhas:
            if all(c.value is None for c in linha):
                continue  # Excel pode manter o estilo de uma linha vazia após ordenar.
            if any(c.data_type == "f" for c in linha):
                raise ValueError("A planilha contém fórmula em uma linha do lote.")
            assinatura = tuple("" if c.value is None else c.value for c in linha[:n_leitura])
            chaves = esperadas[nome].get(assinatura)
            if not chaves or (campos and len(chaves) != 1):
                raise ValueError("Linha desconhecida, repetida ou alterada na planilha.")
            chave = chaves.pop()
            if not campos:
                continue
            destino = decisoes[_MANUAIS[nome][0]]
            if chave in destino:
                raise ValueError("ID repetido na planilha.")
            marcas = {coluna: _manual(coluna, celula) for coluna, celula in zip(campos, linha[n_leitura:], strict=True)}
            if nome == "Provedor" and marcas["Confirmado"] == "sim":
                cid = assinatura[1]
                if cid in confirmados_provedor:
                    raise ValueError("Confirme uma única opção do provedor por candidato.")
                confirmados_provedor.add(cid)
            destino[chave] = marcas
        if any(esperadas[nome].values()):
            raise ValueError("Faltam linhas do lote na planilha.")
    return decisoes
