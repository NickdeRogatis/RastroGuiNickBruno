import hashlib
import json
import zipfile

import pytest

from guicredito.pessoas.cnpj import IndiceCNPJ, estimar_espaco, preparar_cnpj, prever_espaco


@pytest.fixture
def snapshot(tmp_path):
    pasta = tmp_path / "snapshot"
    pasta.mkdir()
    layout = {
        "arquivos": {"socios": ["socios1.zip", "socios2.csv"], "empresas": ["empresas.csv"],
                     "estabelecimentos": ["estab.csv"]},
        "colunas": {"socios": {"cnpj_basico": 0, "nome": 1}, "empresas": {"cnpj_basico": 0, "nome": 1, "capital_social": 2},
                    "estabelecimentos": {"cnpj_basico": 0, "cnpj": 1, "situacao": 2, "matriz": 3}},
        "encoding": "latin-1", "separador": ";", "cabecalho": False,
        "estimativas": {"temporarios": 1000000, "indice_novo": 1000000},
    }
    (pasta / "empresas.csv").write_text("00000001;BANCO EXEMPLO S.A.;100000,00\n00000002;EMPRESA EXEMPLO LTDA;200000,00\n", encoding="latin-1")
    (pasta / "estab.csv").write_text("00000001;00000001000136;ATIVA;1\n00000001;00000001000217;BAIXADA;2\n00000002;00000002000180;ATIVA;1\n", encoding="latin-1")
    with zipfile.ZipFile(pasta / "socios1.zip", "w") as z:
        z.writestr("socios.parte1", "00000001;JOÃO EXEMPLO;***123456**\n".encode("latin-1"))
        z.writestr("socios.parte2", "00000001;TERCEIRO EXEMPLO;***654321**\n".encode("latin-1"))
    (pasta / "socios2.csv").write_text("00000002;JOÃO EXEMPLO;***123456**\n", encoding="latin-1")
    leiaute = tmp_path / "layout.json"
    leiaute.write_text(json.dumps(layout))
    return pasta, leiaute, "2026-11", tmp_path / "indice.sqlite"


def test_socios_por_nome(snapshot):
    manifesto = preparar_cnpj(*snapshot)
    assert manifesto.competencia == "2026-11"
    assert manifesto.contagens == {"socios": 3, "estabelecimentos": 3, "empresas": 2}
    assert len(manifesto.hashes) == 4
    indice = IndiceCNPJ(snapshot[-1])
    alvo = {"id": "alvo1", "processo": "exemplo", "nome": "João Exemplo", "tipo": "PF", "papel": "devedor"}
    candidatos = indice.consultar(alvo)
    assert len(candidatos) == 2
    assert len({c["id"] for c in candidatos}) == 2
    assert {c["empresa"] for c in candidatos} == {"BANCO EXEMPLO S.A.", "EMPRESA EXEMPLO LTDA"}
    um = next(c for c in candidatos if c["empresa"] == "BANCO EXEMPLO S.A.")
    assert (um["capital_social"], um["situacao"]) == ("100000,00", "ATIVA")
    assert um["verificacao"] == "nao_verificado"
    e = um["evidencias"][0]
    assert e["categoria"] == "participação empresarial" and e["candidato_id"] == um["id"]
    assert hashlib.sha256(e["trecho"].encode()).hexdigest() == e["sha256"]
    assert "123456" not in json.dumps(candidatos)
    assert indice.consultar(dict(alvo, papel="credor")) == []
    assert indice.consultar(dict(alvo, nome="SEM REGISTRO")) == []


def test_pj_apenas_sua_inscricao(snapshot):
    preparar_cnpj(*snapshot)
    alvo = {"id": "pj", "papel": "devedor", "tipo": "PJ", "nome": "BANCO EXEMPLO S.A.", "cnpj": "00000001000217"}
    itens = IndiceCNPJ(snapshot[-1]).consultar(alvo)
    assert len(itens) == 1 and itens[0]["situacao"] == "BAIXADA" and itens[0]["cnpj"] == alvo["cnpj"]
    assert itens[0]["categoria"] == "cadastro empresarial"
    assert "JOÃO EXEMPLO" not in json.dumps(itens, ensure_ascii=False)
    assert "TERCEIRO EXEMPLO" not in json.dumps(itens)
    assert IndiceCNPJ(snapshot[-1]).consultar(dict(alvo, cnpj="00000001000306")) == []


def test_refresh_interrompido(snapshot):
    preparar_cnpj(*snapshot)
    antes = snapshot[-1].read_bytes()
    (snapshot[0] / "socios2.csv").write_text("truncado\n", encoding="latin-1")
    with pytest.raises(ValueError):
        preparar_cnpj(*snapshot)
    assert snapshot[-1].read_bytes() == antes
    assert sorted(p.name for p in snapshot[-1].parent.iterdir()) == ["indice.sqlite", "layout.json", "snapshot"]


def test_ausente_ou_corrompido(tmp_path):
    alvo = {"id": "exemplo", "tipo": "PJ", "nome": "BANCO EXEMPLO S.A.", "papel": "credor"}
    p = tmp_path / "indice"
    with pytest.raises(FileNotFoundError):
        IndiceCNPJ(p).consultar(alvo)
    assert not p.exists()
    p.write_bytes(b"corrompido")
    with pytest.raises(ValueError, match="ndice"):
        IndiceCNPJ(p).consultar(alvo)


def test_prevoo_conta_so_bytes_adicionais(tmp_path):
    assert estimar_espaco({"arquivo": 20}, 30, 50, 70, 100) == {
        "necessario": 100, "disponivel": 100, "indice_anterior": 70, "pico_total": 170, "estado": "suficiente"
    }
    assert estimar_espaco([20], 30, 50, 70, 99)["estado"] == "insuficiente"
    for valores in ([], [None], [-1], {"a": True}):
        assert estimar_espaco(valores, 30, 50, 0, 100)["estado"] == "indeterminado"
    estimativas = tmp_path / "tamanho.json"
    estimativas.write_text(json.dumps({"tamanhos": {"arquivo": 20}, "temporarios": 30, "indice_novo": 50}))
    resultado = prever_espaco(estimativas, tmp_path / "indice")
    assert resultado["estado"] == "suficiente" and resultado["necessario"] == 100


@pytest.mark.parametrize("valor", [None, 10**22])
def test_sem_estimativa_ou_sem_espaco_sem_criar_indice(snapshot, valor):
    layout = json.loads(snapshot[1].read_text())
    layout["estimativas"]["indice_novo"] = valor
    snapshot[1].write_text(json.dumps(layout))
    with pytest.raises(ValueError, match="spaço"):
        preparar_cnpj(*snapshot)
    assert not snapshot[-1].exists()


def test_recusa_snapshot_com_partes_faltantes(snapshot):
    (snapshot[0] / "empresas.csv").write_text("00000001;BANCO EXEMPLO S.A.;100000,00\n", encoding="latin-1")
    with pytest.raises(ValueError, match="incompleto"):
        preparar_cnpj(*snapshot)
    assert not snapshot[-1].exists()


def test_pj_sem_inscricao_completa_mantem_estabelecimentos_distintos(snapshot):
    esquema = json.loads(snapshot[1].read_text())
    del esquema["colunas"]["estabelecimentos"]["cnpj"]
    snapshot[1].write_text(json.dumps(esquema))
    preparar_cnpj(*snapshot)
    pj = {"id": "pj", "papel": "credor", "tipo": "PJ", "nome": "BANCO EXEMPLO S.A."}
    achados = IndiceCNPJ(snapshot[-1]).consultar(pj)
    assert {a["situacao"] for a in achados} == {"ATIVA", "BAIXADA"}
    assert len({a["id"] for a in achados}) == 2
