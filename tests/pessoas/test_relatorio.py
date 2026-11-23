import pytest

from guicredito.pessoas.relatorio import projetar_revisao, renderizar, renderizar_revisao


def caso_sintetico():
    return {
        "processo": "0000001-00.2000.8.26.0001", "rotulo": "Caso 01", "fase": "execução",
        "alvos": [{"id": "alvo-sentinela", "papel": "devedor", "tipo": "PF", "nome": "JOÃO EXEMPLO"}],
        "candidatos": [{"id": "c1", "alvo_id": "alvo-sentinela", "nome": "JOÃO EXEMPLO",
                       "fonte": "CNPJ", "empresa": "Empresa Particular", "capital_social": "1234567,89"},
                      {"id": "c2", "alvo_id": "alvo-sentinela", "nome": "JOÃO EXEMPLO",
                       "fonte": "CNPJ", "empresa": "Empresa Confidencial", "capital_social": "8765432,10"}],
        "evidencias": [{"id": "e1", "candidato_id": "c1", "categoria": "participação empresarial",
                        "estado": "registro", "fonte": "CNPJ", "trecho": "<script>sigiloso</script>",
                        "url": "https://site-pessoal.example", "data": "2032-12-31"},
                       {"id": "e2", "candidato_id": "c2", "categoria": "participação empresarial",
                        "estado": "registro", "fonte": "CNPJ", "url": "javascript:alert(1)"}],
        "oab": [{"id": "o1", "alvo_id": "alvo-sentinela", "oab": "OAB999999", "estado": "captcha"}],
        "limitacoes": ["Rua Sentinela 456", "contato@exemplo.test", "11987650000"],
        "contatos": [{"candidato_id": "c1", "origem": "pública", "tipo": "e-mail", "valor": "privado@teste.example"}],
    }


def test_resumo_do_revisor():
    caso = caso_sintetico()
    dados = {"lote": "lote-secreto", "casos": [caso]}
    decisoes = {"candidatos": {"c1": {"Confirmado": "sim", "CPF": "01234567890"}},
                "oab": {"o1": {"Dados profissionais conferidos": "Escritório Exemplo",
                               "Data da conferência": "2026-11-23"}}}
    fichas = projetar_revisao(dados, decisoes)
    html = renderizar_revisao(fichas)
    assert "Caso 01" in html and "execução" in html
    assert "vínculo empresarial pendente de confirmação" in html
    assert "participação empresarial" in html and "capital social declarado" in html
    sentinelas = [caso["processo"], "lote-secreto", "alvo-sentinela", "JOÃO EXEMPLO", "Empresa Particular",
                  "Empresa Confidencial", "OAB999999", "01234567890", "Rua Sentinela 456", "11987650000",
                  "contato@exemplo.test", "privado@teste.example", "site-pessoal.example", "2032-12-31",
                  "sigiloso", "1234567,89", "8765432,10", "Escritório Exemplo", "2026-11-23"]
    for valor in sentinelas:
        assert valor.encode() not in html.encode()
        assert valor not in repr(fichas)
    for tag in ("href=", "src=", "javascript:", "<script", "<!--"):
        assert tag not in html
    privado = renderizar(dados, decisoes)
    assert "JOÃO EXEMPLO" in privado and "Escritório Exemplo" in privado
    assert "2026-11-23" in privado and "captcha" in privado
    assert "<script>" not in privado and "&lt;script&gt;" in privado
    assert "javascript:" not in privado and 'href="https://site-pessoal.example"' in privado


@pytest.mark.parametrize(("valor", "esperado"), [
    ("99999,99", "abaixo de 100 mil"), ("100000", "de 100 mil a menos de 1 milhão"),
    ("999999,99", "de 100 mil a menos de 1 milhão"), ("1000000", "a partir de 1 milhão"),
    (None, "capital não informado"),
])
def test_faixas_so_para_o_socio_confirmado(valor, esperado):
    caso = caso_sintetico()
    caso["candidatos"][0]["capital_social"] = valor
    dados = {"lote": "lote", "casos": [caso]}
    pendente = renderizar_revisao(projetar_revisao(dados, {}))
    assert "vínculo empresarial pendente de confirmação" in pendente
    assert "capital social declarado" not in pendente
    confirmado = renderizar_revisao(projetar_revisao(dados, {"candidatos": {"c1": {"Confirmado": "sim"}}}))
    assert "vínculo empresarial pendente de confirmação" in confirmado and esperado in confirmado
    if esperado != "a partir de 1 milhão":
        assert "a partir de 1 milhão" not in confirmado


def test_sem_registro_associado_ou_somente_snippet():
    caso = caso_sintetico()
    caso["fase"] = "fase privada com endereço"
    caso["evidencias"] = [caso["evidencias"][1], {"id": "e3", "candidato_id": "c1", "categoria": "emprego",
                         "estado": "não verificado", "trecho": "Página de pesquisa"}]
    dados = {"lote": "lote", "casos": [caso]}
    decisoes = {"candidatos": {"c1": {"Confirmado": "sim"}}}
    html = renderizar_revisao(projetar_revisao(dados, decisoes))
    assert "capital social declarado" not in html and "emprego" not in html
    assert "fase privada" not in html
    caso["evidencias"][-1]["estado"] = "verificado"
    assert "emprego" in renderizar_revisao(projetar_revisao(dados, decisoes))


def test_rotulo_nunca_recebe_texto_livre():
    caso = caso_sintetico()
    caso["rotulo"] = "Caso 01 - nome da parte"
    with pytest.raises(ValueError):
        projetar_revisao({"lote": "lote", "casos": [caso]}, {})


def test_ordem_do_resumo_independe_do_ranking_e_omite_papeis_de_terceiros():
    primeiro = dict(caso_sintetico(), rotulo="Caso 02")
    segundo = caso_sintetico()
    segundo["alvos"][0].update(papel="advogado", lado="devedor")
    d = {"candidatos": {"c1": {"Confirmado": "sim"}}}
    fichas = projetar_revisao({"lote": "lote", "casos": [primeiro, segundo]}, d)
    assert [f.rotulo for f in fichas] == ["Caso 01", "Caso 02"]
    assert not fichas[0].indicios


def test_registro_conferido_e_snippet_nao_tem_o_mesmo_peso():
    caso = caso_sintetico()
    caso["evidencias"][0].update(estado="nao_verificado", tipo="registro")
    caso["evidencias"].extend([
        {"id": "e3", "candidato_id": "c1", "categoria": "processo", "tipo": "página", "estado": "consultado"},
        {"id": "e4", "candidato_id": "c1", "categoria": "emprego", "tipo": "snippet", "estado": "consultado"},
    ])
    dados = {"lote": "lote", "casos": [caso]}
    decisoes = {"candidatos": {"c1": {"Confirmado": "sim"}}}
    html = renderizar_revisao(projetar_revisao(dados, decisoes))
    assert "outro processo" in html and "participação empresarial" in html and "emprego" not in html


def test_privado_traz_indicios_conflitos_situacao_da_empresa():
    caso = caso_sintetico()
    caso["candidatos"][0].update(indicios={"cidade": "Cidade Exemplo"}, conflitos=["cidade divergente"],
                                  situacao="BAIXADA", cnpj="00000001000217")
    html = renderizar({"lote": "lote", "casos": [caso]}, {})
    for valor in ("Cidade Exemplo", "cidade divergente", "BAIXADA", "00000001000217"):
        assert valor in html


def test_pendencia_oab_some_apenas_apos_conferencia_datada():
    caso = caso_sintetico()
    caso["oab"][0].update(estado="pendente", motivo="captcha")
    dados = {"lote": "lote", "casos": [caso]}
    decisao = {"oab": {"o1": {"Data da conferência": "2026-11-23"}}}
    assert "conferência manual pendente" in renderizar_revisao(projetar_revisao(dados, decisao))
    decisao["oab"]["o1"]["OAB/UF conferida"] = "SP/1234"
    assert "conferência manual pendente" not in renderizar_revisao(projetar_revisao(dados, decisao))
