"""Read the existing selection, covers and DJEN workbook without modifying them."""
import hashlib
import json
import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from openpyxl import load_workbook

from guicredito.aprofundamento.cnj import normalizar as normalizar_cnj
from guicredito.aprofundamento.fluxo import ler_selecao
from guicredito.djen.partes import eh_empresa, partes_do_cabecalho
from guicredito.djen.texto import normalizar


@dataclass
class Entrada:
    casos: list[dict]
    alvos: list[dict]
    publicacoes: dict[str, list[str]]
    hashes: dict[str, str]
    limitacoes: list[str]


def identificador(*campos: str) -> str:
    return hashlib.sha256(json.dumps(campos, ensure_ascii=False).encode()).hexdigest()[:32]


def _hash(arquivo):
    with arquivo.open("rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()


def papel_da_parte(rotulo):
    r = normalizar(rotulo).strip(".: ")
    if r in {"exeqte", "exequente", "exequentes", "autor", "autora", "reqte", "requerente", "credor", "credora"}:
        return "credor"
    if r in {"executado", "executada", "executados", "executadas", "exectdo", "exectda",
             "exectdo(a)", "execdo", "executado(a)", "devedor", "devedora", "reu", "re",
             "reqdo", "reqda", "requerido", "requerida", "avalista", "fiador", "fiadora",
             "coobrigado", "coobrigada"}:
        return "devedor"
    return None


_ADV = re.compile(r"\b(?:advogad[oa]s?|adv(?:s)?\.?)\s*:", re.I)
_DOC = re.compile(r"(?:,?\s*\(?\b(?:CNPJ|CPF)\b\s*[:.]?\s*[\d.*/-]+\)?)", re.I)
_CNPJ = re.compile(r"\bCNPJ\s*:?\s*(\d{2}\.?\d{3}\.?\d{3}/?\d{4}-?\d{2})\b", re.I)


def _nome(bruto):
    bruto = re.sub(r"\s*\[avalista/sócio\]\s*$", "", bruto, flags=re.I)
    nome = _DOC.sub("", bruto).strip(" ,;-:")
    if normalizar(nome) in {"nao identificado", "nao identificada", "desconhecido", "outros", "sigiloso"}:
        return None
    if not nome or len(nome) > 180 or not re.fullmatch(r"[\w .&/'’\-]+", nome):
        return None
    # Skip ambiguous narrative, labels and embedded identifiers.
    if re.search(r"\d{4,}|\b(?:testemunha|vizinho|sócio|ouça|intime|citou|mencionou)\b", nome, re.I):
        return None
    return nome


def _cabecalhos(texto):
    # Only parse explicit party fields in the header. Never pass the body to a name parser.
    linhas = re.split(r"\b(?:despacho|decisão|sentença|ato ordinat[oó]rio|intime-se|vistos)\b", texto,
                      maxsplit=1, flags=re.I)[0].splitlines()
    for linha in linhas:
        # Bound free text after the field; the existing parser handles chained role labels.
        for trecho in re.split(r";|(?<=\.)\s+(?=[A-ZÁ-Ú][a-zá-ú])", linha):
            if not re.match(r"^\s*(?:EXEQUENTES?|EXECUTAD[OA]S?|REQUERENTES?|REQUERID[OA]S?|AUTORES?|AUTOR|R[EÉ]US?)\s*:", trecho, re.I):
                continue
            credores, devedores = partes_do_cabecalho(trecho.upper())
            for papel, nomes in (("credor", credores), ("devedor", devedores)):
                for nome in nomes:
                    yield papel, nome


def extrair_alvos(partes, publicacoes, caso):
    alvos = {}
    processo = caso["processo"]
    def incluir(papel, bruto, origem):
        if not isinstance(bruto, str):
            return
        for parte in re.split(r"[;\n]", _ADV.split(bruto, maxsplit=1)[0]):
            nome = _nome(parte)
            if nome is None:
                continue
            cnpj = _CNPJ.search(parte)
            chave = identificador(processo, papel, normalizar(nome))
            if chave not in alvos:
                alvos[chave] = {
                    "id": chave, "processo": processo, "papel": papel, "nome": nome,
                    "tipo": "PJ" if cnpj or eh_empresa(nome) else "PF", "lado": papel,
                    "origem": {"fonte": origem}, "cidade": caso.get("cidade") or "",
                }
            if cnpj:
                alvos[chave].update(tipo="PJ", cnpj=re.sub(r"\D", "", cnpj[1]))

    for linha in partes:
        if len(linha) >= 2 and (papel := papel_da_parte(linha[0])):
            incluir(papel, linha[1], "capa e-SAJ")
    for papel in ("credor", "devedor"):
        incluir(papel, caso.get(papel), "Casos")
    for publicacao in publicacoes:
        for papel, nome in _cabecalhos(publicacao):
            incluir(papel, nome, "Publicações")
    return list(alvos.values())


def _capa(pasta, caso, hashes):
    n = caso["processo"]
    subpasta = pasta / n
    arq = subpasta / "resultado.json"
    if subpasta.is_symlink() or arq.is_symlink():
        raise ValueError("Caminho da capa inválido.")
    if not arq.exists():
        caso["limitacoes"].append("capa ausente")
        return []
    dados = json.loads(arq.read_bytes())
    if normalizar_cnj(dados["numero_processo"]) != n or dados.get("status") == "processo_divergente":
        raise ValueError("CNJ divergente no resultado.")
    for campo in ("pontuacao_original", "posicao_original"):
        if campo in dados and dados[campo] != caso[campo]:
            raise ValueError("Dados do resultado divergem da seleção.")
    prefixo = f"capa-{caso['posicao_original']}"
    hashes[prefixo] = _hash(arq)
    for e in dados.get("evidencias", []):
        nome = e.get("arquivo")
        if not isinstance(nome, str) or Path(nome).name != nome or nome in {"", ".", ".."}:
            raise ValueError("Caminho de evidência inválido.")
        arquivo = subpasta / nome
        if arquivo.is_symlink() or not arquivo.is_file() or _hash(arquivo) != e.get("sha256"):
            raise ValueError("Hash de evidência inválido.")
        hashes[prefixo + "-" + nome] = e["sha256"]
    if dados.get("status") not in {"coletado", "coletado_parcial"}:
        caso["limitacoes"].append("capa ausente")
        return []
    campos = dados.get("campos") or {}
    caso["classe"] = campos.get("classe") or caso.get("classe", "")
    return dados.get("partes_linhas", [])


def _linhas(aba, colunas):
    linhas = iter(aba.values)
    cab = next(linhas, ())
    if not set(colunas).issubset(cab) or any(cab.count(c) > 1 for c in colunas):
        raise ValueError("Colunas inválidas na planilha de entrada.")
    for valores in linhas:
        yield dict(zip(cab, valores))


def _numero(valor):
    try:
        return normalizar_cnj(str(valor))
    except ValueError:
        return ""


def _referencia(caso, alvo, numero, fonte, data):
    cid = identificador(alvo["id"], "outro processo", numero)
    eid = identificador(cid, fonte, data)
    trecho = f"{alvo['nome']} — {numero}"
    if not any(e["id"] == eid for e in caso["evidencias"]):
        caso["evidencias"].append(dict(
            id=eid, candidato_id=cid, categoria="outro processo", fonte=fonte,
            data=data, trecho=trecho, sha256=hashlib.sha256(trecho.encode()).hexdigest(),
            estado="nao_verificado", tipo="registro", url="",
        ))
    candidato = next((c for c in caso["candidatos"] if c["id"] == cid), None)
    if candidato is None:
        candidato = dict(id=cid, alvo_id=alvo["id"], processo=caso["processo"],
                         nome=alvo["nome"], fonte="planilha DJEN", confianca="baixa",
                         verificacao="nao_verificado", processo_referenciado=numero,
                         categoria="outro processo", evidencias_ids=[])
        caso["candidatos"].append(candidato)
    if eid not in candidato["evidencias_ids"]:
        candidato["evidencias_ids"].append(eid)


def _cruzar(wb, casos, data):
    # The second pass reads party fields only and keeps references to matching names.
    devedores = {}
    for caso in casos:
        for alvo in caso["alvos"]:
            if alvo["papel"] == "devedor" and alvo["tipo"] == "PF":
                devedores.setdefault(normalizar(alvo["nome"]), []).append((caso, alvo))
    for aba in ("Casos", "Publicações"):
        for row in _linhas(wb[aba], ["Processo"]):
            numero = _numero(row["Processo"])
            if not numero:
                continue
            if aba == "Casos":
                nomes = [row.get("Credor"), row.get("Devedor")]
            else:
                nomes = [nome for _, nome in _cabecalhos(str(row.get("Texto") or ""))]
            quando = row.get("Data") or data
            quando = quando.isoformat() if isinstance(quando, date) else str(quando or "")
            for bruto in nomes:
                for parte in re.split(r"[;\n]", str(bruto or "")):
                    for caso, alvo in devedores.get(normalizar(_nome(parte) or ""), []):
                        if numero != caso["processo"]:
                            _referencia(caso, alvo, numero, aba, quando)


def ler_entrada(selecao: Path, aprofundamento: Path, planilha: Path) -> Entrada:
    sel = ler_selecao(selecao)
    if sel.get("versao") != 1:
        raise ValueError("Versão de seleção inválida.")
    hashes = {"selecao": _hash(selecao), "planilha": _hash(planilha)}
    manifesto = aprofundamento / "selecao.json"
    if manifesto.is_symlink():
        raise ValueError("Caminho do manifesto inválido.")
    if manifesto.is_file():
        anterior = ler_selecao(manifesto)
        if anterior["casos"] != sel["casos"] or anterior.get("versao") != sel["versao"]:
            raise ValueError("Manifesto do aprofundamento diverge da seleção.")
        hashes["manifesto"] = _hash(manifesto)
    casos = {
        c["numero_processo"]: dict(processo=c["numero_processo"], posicao_original=c["posicao_original"],
                                   pontuacao_original=c["pontuacao_original"], limitacoes=[],
                                   candidatos=[], evidencias=[]) for c in sel["casos"]
    }
    posicoes = [c["posicao_original"] for c in casos.values()]
    if any(type(p) is not int or p < 1 for p in posicoes) or len(set(posicoes)) != len(posicoes):
        raise ValueError("Posições inválidas na seleção.")
    pubs = {n: [] for n in casos}
    wb = load_workbook(planilha, read_only=True, data_only=True)
    try:
        vistas = set()
        for row in _linhas(wb["Casos"], ["Processo", "#", "Pontos", "Credor", "Devedor"]):
            numero = _numero(row["Processo"])
            if numero not in casos:
                continue
            caso = casos[numero]
            if numero in vistas or (row["#"], row["Pontos"]) != (caso["posicao_original"], caso["pontuacao_original"]):
                raise ValueError("Posição ou pontuação divergente na planilha.")
            vistas.add(numero)
            caso.update(cidade=row.get("Comarca") or "", classe=row.get("Classe") or "",
                        devedor=row["Devedor"], credor=row["Credor"])
        if vistas != casos.keys():
            raise ValueError("Processo selecionado ausente na planilha.")
        for row in _linhas(wb["Publicações"], ["Processo", "Texto"]):
            numero = _numero(row["Processo"])
            if numero in casos and isinstance(row["Texto"], str):
                pubs[numero].append(row["Texto"])
        for numero, caso in casos.items():
            partes = _capa(aprofundamento, caso, hashes)
            caso["alvos"] = extrair_alvos(partes, pubs[numero], caso)
            classe = normalizar(caso.pop("classe"))
            caso["fase"] = next((f for f in ("cumprimento de sentenca", "execucao", "monitoria")
                                 if f in classe), "não informada")
            caso.pop("devedor")
            caso.pop("credor")
        _cruzar(wb, casos.values(), sel.get("selecionado_em", ""))
    finally:
        wb.close()
    return Entrada(list(casos.values()), [a for c in casos.values() for a in c["alvos"]],
                   pubs, hashes, sorted({l for c in casos.values() for l in c["limitacoes"]}))
