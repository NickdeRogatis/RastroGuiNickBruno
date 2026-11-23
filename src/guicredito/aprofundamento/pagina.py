"""Extrai apenas campos reconhecidos de uma página pública e-SAJ.

Layout não reconhecido nunca equivale a uma consulta bem-sucedida. A
estrutura abaixo ainda precisa ser conferida contra uma página viva do TJSP.
"""
import re
import unicodedata
from dataclasses import dataclass, field
from html.parser import HTMLParser
from urllib.parse import urlencode, urljoin, urlsplit

from .cnj import BASE, normalizar

VERSAO_EXTRATOR = 3


def url_movimentacoes(html):
    """Endpoint usado pelo botão público Exibir movimentações do e-SAJ."""
    m = re.search(r"\$\.saj\.movimentacoes\s*=\s*\{\s*codigoProcesso:\s*['\"]([A-Za-z0-9]+)['\"]", html)
    return BASE + "carregarMovimentacoesAjax.do?" + urlencode({"processo.codigo": m[1]}) if m else None


def extrair_movimentacoes(html):
    raiz = Arvore(html).raiz
    impedimento = diagnostico(html)
    if impedimento in {"captcha", "bloqueado"}:
        return {"movimentacoes_status": impedimento}
    for id_ in ("tabelaPrimeiraPaginaMovimentacoes", "tabelaTodasMovimentacoes", "tabelaUltimasMovimentacoes"):
        tabela = next((n for n in raiz.todos() if n.attrs.get("id") == id_), None)
        if tabela:
            linhas = []
            for tr in tabela.todos():
                if tr.tag == "tr":
                    celulas = [n.texto() for n in tr.filhos if isinstance(n, No) and n.tag == "td"]
                    if any(celulas):
                        linhas.append(celulas)
            return {"movimentacoes_status": "primeira_pagina", "movimentacoes_linhas": linhas, "tabela_movimentacoes": id_, "referencia_eproc": "eproc" in simplificar(raiz.texto())}
    return {"movimentacoes_status": "resposta_nao_reconhecida"}


@dataclass
class No:
    tag: str
    attrs: dict = field(default_factory=dict)
    filhos: list = field(default_factory=list)

    def texto(self):
        if self.tag in {"script", "style", "noscript"}:
            return ""
        return " ".join(" ".join(
            f.texto() if isinstance(f, No) else f for f in self.filhos
        ).split())

    def todos(self):
        yield self
        for f in self.filhos:
            if isinstance(f, No):
                yield from f.todos()


class Arvore(HTMLParser):
    def __init__(self, html):
        super().__init__(convert_charrefs=True)
        self.raiz = No("root")
        self.pilha = [self.raiz]
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        n = No(tag, dict(attrs))
        self.pilha[-1].filhos.append(n)
        if tag not in {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"}:
            self.pilha.append(n)

    def handle_endtag(self, tag):
        for i in range(len(self.pilha) - 1, 0, -1):
            if self.pilha[i].tag == tag:
                del self.pilha[i:]
                break

    def handle_data(self, text):
        self.pilha[-1].filhos.append(text)


def simplificar(text):
    return "".join(c for c in unicodedata.normalize("NFKD", text.casefold()) if not unicodedata.combining(c))


def diagnostico(html):
    raiz = Arvore(html).raiz
    texto = simplificar(raiz.texto())
    if any(x in texto for x in ("access denied", "acesso negado", "verifique que voce e humano", "verify you are human", "too many requests")):
        return "bloqueado"
    # Não basta haver um script de captcha no rodapé: precisa haver um desafio visível.
    if any(x in texto for x in ("captcha", "nao sou um robo", "digite os caracteres da imagem", "just a moment")):
        return "captcha"
    if "eproc" in texto and any(x in texto for x in ("migrado", "migracao", "tramita no", "remetido ao")):
        return "consultar_eproc"
    if any(x in texto for x in ("nenhum processo encontrado", "nao existem informacoes disponiveis", "nao foram encontrados processos")):
        return "nao_localizado"
    return None


def link_detalhe(html, numero):
    """Só segue resultado com o CNJ exato e destino no e-SAJ."""
    numero = normalizar(numero)
    achados = set()
    for n in Arvore(html).raiz.todos():
        if n.tag != "a":
            continue
        if re.sub(r"\D", "", n.texto()) != numero:
            continue
        url = urljoin(BASE, n.attrs.get("href", ""))
        p = urlsplit(url)
        if p.scheme == "https" and p.netloc == "esaj.tjsp.jus.br" and p.path == "/cpopg/show.do":
            achados.add(url)
    return next(iter(achados)) if len(achados) == 1 else None


def extrair(html, numero):
    numero = normalizar(numero)
    impedimento = diagnostico(html)
    if impedimento:
        return {"status": impedimento}
    raiz = Arvore(html).raiz
    ids = {n.attrs["id"]: n for n in raiz.todos() if n.attrs.get("id")}
    identidade = ids.get("numeroProcesso")
    cabecalho = ids.get("containerDadosPrincipaisProcesso")
    incidente = False
    if identidade is None and cabecalho is not None:
        # Incidentes usam um título próprio; nunca usar o link do processo principal como identidade.
        titulos = [n for n in cabecalho.todos() if "unj-larger" in n.attrs.get("class", "").split()]
        if len(titulos) == 1:
            identidade = titulos[0]
            incidente = True
    if identidade is None:
        return {"status": "layout_nao_reconhecido"}
    encontrado = re.search(r"\d{7}-\d{2}\.\d{4}\.8\.26\.\d{4}|\d{20}", identidade.texto())
    if encontrado is None or re.sub(r"\D", "", encontrado[0]) != numero:
        return {"status": "processo_divergente"}
    campos = {
        "classe": "classeProcesso", "assunto": "assuntoProcesso",
        "foro": "foroProcesso", "vara": "varaProcesso", "juiz": "juizProcesso",
        "valor_da_causa_texto": "valorAcaoProcesso",
        "distribuicao_texto": "dataHoraDistribuicaoProcesso", "situacao_texto": "situacaoProcesso",
    }
    dados = {nome: ids[id_].texto() or None if id_ in ids else None for nome, id_ in campos.items()}
    if incidente:
        dados["classe"] = identidade.texto()[:encontrado.start()].rstrip(" (") or None
    principal = next((n for n in cabecalho.todos() if "processoPrinc" in n.attrs.get("class", "").split()), None) if cabecalho else None
    dados["processo_principal_texto"] = principal.texto() if principal else None

    def tabela(opcoes):
        for id_ in opcoes:
            if id_ in ids:
                linhas = []
                for tr in ids[id_].todos():
                    if tr.tag == "tr":
                        celulas = [n.texto() for n in tr.filhos if isinstance(n, No) and n.tag == "td"]
                        if any(celulas):
                            linhas.append(celulas)
                return linhas, id_
        return [], None

    partes, origem_partes = tabela(("tableTodasPartes", "tablePartesPrincipais"))
    movimentos, origem_movimentos = tabela(("tabelaTodasMovimentacoes", "tabelaUltimasMovimentacoes"))
    if not any(dados.values()) and not partes and not movimentos:
        return {"status": "layout_nao_reconhecido"}
    sob_demanda = "btnExibirMovimentacoes" in ids and origem_movimentos is None
    return {
        "status": "coletado_parcial" if sob_demanda else "coletado", "campos": dados,
        "versao_extrator": VERSAO_EXTRATOR,
        "movimentacoes_status": "aguardando_carregamento" if sob_demanda else ("presentes_na_pagina" if origem_movimentos else "nao_disponiveis_na_pagina"),
        "partes_linhas": partes, "movimentacoes_linhas": movimentos,
        "tabela_partes": origem_partes, "tabela_movimentacoes": origem_movimentos,
        "campos_ausentes": [k for k, v in dados.items() if v is None],
        "limitacao": "Somente o conteúdo público retornado nesta página; não são os autos completos. Valor da causa não é saldo atualizado da dívida.",
    }
