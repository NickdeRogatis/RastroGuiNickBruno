"""Lawyer fields in the case sources and the manual Cadastro Nacional dos Advogados check."""
import hashlib
import json
import re
from datetime import datetime
from urllib.parse import urlsplit

from guicredito.djen.texto import normalizar
from .entrada import identificador, papel_da_parte


URL_CADASTRO = "https://cna.oab.org.br/"
_UFS = set("AC AL AP AM BA CE DF ES GO MA MT MS MG PA PB PR PE PI RJ RN RS RO RR SC SP SE TO".split())
_ROTULO = r"(?:advogad[oa](?:\([aA]\))?s?|adv(?:s)?\.?)"
_LADO = r"(?:\s+(?:d[oa]s?)\s+(exequente|executad[oa]|requerente|requerid[oa]|credor[a]?|devedor[a]?|autor[a]?|r[eé]u|ré))?"
_MARCADOR = re.compile(r"\b" + _ROTULO + _LADO + r"\s*:", re.I)
_PAPEL = re.compile(r"^" + _ROTULO + _LADO + r"\s*[:.]?$", re.I)
_PUBLICACAO = re.compile(r"(?:^|[|;]|\s[-–—]\s)\s*(" + _ROTULO + _LADO + r"\s*:)", re.I)
_INSCRICAO = re.compile(
    r"\s*\(?\bOAB\s*[:.-]?\s*(?:[/ -]?\s*(?P<uf1>[A-Z]{2})\s*[-/: ]?\s*)?"
    r"(?P<num>\d[.\d]*[A-Z]?)(?:\s*[/ -]\s*(?P<uf2>[A-Z]{2}))?\s*\)?", re.I)
_NOME = re.compile(r"[^\W\d_]+(?:[-'’][^\W\d_]+)*(?:\s+[^\W\d_]+(?:[-'’][^\W\d_]+)*)+")


def _itens(celula):
    # Do not turn a sentence mentioning an attorney into a professional identity.
    for item in re.split(r"[,;\n]|(?<=\))\s+[eE]\s+", celula):
        item = item.strip(" -–:.")
        inscricao = _INSCRICAO.search(item)
        if inscricao:
            if item[inscricao.end():].strip(" ."):
                continue
            nome = item[:inscricao.start()].strip()
            oab = inscricao["num"].replace(".", "").upper()
            uf = (inscricao["uf1"] or inscricao["uf2"] or "").upper()
            if uf and uf not in _UFS:
                continue
        else:
            nome, oab, uf = item, "", ""
        if (len(nome) > 140 or not _NOME.fullmatch(nome)
                or re.search(r"\b(?:testemunha|despacho|decisão|sentença|citad[oa]|intime|declarou)\b", nome, re.I)):
            continue
        if not all(p[:1].isupper() or normalizar(p) in {"de", "del", "da", "do", "das", "dos", "e"}
                   for p in nome.split()):
            continue
        yield nome, oab, uf


def extrair_advogados(partes, publicacoes, processo="", cidade=""):
    advogados = {}
    lados = {}

    def incluir(texto, lado, fonte):
        for nome, oab, uf in _itens(texto):
            aid = identificador(processo, "advogado", normalizar(nome), oab, uf)
            if aid not in advogados:
                advogados[aid] = dict(id=aid, processo=processo, papel="advogado", tipo="PF",
                                      nome=nome, oab=oab, uf=uf, cidade=cidade,
                                      origem=dict(fonte=fonte, oab=oab, uf=uf))
                lados[aid] = set()
            if lado:
                lados[aid].add(lado)
            confirmado = next(iter(lados[aid])) if len(lados[aid]) == 1 else "desconhecido"
            advogados[aid]["lado"] = advogados[aid]["origem"]["lado"] = confirmado

    def rotulados(texto, lado, fonte):
        marcas = list(_MARCADOR.finditer(texto))
        for i, marca in enumerate(marcas):
            fim = marcas[i+1].start() if i+1 < len(marcas) else len(texto)
            incluir(texto[marca.end():fim], papel_da_parte(marca[1]) if marca[1] else lado, fonte)

    for linha in partes:
        if len(linha) < 2:
            continue
        rotulo = linha[0].strip()
        if advogado := _PAPEL.fullmatch(rotulo):
            incluir(" ".join(linha[1:]), papel_da_parte(advogado[1]) if advogado[1] else None, "capa e-SAJ")
        elif lado := papel_da_parte(rotulo):
            rotulados(" ".join(linha[1:]), lado, "capa e-SAJ")
    for pub in publicacoes:
        for linha in pub.splitlines():
            if re.search(r"\b(?:testemunhas?|terceir[oa]s?|perit[oa]s?|representantes?)\s*:", linha, re.I):
                continue
            if inicio := _PUBLICACAO.search(linha):
                trecho = re.split(r"\b(?:despacho|decisão|sentença|ato ordinat[oó]rio|vistos)\b\s*:?",
                                  linha[inicio.start(1):], maxsplit=1, flags=re.I)[0]
                rotulados(trecho, None, "Publicações")
    return list(advogados.values())


class CaptchaOAB(Exception):
    """A recognized individual challenge, requiring manual verification."""


def consulta_oab(alvo: dict) -> dict:
    if alvo.get("papel") != "advogado":
        raise ValueError("O cadastro OAB exige alvo advogado.")
    return dict(id=identificador(alvo["id"], "pendência OAB"), alvo_id=alvo["id"],
                nome=alvo["nome"], oab=alvo.get("oab", ""), uf=alvo.get("uf", ""),
                url=URL_CADASTRO, estado="pendente", motivo="conferência manual no cadastro",
                verificacao="nao_verificado")


class CadastroOAB:
    def __init__(self, consulta=None):
        self.consulta = consulta

    def consultar(self, alvo):
        pendente = consulta_oab(alvo)
        if self.consulta is None:
            return [pendente]
        try:
            resposta = self.consulta(alvo)
        except CaptchaOAB:
            resposta = {"estado": "captcha"}
        if isinstance(resposta, dict) and resposta.get("estado") == "captcha":
            return [pendente | {"motivo": "captcha"}]
        if not isinstance(resposta, list):
            raise RuntimeError("Cadastro OAB indisponível.")
        return [_registro({**r, "alvo_id": alvo["id"]}, "registro") for r in resposta]


def _registro(registro, tipo):
    campos = ("alvo_id", "nome", "oab", "uf", "url", "data")
    if any(not isinstance(registro.get(k), str) or not registro[k].strip() for k in campos):
        raise ValueError("Campos obrigatórios da conferência OAB ausentes.")
    valores = {k: registro[k].strip() for k in campos}
    valores["oab"] = valores["oab"].replace(".", "").upper()
    valores["uf"] = valores["uf"].upper()
    if not re.fullmatch(r"[0-9]{1,9}[A-Z]?", valores["oab"]) or valores["uf"] not in _UFS:
        raise ValueError("OAB ou UF inválida.")
    url = urlsplit(valores["url"])
    if url.scheme != "https" or not url.hostname or url.username or url.password:
        raise ValueError("URL inválida para o cadastro OAB.")
    try:
        datetime.fromisoformat(valores["data"])
    except ValueError:
        raise ValueError("Data da conferência OAB inválida.") from None
    prof = registro.get("dados_profissionais")
    if isinstance(prof, dict):
        if not prof or any(not isinstance(k, str) or not isinstance(v, str) or not k.strip() or not v.strip() for k,v in prof.items()):
            raise ValueError("Campos profissionais inválidos.")
    elif not isinstance(prof, str) or not prof.strip():
        raise ValueError("Dados profissionais da conferência ausentes.")
    aid = valores["alvo_id"]
    cid = identificador(aid, "OAB", tipo, valores["uf"], valores["oab"])
    trecho = json.dumps({**valores, "dados_profissionais": prof}, ensure_ascii=False, sort_keys=True)
    digest = hashlib.sha256(trecho.encode()).hexdigest()
    estado = "manual" if tipo == "manual" else "nao_verificado"
    e = dict(id=identificador(cid, digest), candidato_id=cid, categoria="registro profissional", fonte="OAB",
             url=valores["url"], data=valores["data"], trecho=trecho, sha256=digest, tipo=tipo, estado=estado)
    return dict(**valores, id=cid, categoria="registro profissional", fonte="OAB", verificacao=estado,
                confianca="baixa", dados_profissionais=prof, evidencias=[e], evidencias_ids=[e["id"]])


def importar_manual(registro: dict) -> dict:
    return _registro(registro, "manual")
