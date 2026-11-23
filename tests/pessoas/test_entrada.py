import hashlib
import json
from pathlib import Path

import pytest
from openpyxl import Workbook

from guicredito.aprofundamento.cnj import formatar
from guicredito.pessoas.entrada import ler_entrada


def cnj(i):
    base = f"{i:07d}20208260001"
    return f"{i:07d}{98 - int(base + '00') % 97:02d}20208260001"


@pytest.fixture
def entradas(tmp_path):
    selecao = tmp_path / "selecao.json"
    pasta = tmp_path / "aprofundamento"
    planilha = tmp_path / "exemplo.xlsx"
    casos = [{"numero_processo": cnj(i), "posicao_original": i, "pontuacao_original": 61-i} for i in (1, 2)]
    selecao.write_text(json.dumps({"versao": 1, "casos": casos}))
    evidencia = pasta / cnj(1) / "consulta.html.txt"
    evidencia.parent.mkdir(parents=True)
    evidencia.write_text("capa fictícia")
    resultado = {
        **casos[0], "status": "coletado",
        "campos": {"classe": "Cumprimento de sentença", "processo_principal_texto": cnj(3)},
        "partes_linhas": [
            ["Exeqte.", "BANCO EXEMPLO S.A."], ["Executado", "JOÃO EXEMPLO"],
            ["Fiadora", "FIADORA EXEMPLO"], ["Coobrigado", "COOBRIGADO EXEMPLO"],
            ["Avalista", "AVALISTA EXEMPLO"], ["Testemunha", "TERCEIRO EXEMPLO"],
        ],
        "evidencias": [{"arquivo": evidencia.name, "sha256": hashlib.sha256(evidencia.read_bytes()).hexdigest()}],
    }
    (evidencia.parent / "resultado.json").write_text(json.dumps(resultado))
    # The principal is neither an input nor a new research target.
    (pasta / cnj(3)).mkdir()
    (pasta / cnj(3) / "resultado.json").write_text("JSON deliberadamente inválido")
    wb = Workbook()
    ws = wb.active
    ws.title = "Casos"
    ws.append(["#", "Pontos", "Processo", "Credor", "Devedor", "Comarca", "Classe"])
    ws.append([1, 60, formatar(cnj(1)), "BANCO EXEMPLO S.A.", "JOÃO EXEMPLO [avalista/sócio]", "Cidade Exemplo"])
    ws.append([2, 59, formatar(cnj(2)), "CREDORA EXEMPLO", "não identificado", "Cidade Exemplo"])
    ws.append([3, 58, formatar(cnj(3)), "OUTRO EXEMPLO", "JOÃO EXEMPLO"])
    pub = wb.create_sheet("Publicações")
    pub.append(["Processo", "Texto", "Data"])
    pub.append([formatar(cnj(2)), "EXECUTADO: DEVEDOR EXEMPLO DESPACHO: Ouça-se TERCEIRO EXEMPLO.", "2026-11-10"])
    pub.append([formatar(cnj(4)), "EXECUTADO: JOÃO EXEMPLO DESPACHO: Ouça-se TERCEIRO EXEMPLO.", "2026-11-11"])
    wb.save(planilha)
    return selecao, pasta, planilha


def test_alvos_selecionados_e_homonimos(entradas):
    selecao, pasta, planilha = entradas
    arquivos = [selecao, planilha, *pasta.rglob("*.json"), *pasta.rglob("*.txt")]
    antes = [a.read_bytes() for a in arquivos]
    entrada = ler_entrada(*entradas)
    primeiro, segundo = entrada.casos
    assert [c["processo"] for c in entrada.casos] == [cnj(1), cnj(2)]
    assert primeiro["pontuacao_original"] == 60
    partes = {(a["papel"], a["tipo"], a["nome"]) for a in entrada.alvos}
    assert partes == {
        ("devedor", "PF", n) for n in ("JOÃO EXEMPLO", "FIADORA EXEMPLO", "COOBRIGADO EXEMPLO", "AVALISTA EXEMPLO", "DEVEDOR EXEMPLO")
    } | {("credor", "PJ", "BANCO EXEMPLO S.A."), ("credor", "PF", "CREDORA EXEMPLO")}
    assert "capa ausente" in segundo["limitacoes"]
    achados = primeiro["candidatos"]
    assert {x["processo_referenciado"] for x in achados} == {cnj(3), cnj(4)}
    assert all(x["confianca"] == "baixa" and x["verificacao"] == "nao_verificado" for x in achados)
    assert len(primeiro["evidencias"]) == 2
    assert all(x["alvo_id"] in {a["id"] for a in primeiro["alvos"]} for x in achados)
    assert [a.read_bytes() for a in arquivos] == antes
    assert ler_entrada(*entradas).hashes == entrada.hashes


@pytest.mark.parametrize("erro", ["11 casos", "duplicado", "resultado", "estado", "evidencia", "traversal", "manifesto", "score", "versao"])
def test_entrada_incompativel(entradas, erro):
    selecao, pasta, _ = entradas
    arquivo = pasta / cnj(1) / "resultado.json"
    resultado = json.loads(arquivo.read_text())
    sel = json.loads(selecao.read_text())
    if erro == "11 casos":
        sel["casos"] *= 6
    elif erro == "duplicado":
        sel["casos"][1] = sel["casos"][0]
    elif erro == "resultado":
        resultado["numero_processo"] = cnj(2)
    elif erro == "estado":
        resultado["status"] = "processo_divergente"
    elif erro == "evidencia":
        (arquivo.parent / "consulta.html.txt").write_text("alterada")
    elif erro == "traversal":
        resultado["evidencias"][0]["arquivo"] = "../selecao.json"
    elif erro == "manifesto":
        (pasta / "selecao.json").write_text(json.dumps({**sel, "casos": sel["casos"][:1]}))
    elif erro == "score":
        sel["casos"][1]["pontuacao_original"] = 90
    elif erro == "versao":
        sel["versao"] = 8
    selecao.write_text(json.dumps(sel))
    arquivo.write_text(json.dumps(resultado))
    with pytest.raises(ValueError):
        ler_entrada(*entradas)


def test_cabecalho_preserva_nome_original_e_exige_limite_entre_partes_e_texto():
    from guicredito.pessoas.entrada import extrair_alvos
    publicacoes = [
        "EXECUTADO: João Exemplo foi até a casa de Terceiro Exemplo.",
        "Exequente: Banco Exemplo S.A. EXECUTADO: João Exemplo DESPACHO: Ouça-se Terceiro Exemplo.",
        "EXECUTADO: JOÃO EXEMPLO; Terceiro mencionado na petição.",
    ]
    alvos = extrair_alvos([], publicacoes, {"processo": "ficcao"})
    assert {a["nome"] for a in alvos} == {"Banco Exemplo S.A.", "João Exemplo"}


def test_celula_com_documentos_e_advogado_qualificado():
    from guicredito.pessoas.entrada import extrair_alvos
    partes = [["Exeqte.", "BANCO EXEMPLO S.A. CNPJ: 00.000.001/0001-36 Advogado do exequente: ANA EXEMPLO"]]
    alvos = extrair_alvos(partes, [], {"processo": "ficcao"})
    assert [(a["nome"], a["papel"]) for a in alvos] == [("BANCO EXEMPLO S.A.", "credor"), ("ANA EXEMPLO", "advogado")]
    assert alvos[0]["cnpj"] == "00000001000136"


def test_comarca_do_processo_nao_atribui_cidade_a_pessoas(entradas):
    entrada = ler_entrada(*entradas)
    assert entrada.casos[0].get("comarca") == "Cidade Exemplo"
    assert all(not alvo.get("cidade") for alvo in entrada.alvos)
