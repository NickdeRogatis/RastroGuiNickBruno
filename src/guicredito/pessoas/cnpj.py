"""Build and consult a read-only public registry snapshot using an explicit layout."""
import csv
import hashlib
import io
import json
import os
import re
import shutil
import sqlite3
import tempfile
import zipfile
from collections.abc import Mapping
from contextlib import closing
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

from guicredito.djen.texto import normalizar
from .entrada import identificador


URL_FONTE = "https://dados.gov.br/dados/conjuntos-dados/cadastro-nacional-da-pessoa-juridica---cnpj"
_REQUERIDAS = {
    "empresas": {"cnpj_basico", "nome", "capital_social"},
    "socios": {"cnpj_basico", "nome"},
    "estabelecimentos": {"cnpj_basico", "situacao"},
}


@dataclass(frozen=True)
class LayoutCNPJ:
    colunas: dict
    encoding: str
    separador: str
    cabecalho: bool
    estimativas: dict
    situacoes: dict | None = None

    def validar(self):
        if len(self.separador) != 1 or type(self.cabecalho) is not bool:
            raise ValueError("Leiaute CNPJ inválido.")
        if set(self.colunas) != _REQUERIDAS.keys():
            raise ValueError("Tabelas do leiaute CNPJ incompletas.")
        for tabela, colunas in self.colunas.items():
            if not _REQUERIDAS[tabela].issubset(colunas):
                raise ValueError("Colunas obrigatórias do CNPJ ausentes.")
            if not all(type(i) is int and i >= 0 for i in colunas.values()):
                raise ValueError("Índices de colunas inválidos no leiaute.")


@dataclass
class ManifestoCNPJ:
    competencia: str
    hashes: dict
    contagens: dict
    data: str


def estimar_espaco(tamanhos, temporarios, indice_novo, indice_anterior, livre):
    partes = tamanhos.values() if isinstance(tamanhos, Mapping) else tamanhos
    valores = list(partes) if isinstance(tamanhos, (dict, list, tuple)) else []
    resultado = dict(necessario=None, disponivel=livre, indice_anterior=indice_anterior,
                     pico_total=None, estado="indeterminado")
    if not valores or any(type(v) is not int or v < 0 for v in [*valores, temporarios, indice_novo, indice_anterior, livre]):
        return resultado
    necessario = sum(valores) + temporarios + indice_novo
    resultado.update(necessario=necessario, pico_total=necessario + indice_anterior,
                     estado="suficiente" if livre >= necessario else "insuficiente")
    return resultado


def _disco(indice):
    pasta = indice.parent
    while not pasta.exists():
        pasta = pasta.parent
    return (indice.stat().st_size if indice.is_file() else 0, shutil.disk_usage(pasta).free)


def prever_espaco(estimativas: Path, indice: Path) -> dict:
    estimado = json.loads(estimativas.read_text(encoding="utf-8"))
    anterior, livre = _disco(indice)
    return estimar_espaco(estimado.get("tamanhos"), estimado.get("temporarios"),
                          estimado.get("indice_novo"), anterior, livre)


_SCHEMA = """
    CREATE TABLE empresas (base TEXT PRIMARY KEY, nome TEXT NOT NULL, normal TEXT NOT NULL, capital TEXT NOT NULL);
    CREATE TABLE socios (base TEXT NOT NULL, nome TEXT NOT NULL, normal TEXT NOT NULL, origem TEXT NOT NULL);
    CREATE TABLE estabelecimentos (base TEXT NOT NULL, cnpj TEXT NOT NULL, situacao TEXT NOT NULL, matriz TEXT NOT NULL, origem TEXT NOT NULL);
    CREATE TABLE manifesto (registro TEXT NOT NULL);
"""
_INDICES = """
    CREATE INDEX idx_socios ON socios(normal,base);
    CREATE INDEX idx_empresas ON empresas(normal);
    CREATE INDEX idx_estab ON estabelecimentos(base);
    CREATE INDEX idx_cnpj ON estabelecimentos(cnpj);
"""
_INSERTS = {
    "empresas": "INSERT INTO empresas VALUES (?,?,?,?)",
    "socios": "INSERT INTO socios VALUES (?,?,?,?)",
    "estabelecimentos": "INSERT INTO estabelecimentos VALUES (?,?,?,?,?)",
}


def _registros(bruto, tabela, layout, origem):
    with io.TextIOWrapper(bruto, encoding=layout.encoding, newline="") as texto:
        leitor = csv.reader(texto, delimiter=layout.separador, strict=True)
        if layout.cabecalho:
            next(leitor, None)
        for n, linha in enumerate(leitor, 1):
            if not linha:
                continue
            try:
                campos = {campo: linha[i].strip() for campo, i in layout.colunas[tabela].items()}
            except IndexError:
                raise ValueError("Registro CNPJ incompleto.") from None
            base = campos["cnpj_basico"]
            if not re.fullmatch(r"[0-9A-Z]{8}", base):
                raise ValueError("CNPJ básico inválido no snapshot.")
            if tabela == "estabelecimentos":
                cnpj = campos.get("cnpj", "")
                if not cnpj and "ordem" in campos and "dv" in campos:
                    cnpj = base + campos["ordem"] + campos["dv"]
                if cnpj and (not re.fullmatch(r"[A-Z0-9]{12}[0-9]{2}", cnpj) or cnpj[:8] != base):
                    raise ValueError("CNPJ do estabelecimento incompatível.")
                situacao = (layout.situacoes or {}).get(campos["situacao"], campos["situacao"])
                yield base, cnpj, situacao, campos.get("matriz", ""), "" if cnpj else f"{origem}/{n}"
            elif tabela == "empresas":
                yield base, campos["nome"], normalizar(campos["nome"]), campos["capital_social"]
            else:
                # Never index masked identifiers. Each source row can be a different person.
                yield base, campos["nome"], normalizar(campos["nome"]), f"{origem}/{n}"


def _carregar(con, tabela, arquivo, layout):
    mudancas = con.total_changes
    with arquivo.open("rb") as stream:
        antes = os.fstat(stream.fileno())
        digest = hashlib.file_digest(stream, "sha256").hexdigest()
        stream.seek(0)
        if arquivo.suffix.lower() == ".zip":
            with zipfile.ZipFile(stream) as z:
                membros = [m for m in z.infolist() if not m.is_dir()]
                if not membros:
                    raise ValueError("Arquivo ZIP sem registros.")
                for m in membros:
                    with z.open(m) as bruto:
                        origem = identificador(arquivo.name, digest, m.filename)
                        con.executemany(_INSERTS[tabela], _registros(bruto, tabela, layout, origem))
        else:
            # _registros owns its text wrapper; keep the original fd for the consistency check.
            with os.fdopen(os.dup(stream.fileno()), "rb") as bruto:
                con.executemany(_INSERTS[tabela], _registros(bruto, tabela, layout, digest))
        depois = os.fstat(stream.fileno())
        if (antes.st_size, antes.st_mtime_ns) != (depois.st_size, depois.st_mtime_ns):
            raise ValueError("Snapshot alterado durante a importação.")
    return digest, con.total_changes - mudancas


def importar_snapshot(arquivos: Mapping, competencia: str, destino: Path, layout: LayoutCNPJ) -> ManifestoCNPJ:
    layout.validar()
    if not re.fullmatch(r"[0-9]{4}-(?:0[1-9]|1[0-2])", competencia):
        raise ValueError("Competência CNPJ inválida.")
    if set(arquivos) != _REQUERIDAS.keys():
        raise ValueError("Snapshot incompleto.")
    listas = {ch: [Path(v)] if isinstance(v, (str, Path)) else list(map(Path, v)) for ch, v in arquivos.items()}
    fontes = [p.resolve() for partes in listas.values() for p in partes]
    if not all(listas.values()) or len(set(fontes)) != len(fontes) or destino.resolve() in fontes:
        raise ValueError("Arquivos CNPJ inválidos ou repetidos.")
    anterior, livre = _disco(destino)
    # Compressed inputs are already present. The builder streams them without extracting to disk.
    previsto = estimar_espaco([0], layout.estimativas.get("temporarios"),
                              layout.estimativas.get("indice_novo"), anterior, livre)
    if previsto["estado"] != "suficiente":
        raise ValueError("Espaço " + previsto["estado"] + " para construir o índice.")
    destino.parent.mkdir(parents=True, exist_ok=True)
    fd, nome = tempfile.mkstemp(prefix=".cnpj-", suffix=".sqlite", dir=destino.parent)
    os.close(fd)
    novo = Path(nome)
    manifesto = ManifestoCNPJ(competencia, {}, dict.fromkeys(_REQUERIDAS, 0),
                              datetime.now(timezone.utc).isoformat())
    try:
        with closing(sqlite3.connect(novo)) as con:
            con.executescript(_SCHEMA)
            for tabela, partes in listas.items():
                for i, arquivo in enumerate(partes):
                    digest, total = _carregar(con, tabela, arquivo, layout)
                    manifesto.hashes[f"{tabela}/{i}/{arquivo.name}"] = digest
                    manifesto.contagens[tabela] += total
            for tabela in ("socios", "estabelecimentos"):
                sem_empresa = con.execute(f"""
                    SELECT 1 FROM {tabela} t WHERE NOT EXISTS (
                        SELECT 1 FROM empresas e WHERE e.base=t.base
                    ) LIMIT 1
                """).fetchone()
                if sem_empresa:
                    raise ValueError("Snapshot incompleto: falta cadastro empresarial.")
            con.executescript(_INDICES)
            con.execute("PRAGMA user_version=1")
            con.execute("INSERT INTO manifesto VALUES (?)", (json.dumps(asdict(manifesto)),))
            con.commit()
        os.replace(novo, destino)
    finally:
        novo.unlink(missing_ok=True)
    return manifesto


def preparar_cnpj(snapshot: Path, layout: Path, competencia: str, indice: Path) -> ManifestoCNPJ:
    esquema = json.loads(layout.read_text(encoding="utf-8"))
    if layout.resolve() == indice.resolve():
        raise ValueError("O índice precisa de um arquivo próprio.")
    arquivos = {}
    for nome, valores in esquema["arquivos"].items():
        partes = [valores] if isinstance(valores, str) else valores
        caminhos = [(snapshot / p).resolve() for p in partes]
        if any(not p.is_relative_to(snapshot.resolve()) for p in caminhos):
            raise ValueError("Arquivo fora do snapshot.")
        arquivos[nome] = caminhos
    leiaute = LayoutCNPJ(esquema["colunas"], esquema["encoding"], esquema["separador"],
                         esquema["cabecalho"], esquema.get("estimativas", {}), esquema.get("situacoes"))
    return importar_snapshot(arquivos, competencia, indice, leiaute)


class IndiceCNPJ:
    def __init__(self, caminho: Path):
        self.caminho = Path(caminho)

    def consultar(self, alvo: dict) -> list[dict]:
        if not self.caminho.is_file():
            raise FileNotFoundError("Índice CNPJ não configurado.")
        try:
            with closing(sqlite3.connect(self.caminho.resolve().as_uri() + "?mode=ro", uri=True)) as con:
                con.row_factory = sqlite3.Row
                if con.execute("PRAGMA user_version").fetchone()[0] != 1:
                    raise ValueError("Versão do índice CNPJ inválida.")
                meta = json.loads(con.execute("SELECT registro FROM manifesto").fetchone()[0])
                if alvo["tipo"] == "PF" and alvo["papel"] == "devedor":
                    linhas = con.execute("""
                        SELECT s.nome AS pessoa,s.origem,e.* FROM socios s JOIN empresas e ON e.base=s.base
                        WHERE s.normal=? ORDER BY s.base,s.origem
                    """, (normalizar(alvo["nome"]),))
                    achados = []
                    for socio in linhas:
                        unidades = list(con.execute("SELECT * FROM estabelecimentos WHERE base=?", (socio["base"],)))
                        matriz = next((u for u in unidades if u["matriz"] == "1"), None)
                        unidade = matriz or (unidades[0] if len(unidades) == 1 else {})
                        achados.append(_candidato(alvo, socio, unidade, meta, socio["origem"]))
                    return achados
                if alvo["tipo"] == "PJ" and alvo["papel"] in {"devedor", "credor"}:
                    if alvo.get("cnpj"):
                        campo, valor = "u.cnpj", re.sub(r"[./\-]", "", alvo["cnpj"]).upper()
                    else:
                        campo, valor = "e.normal", normalizar(alvo["nome"])
                    linhas = con.execute(f"""
                        SELECT e.*,u.cnpj,u.situacao,u.origem FROM empresas e LEFT JOIN estabelecimentos u ON e.base=u.base
                        WHERE {campo}=? ORDER BY e.base,u.cnpj
                    """, (valor,))
                    return [_candidato(alvo, u, u, meta, "") for u in linhas]
                return []
        except (sqlite3.Error, IndexError, KeyError, TypeError, json.JSONDecodeError):
            raise ValueError("Índice CNPJ inválido ou corrompido.") from None


def _candidato(alvo, empresa, unidade, meta, origem):
    categoria = "participação empresarial" if origem else "cadastro empresarial"
    cnpj = unidade["cnpj"] if unidade else ""
    situacao = unidade["situacao"] if unidade else ""
    chave = identificador(alvo["id"], "CNPJ", meta["competencia"], empresa["base"],
                         origem or cnpj or unidade["origem"] or "")
    trecho = " | ".join(str(x or "") for x in (meta["competencia"], empresa["base"], empresa["nome"],
                                                 empresa["pessoa"] if origem else "", empresa["capital"], situacao))
    eid = identificador(chave, trecho)
    evidencia = dict(id=eid, candidato_id=chave, categoria=categoria, fonte="CNPJ", url=URL_FONTE,
                     data=meta["data"], competencia=meta["competencia"], trecho=trecho, tipo="registro",
                     sha256=hashlib.sha256(trecho.encode()).hexdigest(), estado="nao_verificado")
    return dict(id=chave, alvo_id=alvo["id"], nome=empresa["pessoa"] if origem else empresa["nome"],
                processo=alvo.get("processo"), fonte="CNPJ", categoria=categoria, confianca="baixa",
                verificacao="nao_verificado", empresa=empresa["nome"], capital_social=empresa["capital"],
                situacao=situacao, cnpj=cnpj, cnpj_basico=empresa["base"],
                evidencias=[evidencia], evidencias_ids=[eid])
