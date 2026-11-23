"""Relatório privado e projeção categórica para o revisor."""

import re
from collections import defaultdict
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from html import escape
from urllib.parse import urlsplit

from guicredito.djen.texto import normalizar
from guicredito.pessoas.planilha import CABECALHOS, CATEGORIAS_SOCIETARIAS, linhas_do_caso, valores_manuais


def _documento(titulo, corpo):
    return (f'<!doctype html><html lang="pt-BR"><head><meta charset="utf-8">'
            f'<meta name="viewport" content="width=device-width,initial-scale=1"><title>{titulo}</title>'
            '<style>body{font:1rem/1.55 system-ui,sans-serif;color:#1e3039;background:#fff;'
            'max-width:78rem;margin:auto;padding:1.5rem}h1,h2,h3{line-height:1.25}'
            'article{border-top:2px solid #436779;padding:1rem 0}dl{display:grid;'
            'grid-template-columns:minmax(8rem,12rem) 1fr;gap:.25rem .75rem}dt{font-weight:600}'
            'dd{margin:0;overflow-wrap:anywhere;white-space:pre-line}li{overflow-wrap:anywhere}'
            '@media(max-width:38rem){dl{display:block}dd{margin-bottom:.5rem}}</style></head>'
            f'<body><main><h1>{titulo}</h1>{corpo}</main></body></html>')


def _link(valor):
    if not isinstance(valor, str) or any(ord(c) < 33 for c in valor):
        return ""
    try:
        partes = urlsplit(valor)
        if partes.scheme not in {"http", "https"} or not partes.hostname or partes.username or partes.password:
            return ""
        partes.port  # Também rejeita uma porta malformada.
    except ValueError:
        return ""
    texto = escape(valor, quote=True)
    return f'<a href="{texto}" rel="noreferrer">{texto}</a>'


def _seguro(valor):
    if isinstance(valor, dict):
        return "<br>".join(f"{escape(str(k))}: {_seguro(v)}" for k, v in valor.items())
    if isinstance(valor, (tuple, list)):
        return "<br>".join(_seguro(v) for v in valor)
    return escape(str(valor), quote=True)


def _ficha(campos):
    itens = []
    for titulo, valor in campos:
        if valor is None or valor == "" or valor == [] or valor == {}:
            continue
        if titulo in {"URL", "Link do cadastro", "URLs"}:
            urls = valor if isinstance(valor, list) else [valor]
            conteudo = "<br>".join(filter(None, map(_link, urls)))
        else:
            conteudo = _seguro(valor)
        if conteudo:
            itens.append(f"<dt>{escape(titulo)}</dt><dd>{conteudo}</dd>")
    return "<dl>" + "".join(itens) + "</dl>"


def renderizar(dados: dict, decisoes: dict | None = None) -> str:
    decisoes = decisoes or {}
    partes = []
    for caso in dados["casos"]:
        partes.append("<article><h2>" + escape(caso["rotulo"]) + "</h2>")
        partes.append(_ficha((("Processo", caso["processo"]), ("Fase", caso.get("fase")),
                              ("Limitações", caso.get("limitacoes")))))
        if caso.get("alvos"):
            partes.append("<h3>Alvos</h3>")
            for alvo in caso["alvos"]:
                partes.append(_ficha((("Nome", alvo.get("nome")), ("Papel", alvo.get("papel")),
                                      ("Tipo", alvo.get("tipo")), ("Lado", alvo.get("lado")))))
        secoes = defaultdict(list)
        candidatos = {c["id"]: c for c in caso.get("candidatos", [])}
        for aba, chave, leitura in linhas_do_caso(dados["lote"], caso):
            valores = leitura + valores_manuais(aba, chave, decisoes)
            campos = list(zip(CABECALHOS[aba], valores, strict=True))
            if aba == "Candidatos":
                candidato = candidatos[chave]
                extras = (("Fonte", "fonte"), ("Indícios", "indicios"), ("Conflitos", "conflitos"),
                          ("Empresa", "empresa"), ("Situação da empresa", "situacao"), ("CNPJ", "cnpj"),
                          ("Processo referenciado", "processo_referenciado"))
                campos.extend((titulo, candidato.get(campo)) for titulo, campo in extras)
            secoes[aba].append(_ficha(campos))
        for nome in CABECALHOS:
            if nome in secoes:
                partes.extend((f"<h3>{nome}</h3>", *secoes[nome]))
        if caso.get("consultas"):
            partes.append("<h3>Consultas</h3>")
            for q in caso["consultas"]:
                partes.append(_ficha((("Fonte", q.get("fonte")), ("Estado", q.get("estado")),
                                      ("Motivo", q.get("motivo")), ("Data", q.get("data")))))
        partes.append("</article>")
    return _documento("Pesquisa de pessoas · relatório privado", "".join(partes))


_FASES = {"execucao": "execução", "cumprimento de sentenca": "cumprimento de sentença",
          "monitoria": "monitória", "conhecimento": "conhecimento", "recurso": "recurso",
          "arquivamento": "arquivamento"}
_ROTULO = re.compile(r"Caso (?:0[1-9]|10)\Z")
_PENDENTE = "vínculo empresarial pendente de confirmação"
_FAIXAS = ("abaixo de 100 mil", "de 100 mil a menos de 1 milhão", "a partir de 1 milhão")
_INFORMES = {"vínculo profissional documentado (emprego)", "referência documentada a outro processo",
             "capital não informado", _PENDENTE, "participação empresarial", "cadastro empresarial"}
_INFORMES.update(f"capital social declarado {f}" for f in _FAIXAS)
_LIMITES = {"cobertura parcial das fontes", "fonte indisponível", "fonte não configurada",
            "conferência manual pendente", "nenhum indício confirmado"}
_FASE_DESCONHECIDA = "fase não informada"


@dataclass(frozen=True)
class FichaRevisao:
    rotulo: str
    fase: str
    indicios: tuple[str, ...]
    limitacoes: tuple[str, ...]


def _capital(valor):
    try:
        texto = str(valor).strip()
        if "," in texto:
            texto = texto.replace(".", "").replace(",", ".")
        capital = Decimal(texto)
    except InvalidOperation:
        return "capital não informado"
    if not capital.is_finite() or capital < 0:
        return "capital não informado"
    faixa = _FAIXAS[0] if capital < 100000 else _FAIXAS[1] if capital < 1000000 else _FAIXAS[2]
    return f"capital social declarado {faixa}"


def _limitacoes(caso):
    limites = set()
    if caso.get("limitacoes"):
        limites.add("cobertura parcial das fontes")
    for consulta in caso.get("consultas", []):
        estado = consulta.get("estado")
        if estado == "nao_configurado":
            limites.add("fonte não configurada")
        elif estado in {"nao_consultado", "interrompido", "incerto"}:
            limites.add("fonte indisponível")
    return limites


def _indicios(caso, decisoes):
    alvos = {a["id"]: a for a in caso.get("alvos", [])}
    evidencias = defaultdict(list)
    for e in caso.get("evidencias", []):
        evidencias[e["candidato_id"]].append(e)
    resultado = set()
    for c in caso.get("candidatos", []):
        alvo = alvos.get(c["alvo_id"], {})
        if alvo.get("papel") != "devedor":
            continue
        cid = c["id"]
        marca = decisoes.get(cid, {}).get("Confirmado", "")
        if marca == "não":
            continue
        for e in evidencias[cid]:
            cat = e.get("categoria")
            if (cat in CATEGORIAS_SOCIETARIAS or cat == "cadastro empresarial") and c.get("empresa"):
                registro = (str(c.get("fonte", "")).upper() == "CNPJ" and
                            str(e.get("fonte", "")).upper() == "CNPJ" and
                            (e.get("tipo") == "registro" or e.get("estado") in {"registro", "consultado", "verificado"}))
                if registro and marca == "sim":
                    resultado.add("cadastro empresarial" if cat == "cadastro empresarial" else "participação empresarial")
                    resultado.add(_capital(c.get("capital_social")))
                elif registro and cat in CATEGORIAS_SOCIETARIAS:
                    resultado.add(_PENDENTE)
            elif (marca == "sim" and e.get("tipo") not in {"link", "snippet"} and
                  (e.get("estado") in {"verificado", "consultado"} or e.get("tipo") == "registro")):
                if cat in {"emprego", "vínculo profissional", "empregador"}:
                    resultado.add("vínculo profissional documentado (emprego)")
                elif cat in {"outro processo", "processo"}:
                    resultado.add("referência documentada a outro processo")
    return resultado


def projetar_revisao(dados: dict, decisoes: dict | None = None) -> list[FichaRevisao]:
    decisoes = decisoes or {}
    fichas = []
    rotulos = set()
    for caso in dados["casos"]:
        rotulo = caso["rotulo"]
        if not isinstance(rotulo, str) or not _ROTULO.fullmatch(rotulo) or rotulo in rotulos:
            raise ValueError("Rótulo de revisão inválido ou repetido.")
        rotulos.add(rotulo)
        fase = _FASES.get(normalizar(caso.get("fase") or ""), _FASE_DESCONHECIDA)
        indicios = _indicios(caso, decisoes.get("candidatos", {}))
        limites = _limitacoes(caso)
        for o in caso.get("oab", []):
            if o.get("estado") in {"captcha", "pendente", "pendente_manual", "nao_verificado"}:
                manual = decisoes.get("oab", {}).get(o["id"], {})
                conferido = manual.get("OAB/UF conferida") or manual.get("Dados profissionais conferidos")
                if not (manual.get("Data da conferência") and conferido):
                    limites.add("conferência manual pendente")
        if not indicios - {_PENDENTE}:
            limites.add("nenhum indício confirmado")
        fichas.append(FichaRevisao(rotulo, fase, tuple(sorted(indicios)), tuple(sorted(limites))))
    return sorted(fichas, key=lambda f: f.rotulo)


def renderizar_revisao(fichas: list[FichaRevisao]) -> str:
    partes = []
    for ficha in fichas:
        if (not isinstance(ficha, FichaRevisao) or not _ROTULO.fullmatch(ficha.rotulo)
                or ficha.fase not in (*_FASES.values(), _FASE_DESCONHECIDA)
                or set(ficha.indicios) - _INFORMES or set(ficha.limitacoes) - _LIMITES):
            raise ValueError("A ficha contém campos fora da projeção de revisão.")
        partes.append(f"<article><h2>{ficha.rotulo}</h2><p>Fase · {ficha.fase}</p>")
        for nome, itens in (("Indícios", ficha.indicios), ("Limitações", ficha.limitacoes)):
            if itens:
                partes.append(f"<h3>{nome}</h3><ul>")
                partes.extend(f"<li>{item}</li>" for item in itens)
                partes.append("</ul>")
        partes.append("</article>")
    return _documento("Resumo para revisão", "".join(partes))
