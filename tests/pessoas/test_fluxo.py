import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from openpyxl import load_workbook

from guicredito.pessoas import fluxo
from guicredito.pessoas.config import carregar_config


def cnj(i):
    base = f"{i:07}20268260001"
    dv = 98 - int(base + "00") % 97
    return base[:7] + f"{dv:02}" + base[7:]


def entrada():
    casos = []
    for i, nome in enumerate(("JOÃO EXEMPLO", "SEGUNDO EXEMPLO"), start=1):
        numero = cnj(i)
        casos.append({"processo": numero, "posicao_original": i * 5, "pontuacao_original": 32, "fase": "execução",
                      "alvos": [{"id": f"a{i}", "nome": nome, "processo": numero, "papel": "devedor", "tipo": "PF",
                                 "lado": "devedor", "cidade": "Cidade A"}], "limitacoes": []})
    return SimpleNamespace(casos=casos, hashes={"planilha": "hash"}, limitacoes=[])


def editar(pasta, aba, coluna, valor, linha=2):
    wb = load_workbook(pasta / "pessoas.xlsx")
    ws = wb[aba]
    i = [c.value for c in ws[1]].index(coluna) + 1
    ws.cell(linha, i).value = valor
    wb.save(pasta / "pessoas.xlsx")
    wb.close()


class CNPJ:
    def __init__(self):
        self.chamadas = []
    def consultar(self, alvo):
        self.chamadas.append(alvo["id"])
        return [{"id":"c" + alvo["id"], "alvo_id":alvo["id"], "nome":alvo["nome"],
                 "cidade":"Cidade A", "fonte":"CNPJ", "confianca":"baixa", "verificacao":"nao_verificado",
                 "empresa":"EMPRESA FICTÍCIA", "capital_social":"100000,00", "evidencias": []}]


def config(tmp_path):
    return carregar_config(tmp_path / "env-ausente", {})


def test_lote_preserva_decisoes_e_descarte(tmp_path):
    f = CNPJ()
    lote = tmp_path / "lote"
    executar = lambda: fluxo.pesquisar(entrada(), config(tmp_path), {"cnpj": f}, lote)
    executar()
    assert f.chamadas == ["a1", "a2"]
    editar(lote, "Candidatos", "Confirmado", "sim", 3)
    editar(lote, "Candidatos", "Autorizar consulta paga", "sim", 3)
    executar()
    assert f.chamadas == ["a1", "a2"]
    assert fluxo.contatos(lote, None)["estado"] == "nao_configurado"
    editar(lote, "Casos", "Descartar", "sim")
    previa = fluxo.prever_descarte(lote)
    assert len(previa["rotulos"]) == 1
    with pytest.raises(ValueError):
        fluxo.confirmar_descarte(lote, "incorreto")
    assert (lote / cnj(1) / "pessoas.json").exists()
    fluxo.confirmar_descarte(lote, previa["codigo"])
    executar()
    assert f.chamadas == ["a1", "a2"]
    assert not (lote / cnj(1)).exists()
    assert (lote / cnj(2) / "pessoas.json").exists()
    assert cnj(1) not in (lote / "manifesto.json").read_text()
    assert "JOÃO EXEMPLO" not in (lote / "relatorio.html").read_text()
    wb = load_workbook(lote / "pessoas.xlsx")
    ws = wb["Candidatos"]
    assert ws.cell(2,[c.value for c in ws[1]].index("Confirmado")+1).value=="sim"
    wb.close()


def test_hash_alterado_recusa_reuso(tmp_path):
    e = entrada()
    lote = tmp_path / "lote"
    fluxo.pesquisar(e, config(tmp_path), {}, lote)
    e.hashes["planilha"] = "mudou"
    with pytest.raises(ValueError, match="entrada"):
        fluxo.pesquisar(e, config(tmp_path), {}, lote)


def test_descartar_todos_preserva_supressao_e_nao_chama_fontes(tmp_path):
    e = entrada()
    lote = tmp_path / "lote"
    fonte = CNPJ()
    fluxo.pesquisar(e, config(tmp_path), {"cnpj": fonte}, lote)
    for i in (2, 3):
        editar(lote, "Casos", "Descartar", "sim", i)
    previa = fluxo.prever_descarte(lote)
    assert len(previa["rotulos"]) == 2
    assert fluxo.confirmar_descarte(lote, previa["codigo"]) == 2
    fluxo.pesquisar(e, config(tmp_path), {"cnpj": fonte}, lote)
    assert fonte.chamadas == ["a1", "a2"]
    assert json.loads((lote / "manifesto.json").read_text())["numeros"] == []
    assert not any(p.is_dir() for p in lote.iterdir())


def test_descarte_vencido(tmp_path):
    lote = tmp_path / "lote"
    fluxo.pesquisar(entrada(), config(tmp_path), {}, lote)
    editar(lote,"Casos","Descartar","sim")
    previa=fluxo.prever_descarte(lote)
    editar(lote,"Casos","Descartar","sim",3)
    with pytest.raises(ValueError):
        fluxo.confirmar_descarte(lote,previa["codigo"])
    assert (lote / cnj(1)).is_dir()


def test_descarte_remove_referencia_cruzada_e_preserva_outros_achados(tmp_path):
    e = entrada()
    mantido = e.casos[1]
    referencia = {"id": "referencia", "nome": "SEGUNDO EXEMPLO", "alvo_id": "a2",
                  "processo_referenciado": cnj(1)}
    trecho = "Referência documental a " + cnj(1)
    sha = hashlib.sha256(trecho.encode()).hexdigest()
    mantido.update(candidatos=[referencia], evidencias=[
        {"id": "ev", "candidato_id": "referencia", "trecho": trecho, "sha256": sha}],
        contatos=[{"id": "privado", "candidato_id": "referencia", "valor": "DADO_TESTE"}],
        provedor=[{"id": "opcao", "candidato_id": "referencia"}], pedidos={"referencia": {}})
    lote = tmp_path / "lote"
    fluxo.pesquisar(e, config(tmp_path), {"cnpj": CNPJ()}, lote)
    ev, = json.loads((lote / cnj(2) / "evidencias.json").read_text())
    assert (lote / cnj(2) / ev["arquivo"]).read_text() == trecho
    editar(lote, "Casos", "Descartar", "sim")
    fluxo.confirmar_descarte(lote, fluxo.prever_descarte(lote)["codigo"])
    fluxo.pesquisar(e, config(tmp_path), {"cnpj": CNPJ()}, lote)
    assert not (lote / cnj(2) / ev["arquivo"]).exists()
    for p in lote.rglob("*"):
        if p.suffix in {".json", ".html", ".txt"}:
            texto = p.read_text()
            assert cnj(1) not in texto and "DADO_TESTE" not in texto
    assert json.loads((lote / cnj(2) / "pessoas.json").read_text())["candidatos"][0]["id"] == "ca2"


def test_falha_no_primeiro_registro_preserva_cobertura_dos_restantes(tmp_path):
    class Quebrado:
        def consultar(self, alvo):
            raise OSError("nome privado")
    lote = tmp_path / "lote"
    with pytest.raises(ValueError, match="CNPJ"):
        fluxo.pesquisar(entrada(), config(tmp_path), {"cnpj": Quebrado()}, lote)
    primeira = json.loads((lote / cnj(1) / "consultas.json").read_text())
    segunda = json.loads((lote / cnj(2) / "consultas.json").read_text())
    assert any(q["estado"] == "interrompido" for q in primeira)
    assert {q["fonte"] for q in segunda if q["estado"] == "nao_consultado"} == {"CNPJ", "Hermes"}
    assert "nome privado" not in (lote / "relatorio.html").read_text()


def test_adaptador_oab_e_pendencia_sao_auditados_sem_repeticao(tmp_path):
    from guicredito.pessoas.oab import CadastroOAB, CaptchaOAB, URL_CADASTRO

    e = entrada()
    chamadas = []
    for caso in e.casos:
        caso["alvos"][0].update(papel="advogado", lado="desconhecido")
    def consulta(alvo):
        chamadas.append(alvo["id"])
        if alvo["id"] == "a1":
            raise CaptchaOAB
        return [{"nome": alvo["nome"], "oab": "234", "uf": "SP", "url": URL_CADASTRO, "data": "2026-11-23",
                 "dados_profissionais": "escritório fictício"}]

    pasta = tmp_path / "lote"
    for _ in range(2):
        dados = fluxo.pesquisar(e, config(tmp_path), {"oab": CadastroOAB(consulta)}, pasta)
    assert chamadas == ["a1", "a2"]
    a, b = dados["casos"]
    assert a["oab"][0]["motivo"] == "captcha" and b["oab"][0]["estado"] == "consultado"
    assert {r["fonte"]: r["estado"] for r in a["consultas"]}["OAB"] == "nao_verificado"
    assert {r["fonte"]: r["estado"] for r in b["consultas"]}["OAB"] == "consultado"
    assert not a["candidatos"] and b["candidatos"][0]["verificacao"] == "nao_verificado"
    assert b["evidencias"][0]["candidato_id"] == b["candidatos"][0]["id"]


def test_oab_indisponivel_persiste_falha_antes_do_proximo_alvo(tmp_path):
    from guicredito.pessoas.oab import CadastroOAB

    e = entrada()
    for caso in e.casos:
        caso["alvos"][0].update(papel="advogado", lado="desconhecido")
    vistos = []
    def falhar(alvo):
        vistos.append(alvo["id"])
        raise RuntimeError("sentinela privada")
    pasta = tmp_path / "lote"
    with pytest.raises(ValueError, match="OAB indisponível"):
        fluxo.pesquisar(e, config(tmp_path), {"oab": CadastroOAB(falhar)}, pasta)
    assert vistos == ["a1"]
    consultas = json.loads((pasta / cnj(1) / "consultas.json").read_text())
    assert any(r["fonte"] == "OAB" and r["estado"] == "interrompido" for r in consultas)
