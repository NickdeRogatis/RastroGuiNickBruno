from copy import deepcopy
from datetime import date

import pytest
from openpyxl import load_workbook

from guicredito.pessoas.planilha import gravar_planilha, ler_decisoes


@pytest.fixture
def dados_excel():
    cnj = "0000001-00.2000.8.26.0001"
    alvo = {"id": "a1", "nome": "JOÃO EXEMPLO", "papel": "devedor", "tipo": "PF", "processo": cnj}
    caso = {
        "processo": cnj, "rotulo": "Caso 01", "fase": "execução", "alvos": [alvo],
        "candidatos": [
            {"id": "c1", "alvo_id": "a1", "nome": "JOÃO EXEMPLO", "fonte": "CNPJ",
             "empresa": "Empresa Um", "capital_social": "100000,00"},
            {"id": "c2", "alvo_id": "a1", "nome": "JOÃO EXEMPLO", "fonte": "CNPJ",
             "empresa": "Empresa Dois", "capital_social": "1000,00"},
        ],
        "evidencias": [{"id": "e1", "candidato_id": "c1", "categoria": "participação empresarial",
                        "trecho": "=2+3", "url": "https://fonte.example"}],
        "provedor": [{"id": "p1", "candidato_id": "c1", "nome": "JOÃO EXEMPLO", "indicios": {"cidade": "Cidade A"}},
                     {"id": "p2", "candidato_id": "c1", "nome": "JOÃO EXEMPLO", "indicios": {"cidade": "Cidade B"}}],
        "oab": [{"id": "o1", "alvo_id": "a2", "nome": "Advogado Exemplo", "oab": "12345",
                 "uf": "SP", "url": "https://cadastro.example", "estado": "captcha"}],
    }
    caso["alvos"].append({"id": "a2", "processo": cnj, "papel": "advogado", "tipo": "PF", "nome": "Advogado Exemplo"})
    return {"lote": "lote-fixture", "casos": [caso]}


def editar(aba, coluna, valor, linha=2):
    titulo = next(c for c in aba[1] if c.value == coluna)
    aba.cell(linha, titulo.column).value = valor


def test_leituras_manuais(tmp_path, dados_excel):
    caminho = tmp_path / "pessoas.xlsx"
    gravar_planilha(caminho, dados_excel, {})
    decisoes = ler_decisoes(caminho, dados_excel)
    assert decisoes["candidatos"]["c1"] == {"Confirmado": "", "CPF": "", "Autorizar consulta paga": ""}
    wb = load_workbook(caminho)
    assert wb.sheetnames == ["Candidatos", "Provedor", "Evidências", "Contatos", "Casos", "Vínculos", "OAB", "Como ler"]
    assert wb["Evidências"]["G2"].value == "=2+3"
    assert wb["Evidências"]["G2"].data_type == "s"
    editar(wb["Candidatos"], "Confirmado", "sim")
    editar(wb["Candidatos"], "CPF", "01234567890")
    editar(wb["Candidatos"], "Autorizar consulta paga", "sim")
    editar(wb["Provedor"], "Confirmado", "sim", 3)
    editar(wb["Casos"], "Descartar", "sim")
    editar(wb["OAB"], "OAB/UF conferida", "SP/12345")
    editar(wb["OAB"], "Dados profissionais conferidos", "Escritório de teste")
    editar(wb["OAB"], "Data da conferência", date(2026, 11, 23))
    for nome in ("Candidatos", "Vínculos", "Provedor"):
        aba = wb[nome]
        linhas = list(aba.values)[1:]
        aba.delete_rows(2, len(linhas))
        for linha in reversed(linhas):
            aba.append(linha)
    wb.save(caminho)
    lidas = ler_decisoes(caminho, dados_excel)
    assert lidas["candidatos"]["c1"] == {"Confirmado": "sim", "CPF": "01234567890", "Autorizar consulta paga": "sim"}
    assert lidas["candidatos"]["c2"]["Confirmado"] == ""
    assert lidas["casos"][dados_excel["casos"][0]["processo"]]["Descartar"] == "sim"
    assert lidas["provedor"] == {"p1": {"Confirmado": ""}, "p2": {"Confirmado": "sim"}}
    assert lidas["oab"]["o1"] == {"OAB/UF conferida": "SP/12345", "Dados profissionais conferidos": "Escritório de teste",
                                  "Data da conferência": "2026-11-23"}
    novos = deepcopy(dados_excel)
    novos["casos"][0]["evidencias"].append({"id": "e2", "candidato_id": "c2", "categoria": "participação empresarial"})
    gravar_planilha(caminho, novos, lidas)
    assert ler_decisoes(caminho, novos) == lidas


@pytest.mark.parametrize(("aba", "coluna", "valor"), [
    ("Candidatos", "Candidato ID", "c2"), ("Candidatos", "Candidato ID", "desconhecido"),
    ("Candidatos", "Alvo ID", "a2"), ("Candidatos", "Nome", "OUTRA PESSOA"),
    ("Casos", "Processo", "0000002-00.2000.8.26.0001"), ("Vínculos", "Candidato ID", "c2"),
    ("OAB", "Alvo ID", "a1"), ("Provedor", "Candidato ID de origem", "c2"),
    ("Candidatos", "Confirmado", "talvez"), ("Casos", "Descartar", "não"),
    ("Candidatos", "CPF", 1234567890), ("Candidatos", "Confirmado", '=IF(1,"sim","")'),
    ("Candidatos", "CPF", "01234567891"), ("OAB", "Data da conferência", "inexistente"),
])
def test_recusa_edicoes_invalidas(tmp_path, dados_excel, aba, coluna, valor):
    caminho = tmp_path / "pessoas.xlsx"
    gravar_planilha(caminho, dados_excel, {})
    wb = load_workbook(caminho)
    editar(wb[aba], coluna, valor)
    wb.save(caminho)
    original = caminho.read_bytes()
    with pytest.raises(ValueError):
        ler_decisoes(caminho, dados_excel)
    assert caminho.read_bytes() == original


def test_exige_linhas_e_confirmacao_unica_do_provedor(tmp_path, dados_excel):
    caminho = tmp_path / "pessoas.xlsx"
    gravar_planilha(caminho, dados_excel, {})
    wb = load_workbook(caminho)
    editar(wb["Provedor"], "Confirmado", "sim", 2)
    editar(wb["Provedor"], "Confirmado", "sim", 3)
    wb.save(caminho)
    with pytest.raises(ValueError):
        ler_decisoes(caminho, dados_excel)
    editar(wb["Provedor"], "Confirmado", None, 2)
    wb["Vínculos"].delete_rows(3)
    wb.save(caminho)
    with pytest.raises(ValueError):
        ler_decisoes(caminho, dados_excel)


def test_outro_lote_e_arquivo_aberto(tmp_path, dados_excel):
    caminho = tmp_path / "pessoas.xlsx"
    gravar_planilha(caminho, dados_excel, {})
    original = caminho.read_bytes()
    with pytest.raises(ValueError):
        ler_decisoes(caminho, {**dados_excel, "lote": "outro"})
    (tmp_path / "~$pessoas.xlsx").touch()
    with pytest.raises((ValueError, OSError)):
        ler_decisoes(caminho, dados_excel)
    with pytest.raises((ValueError, OSError)):
        gravar_planilha(caminho, dados_excel, {})
    assert caminho.read_bytes() == original


def test_pendencia_oab_identifica_motivo_e_preserva_origem(tmp_path, dados_excel):
    dados_excel["casos"][0]["oab"][0].update(estado="pendente", motivo="captcha")
    caminho = tmp_path / "pessoas.xlsx"
    gravar_planilha(caminho, dados_excel, {})
    ws = load_workbook(caminho)["OAB"]
    assert "captcha" in ws["E2"].value and "pendente" in ws["E2"].value
    assert ws["D2"].value == "https://cadastro.example"
