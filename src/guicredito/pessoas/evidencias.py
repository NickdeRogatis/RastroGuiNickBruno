"""Pesquisa de um alvo, com evidências restritas à fonte efetivamente consultada."""
import hashlib
import ipaddress
import re
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlsplit

from guicredito.djen.texto import normalizar
from .entrada import identificador
from .hermes import CATEGORIAS, INDICIOS
from .http import ErroGateway, rede_social


_EMAIL = re.compile(r"[\w.+-]+@[\w.-]+\.[a-zA-Z]{2,64}")
_TELEFONE = re.compile(r"(?<!\d)(?:\+55\s*)?\(?[1-9]\d\)?[\s.-]*(?:9\d{4}|[2-5]\d{3})[\s.-]?\d{4}(?!\d)")
_CPF = re.compile(r"(?<!\d)\d{3}\.?\d{3}\.?\d{3}-?\d{2}(?!\d)")
_MIDIA = re.compile(r"\b(post|posts|foto|fotos|video|videos|seguidores|seguindo|followers|likes|reels?)\b")
_OBJETIVOS = {"devedor": "profissional processo", "credor": "contato profissional",
              "advogado": "advocacia contato profissional"}


class ErroPesquisaParcial(ErroGateway):
    def __init__(self, parcial):
        super().__init__("Leitura interrompida após busca concluída")
        self.parcial = parcial


def _agora():
    return datetime.now(UTC).isoformat()


def _sha(texto):
    return hashlib.sha256(texto.encode()).hexdigest()


def _contem(texto, parte):
    return bool(parte.strip() and re.search(r"(?<!\w)" + re.escape(normalizar(parte)) + r"(?!\w)", normalizar(texto)))


def _consulta(alvo):
    nome, papel, tipo = alvo["nome"], alvo["papel"], alvo["tipo"]
    if papel not in _OBJETIVOS or tipo not in ("PF", "PJ") or (papel == "devedor" and tipo == "PJ"):
        return None
    # Nomes vêm de campos de parte; jamais incluir texto processual ou contatos
    # mesmo se um chamador fornecer um dicionário com campos em excesso.
    if (not isinstance(nome, str) or not 2 <= len(nome) <= 180 or not any(c.isalpha() for c in nome)
            or sum(c.isdigit() for c in nome) > (3 if tipo == "PJ" else 0)
            or not all(c.isalnum() or c in " .&'’/-" for c in nome)):
        return None
    return f'"{nome}" {_OBJETIVOS[papel]}'


def _url_permitida(url):
    try:
        p = urlsplit(url)
        if (p.scheme not in ("https", "http") or not p.hostname or p.username is not None
                or p.fragment or re.search(r"[\s\\\x00-\x1f\x7f]", url) or not 0 < (p.port or 80) < 65536
                or p.hostname == "localhost" or p.hostname.endswith((".localhost", ".local", ".internal"))):
            return False
        try:
            ip = ipaddress.ip_address(p.hostname)
        except ValueError:
            ip = None
        if ip is not None and (not ip.is_global or ip.is_multicast or ip.is_reserved):
            return False
        social = rede_social(p.hostname)
        if not social:
            return True
        caminho = p.path.strip("/")
        if social == "linkedin.com":
            return bool(re.fullmatch(r"(?:in|company)/[\w%-]+", caminho))
        if social == "facebook.com" and caminho == "profile.php":
            return bool(re.fullmatch(r"id=\d+", p.query))
        return (bool(re.fullmatch(r"[\w.-]+", caminho)) and caminho.lower() not in
                {"p", "reel", "reels", "explore", "stories", "watch", "photo.php", "photos", "groups",
                 "login", "posts", "marketplace", "friends", "accounts", "events", "share.php"})
    except (ValueError, TypeError):
        return False


def confianca(indicios, conflitos):
    if conflitos:
        return "baixa"
    campos = {i["campo"] for i in indicios if i.get("campo") in INDICIOS and i.get("valor")}
    valores = {normalizar(i["valor"]) for i in indicios if i.get("campo") in campos}
    return ("baixa", "média", "alta")[min(len(campos), len(valores), 2)]


def validar_achado(achado, resultados, paginas):
    url = achado.get("url")
    fonte = next((r for r in resultados if r.url == url), None)
    pagina = paginas.get(url)
    trecho = achado.get("trecho")
    if (not fonte or not pagina or pagina.url != url or not _url_permitida(url)
            or not isinstance(trecho, str) or not 0 < len(trecho.strip()) <= 500
            or achado.get("categoria") not in CATEGORIAS):
        return None
    de_pagina = pagina.estado == "consultado"
    origem = pagina.texto if de_pagina else fonte.snippet
    if not _contem(origem, trecho):
        return None
    trecho = trecho.strip()
    return dict(url=url, fonte="web_search", trecho=trecho, categoria=achado["categoria"],
                estado="consultado" if de_pagina else "nao_verificado",
                tipo="pagina" if de_pagina else "snippet", data=pagina.data or _agora(), sha256=_sha(trecho))


def salvar_recorte(pasta: Path, evidencia: dict, texto: str):
    if texto != evidencia["trecho"] or _sha(texto) != evidencia["sha256"]:
        raise ValueError("Recorte divergente da evidência")
    arquivo = "evidencia-" + evidencia["sha256"] + ".txt"
    caminho = Path(pasta) / arquivo
    if caminho.is_symlink():
        raise ValueError("Caminho de recorte inválido")
    if caminho.exists():
        if caminho.read_bytes() != texto.encode():
            raise ValueError("Recorte já existente incompatível")
    else:
        with caminho.open("xb") as f:
            f.write(texto.encode())
    return dict(evidencia, arquivo=arquivo)


def _contatos_profissionais(trecho):
    for match in _EMAIL.finditer(trecho):
        yield "email", match[0]
    for match in _TELEFONE.finditer(trecho):
        rotulo = normalizar(trecho[max(0, match.start() - 20):match.start()])
        tipo = "whatsapp" if re.search(r"\bwhatsapp\s*[:(\-]?\s*$", rotulo) else "telefone"
        yield tipo, match[0]


def _permitido(alvo, proposta):
    if normalizar(proposta.get("nome", "")) != normalizar(alvo["nome"]):
        return False
    trecho = proposta.get("trecho", "")
    if not _contem(trecho, alvo["nome"]):
        return False
    categoria = proposta["categoria"]
    if _CPF.search(trecho):
        return False
    if alvo["papel"] == "devedor" and (categoria == "contato_profissional" or _EMAIL.search(trecho) or _TELEFONE.search(trecho)):
        return False
    if categoria in ("emprego", "processo") and re.search(
            r"\b(nao|nunca|jamais|suposto|suposta|talvez|alegado|alegada)\b", normalizar(trecho)):
        return False
    if categoria == "emprego":
        tem_vinculo = re.search(r"\b(empregad[oa]|trabalha|funcionari[oa]|diretor[a]?|gerente|soci[oa])\b", normalizar(trecho))
        return bool(tem_vinculo or _contem(trecho, proposta["indicios"].get("empregador", "")))
    if categoria == "processo":
        return bool(re.search(r"\b(processo|tribunal|autos|executad[oa]|requerid[oa])\b", normalizar(trecho)))
    if categoria == "contato_profissional":
        return bool(list(_contatos_profissionais(trecho)))
    return True


def _adicionar(saida, alvo, proposta, ev):
    if not _permitido(alvo, proposta):
        return
    if rede_social(urlsplit(ev["url"]).hostname):
        if ev["categoria"] not in {"identidade", "emprego"} or _MIDIA.search(normalizar(ev["trecho"])):
            return
    campos = {k: v.strip() for k, v in proposta["indicios"].items()
              if k in INDICIOS and isinstance(v, str) and 0 < len(v.strip()) <= 100 and _contem(ev["trecho"], v)}
    compativeis, conflitos = [], []
    for campo, valor in campos.items():
        referencia = alvo.get(campo)
        if referencia:
            if normalizar(valor) == normalizar(referencia):
                compativeis.append({"campo": campo, "valor": valor})
            else:
                conflitos.append(campo)
    cid = identificador(alvo["id"], ev["url"], normalizar(ev["trecho"]), ev["categoria"])
    if any(c["id"] == cid for c in saida["candidatos"]):
        return
    eid = identificador(cid, ev["tipo"], ev["sha256"])
    ev.update(id=eid, candidato_id=cid, alvo_id=alvo["id"], arquivo="evidencia-" + ev["sha256"] + ".txt")
    candidato = dict(id=cid, alvo_id=alvo["id"], nome=alvo["nome"], processo=alvo["processo"],
                     papel=alvo["papel"], tipo=alvo["tipo"], fonte="web_search", chave=ev["url"],
                     verificacao="nao_verificado", confianca=confianca(compativeis, conflitos),
                     indicios=campos, conflitos=conflitos, categoria=ev["categoria"], evidencias_ids=[eid], **campos)
    saida["candidatos"].append(candidato)
    saida["evidencias"].append(ev)
    if ev["tipo"] == "pagina" and ev["categoria"] == "contato_profissional":
        for tipo, valor in dict.fromkeys(_contatos_profissionais(ev["trecho"])):
            saida["contatos"].append(dict(id=identificador(cid, tipo, valor), candidato_id=cid, tipo=tipo,
                                          valor=valor, origem=ev["url"], data_fonte=ev["data"],
                                          data_consulta=ev["data"], evidencia_id=eid))


def _preservar_barreira(saida, alvo, item, pagina):
    # Preservar somente a frase do snippet relativa ao alvo. Em perfis sociais
    # que mencionem publicações/conexões, conservar apenas o próprio nome.
    frases = re.split(r"(?<=[.!?])\s+|[\r\n]+", item.snippet)
    trecho = next((f.strip() for f in frases if _contem(f, alvo["nome"]) and len(f.strip()) <= 500), "")
    if trecho and rede_social(urlsplit(item.url).hostname) and _MIDIA.search(normalizar(trecho)):
        trecho = alvo["nome"]
    proposta = dict(nome=alvo["nome"], trecho=trecho, categoria="identidade", url=item.url, indicios={})
    ev = validar_achado(proposta, [item], {item.url: pagina}) if trecho else None
    if ev and _permitido(alvo, proposta):
        titulo = item.titulo.strip()
        if (len(titulo) <= 180 and not _MIDIA.search(normalizar(titulo)) and not _CPF.search(titulo)
                and not _EMAIL.search(titulo) and not _TELEFONE.search(titulo)):
            ev["titulo"] = titulo
        _adicionar(saida, alvo, proposta, ev)
        return
    # Com um link isolado não há candidato documentado à confirmação.
    eid = identificador(alvo["id"], item.url, "link")
    if any(e["id"] == eid for e in saida["evidencias"]):
        return
    saida["evidencias"].append(dict(id=eid,
                                    alvo_id=alvo["id"], candidato_id="", categoria="identidade",
                                    fonte="web_search", url=item.url, data=pagina.data or _agora(),
                                    trecho="", sha256=_sha(""), tipo="link", estado="nao_verificado"))


def pesquisar_web(alvo: dict, cliente, http) -> dict:
    saida = {"candidatos": [], "evidencias": [], "consultas": [], "contatos": []}
    consulta = dict(id=identificador(alvo["id"], "web_search"), alvo_id=alvo["id"], fonte="web_search",
                    data=_agora(), versao=1, estado="nao_consultado", motivo="alvo fora do escopo da busca")
    saida["consultas"].append(consulta)
    pedido = _consulta(alvo)
    if not pedido:
        return saida
    if cliente is None:
        consulta.update(estado="nao_configurado", motivo="busca não configurada")
        return saida
    cliente.exigir_politica()
    busca = cliente.buscar(pedido)
    consulta.update(estado="consultado" if busca.itens else "sem_resultados", motivo="",
                    id_resposta=busca.id_resposta, id_chamada=busca.id_chamada, backend=busca.backend,
                    ferramenta="web_search", limite=busca.limite, paginacao="uma página", quantidade=len(busca.itens))
    por_url = {}
    for item in busca.itens:
        por_url.setdefault(item.url, []).append(item)
    for url, resultados in por_url.items():
        pagina_q = dict(id=identificador(alvo["id"], "pagina", url), alvo_id=alvo["id"], fonte="página pública",
                        data=consulta["data"], versao=1, estado="nao_consultado", motivo="URL fora do escopo")
        saida["consultas"].append(pagina_q)
        if not _url_permitida(url):
            continue
        pagina = http.baixar(url)
        pagina_q.update(url=url, estado=pagina.estado, motivo=pagina.motivo, data=pagina.data or _agora())
        if pagina.estado != "consultado":
            for referencia_busca in dict.fromkeys(resultados):
                _preservar_barreira(saida, alvo, referencia_busca, pagina)
            continue
        if not _contem(pagina.texto, alvo["nome"]):
            continue
        referencia = {"nome": alvo["nome"], "papel": alvo["papel"], "url": url}
        texto = _CPF.sub("[identificador omitido]", pagina.texto)
        if alvo["papel"] == "devedor":
            texto = _TELEFONE.sub("[telefone omitido]", _EMAIL.sub("[email omitido]", texto))
        try:
            propostas = cliente.propor(texto, referencia)
        except Exception:
            saida["consultas"].append(dict(id=identificador(alvo["id"], "leitura", url), alvo_id=alvo["id"],
                                           fonte="leitura Hermes", url=url, estado="interrompido",
                                           motivo="leitura incompleta; sem reenvio", data=_agora(), versao=1))
            raise ErroPesquisaParcial(saida) from None
        for proposta in propostas:
            ev = validar_achado(proposta, resultados, {url: pagina})
            if ev:
                _adicionar(saida, alvo, proposta, ev)
    return saida
