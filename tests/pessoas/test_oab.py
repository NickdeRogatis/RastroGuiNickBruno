import pytest
from guicredito.pessoas.entrada import extrair_alvos
from guicredito.pessoas.oab import CadastroOAB, CaptchaOAB, consulta_oab, extrair_advogados, importar_manual


def test_papeis_explicitos_e_varios_advogados():
    partes = [
        ["Exeqte.", "BANCO EXEMPLO S.A. Advogado: ANA EXEMPLO (OAB 123456/SP), BIA EXEMPLO (OAB/SP 123.457)"],
        ["Advogado", "CAIO EXEMPLO"],
        ["Testemunha", "TERCEIRO EXEMPLO Advogado: TERCEIRA EXEMPLO (OAB 333/SP)"],
    ]
    publicacoes = ["ADV: ANA EXEMPLO (OAB 123456/SP); DORA EXEMPLO (OAB 2345/RJ)"]
    alvos = extrair_alvos(partes, publicacoes, {"processo": "caso1", "cidade": "Cidade Exemplo"})
    por_nome = {a["nome"]: a for a in alvos}
    assert set(por_nome) == {"ANA EXEMPLO", "BIA EXEMPLO", "CAIO EXEMPLO", "DORA EXEMPLO", "BANCO EXEMPLO S.A."}
    assert len(alvos) == len(por_nome)
    assert por_nome["ANA EXEMPLO"]["lado"] == "credor"
    assert por_nome["ANA EXEMPLO"]["oab"] == "123456"
    assert por_nome["BIA EXEMPLO"]["oab"] == "123457"
    assert por_nome["ANA EXEMPLO"]["origem"]["uf"] == "SP"
    assert por_nome["CAIO EXEMPLO"]["lado"] == "desconhecido" and not por_nome["CAIO EXEMPLO"]["oab"]
    assert por_nome["DORA EXEMPLO"]["uf"] == "RJ"


def test_ignora_mencoes_e_preserva_homonimos():
    partes = [["Advogado do executado", "JOÃO EXEMPLO (OAB 2456/SP)"]]
    publicacoes = [
        "A testemunha declarou que sua advogada: TERCEIRA EXEMPLO.", "ADV: JOÃO EXEMPLO (OAB 2456/RJ)",
        "DESPACHO: ouça-se TERCEIRO EXEMPLO.", "Advogada da testemunha: TERCEIRA EXEMPLO",
    ]
    adv = extrair_advogados(partes, publicacoes)
    assert [(a["nome"], a["uf"], a["lado"]) for a in adv] == [
        ("JOÃO EXEMPLO", "SP", "devedor"), ("JOÃO EXEMPLO", "RJ", "desconhecido")]
    assert adv[0]["id"] != adv[1]["id"]


def test_mesma_inscricao_nos_dois_lados_exige_conferencia():
    adv = extrair_advogados([["Advogado do autor", "ANA EXEMPLO (OAB 123/SP)"],
                             ["Advogado do réu", "ANA EXEMPLO (OAB 123/SP)"]], [])
    assert len(adv) == 1 and adv[0]["lado"] == "desconhecido"


def test_captcha_esperado_e_inesperado_e_falha_central():
    a, b = extrair_advogados([["Advogado", "ANA EXEMPLO (OAB 123/SP)"], ["Advogada", "BIA EXEMPLO"]], [])
    padrao = consulta_oab(a)
    assert padrao["alvo_id"] == a["id"] and padrao["nome"] == a["nome"] and padrao["oab"] == "123"
    assert padrao["url"].startswith("https://cna.oab.org.br/") and padrao["estado"] == "pendente"
    vistos = []
    def consulta(alvo):
        vistos.append(alvo["id"])
        if len(vistos) == 1:
            raise CaptchaOAB
        return []
    registro = CadastroOAB(consulta)
    assert registro.consultar(a)[0]["motivo"] == "captcha"
    assert registro.consultar(b) == [] and vistos == [a["id"], b["id"]]
    assert CadastroOAB(lambda _: {"estado": "captcha"}).consultar(a)[0]["estado"] == "pendente"
    with pytest.raises(RuntimeError):
        CadastroOAB(lambda _: {"estado": "indisponivel"}).consultar(a)


def test_registro_manual_e_automatico_sao_distintos():
    alvo = extrair_advogados([["Advogado", "JOÃO EXEMPLO"]], [])[0]
    registro = dict(alvo_id=alvo["id"], nome=alvo["nome"], oab="00123", uf="SP",
                    url="https://cna.oab.org.br/", data="2026-11-23",
                    dados_profissionais={"email_profissional": "exemplo@example.test"})
    candidato = importar_manual(registro)
    assert candidato["verificacao"] == "manual" and candidato["oab"] == "00123"
    assert candidato["dados_profissionais"] == registro["dados_profissionais"]
    assert candidato["evidencias"][0]["tipo"] == "manual"
    assert "confirmado" not in candidato and "autorizar_consulta_paga" not in candidato
    automatico = CadastroOAB(lambda _: [registro]).consultar(alvo)[0]
    assert automatico["verificacao"] == "nao_verificado"
    assert automatico["evidencias"][0]["tipo"] == "registro"
    for invalido in (dict(data="2026-02-31"), dict(nome=""), dict(uf="XX"), dict(oab="*"),
                     dict(dados_profissionais={}), dict(url="javascript:alert(1)")):
        with pytest.raises(ValueError):
            importar_manual(registro | invalido)


def test_nao_pesquisa_advogado_de_terceiro_mencionado_na_publicacao():
    assert extrair_advogados([], ["Testemunha: TERCEIRO EXEMPLO; Advogada: TERCEIRA EXEMPLO (OAB 345/SP)"]) == []
