import hashlib

import pytest

from guicredito.pessoas.evidencias import confianca, pesquisar_web, salvar_recorte, validar_achado
from guicredito.pessoas.hermes import ClienteHermes, ResultadoBusca, RetornoBusca
from guicredito.pessoas.http import Pagina, PoliticaIndisponivel
from guicredito.pessoas.config import carregar_config

NOME = "JOÃO EXEMPLO"
ALVO = dict(id="alvo-a", processo="ficticio", papel="devedor", tipo="PF",
            nome=NOME, cidade="Cidade Exemplo", empregador="Empresa Exemplo", lado="devedor",
            cpf="12345678909", telefone="99999-9999", texto="TESTEMUNHA EXEMPLO")
URL = "https://example.test/fonte"
SOCIAL = "https://www.linkedin.com/in/joaoexemplo"
DATA = "2026-01-01T00:00:00+00:00"


def achado(url=URL, trecho="João Exemplo", **extra):
    return dict(nome=NOME, url=url, trecho=trecho, categoria="identidade", indicios=extra)


class Hermes:
    def __init__(self, resultados, propostas):
        self.resultados = resultados
        self.propostas = propostas
        self.pesquisas = []
        self.leituras = []

    def exigir_politica(self):
        pass

    def buscar(self, consulta):
        self.pesquisas.append(consulta)
        return RetornoBusca(self.resultados, "resp_teste", "call_teste", "gratuito")

    def propor(self, texto, alvo):
        self.leituras.append((texto, alvo))
        return self.propostas.get(alvo["url"], [])


class Paginas:
    def __init__(self, paginas):
        self.paginas = paginas
        self.chamadas = []

    def baixar(self, url):
        self.chamadas.append(url)
        return self.paginas[url]


def test_grounding_normalizado_e_limites_de_fonte():
    resultados = [ResultadoBusca(URL, "titulo", "João Exemplo em outra cidade")]
    pagina = Pagina(URL, "João  Exemplo na EMPRESA EXEMPLAR.", "consultado", data=DATA)
    assert validar_achado(achado(url=URL + "/inventado"), resultados, {URL: pagina}) is None
    assert validar_achado(achado(trecho="João Exemplo em outra cidade"), resultados, {URL: pagina}) is None
    assert validar_achado(achado(trecho="João Exemplo milionário"), resultados, {URL: pagina}) is None
    ev = validar_achado(achado(trecho="JOAO EXEMPLO na empresa exemplar"), resultados, {URL: pagina})
    assert ev["tipo"] == "pagina" and ev["data"] == DATA
    bloqueio = Pagina(URL, "", "nao_consultado", "HTTP 403", DATA)
    ev = validar_achado(achado(trecho=resultados[0].snippet), resultados, {URL: bloqueio})
    assert ev["tipo"] == "snippet" and ev["estado"] == "nao_verificado"
    assert validar_achado(achado(), resultados, {}) is None


def test_confianca_com_indicios_independentes():
    cidade = {"campo": "cidade", "valor": "Cidade Exemplo"}
    trabalho = {"campo": "empregador", "valor": "Empresa Exemplo"}
    assert confianca([], []) == "baixa"
    assert confianca([cidade, cidade], []) == "média"
    assert confianca([cidade, trabalho], []) == "alta"
    assert confianca([cidade, trabalho], ["divergência"]) == "baixa"


def test_consulta_minima_rastro_de_todos_os_candidatos_e_recortes(tmp_path):
    trecho = "JOÃO EXEMPLO, Cidade Exemplo, Empresa Exemplo."
    outro = "João Exemplo, Outra Cidade."
    resultados = [ResultadoBusca(URL, "Referência profissional", "apenas snippet")]
    hermes = Hermes(resultados, {URL: [
        achado(trecho=trecho, cidade="Cidade Exemplo", empregador="Empresa Exemplo"),
        achado(trecho=outro, cidade="Outra Cidade", empregador="inventado"),
        achado(trecho="João Exemplo, alegação falsa"),
        achado() | {"nome": "TERCEIRO EXEMPLO"},
    ]})
    http = Paginas({URL: Pagina(URL, trecho + " " + outro, "consultado", data=DATA)})
    resp = pesquisar_web(ALVO, hermes, http)
    assert len(hermes.pesquisas) == 1 and NOME in hermes.pesquisas[0]
    assert all(x not in hermes.pesquisas[0] for x in ("12345678909", "99999", "TESTEMUNHA", "ficticio"))
    assert len(hermes.leituras) == len(http.chamadas) == 1
    assert not (hermes.leituras[0][1].keys() & {"cpf", "processo", "telefone", "texto"})
    candidatos = resp["candidatos"]
    assert len({c["id"] for c in candidatos}) == len(candidatos) == 2
    assert [c["confianca"] for c in candidatos] == ["alta", "baixa"]
    assert not candidatos[1].get("empregador")
    assert all(c["verificacao"] == "nao_verificado" for c in candidatos)
    consulta, pagina = resp["consultas"]
    assert (consulta["id_resposta"], consulta["id_chamada"], consulta["backend"], consulta["limite"]) == (
        "resp_teste", "call_teste", "gratuito", 3)
    assert pagina["data"] == DATA and pagina["estado"] == "consultado"
    for c, e in zip(candidatos, resp["evidencias"], strict=True):
        assert e["id"] in c["evidencias_ids"] and e["candidato_id"] == c["id"]
        ev = salvar_recorte(tmp_path, e, e["trecho"])
        assert hashlib.sha256((tmp_path / ev["arquivo"]).read_bytes()).hexdigest() == e["sha256"]


def test_pagina_social_bloqueada_uma_vez_e_proximo_link_processado():
    social = ResultadoBusca(SOCIAL, "JOÃO EXEMPLO", "João Exemplo. Post mostrando fotos de família.")
    outros = [ResultadoBusca(URL, NOME, NOME), ResultadoBusca("https://instagram.com/p/exemplo", NOME, NOME)]
    hermes = Hermes([social, social] + outros, {URL: [achado()]})
    http = Paginas({SOCIAL: Pagina(SOCIAL, "", "nao_consultado", "login ou captcha", DATA),
                    URL: Pagina(URL, NOME, "consultado", data=DATA)})
    resp = pesquisar_web(ALVO, hermes, http)
    assert http.chamadas == [SOCIAL, URL] and [r[1]["url"] for r in hermes.leituras] == [URL]
    assert all(c["verificacao"] == "nao_verificado" for c in resp["candidatos"])
    assert {e["tipo"] for e in resp["evidencias"]} == {"pagina", "snippet"}
    assert "família" not in str(resp)
    assert any(c["estado"] == "nao_consultado" and c["url"] == SOCIAL for c in resp["consultas"])


def test_nome_ausente_no_snippet_preserva_link_sem_inventar_confirmacao():
    hermes = Hermes([ResultadoBusca(URL, "Índice público", "")], {})
    http = Paginas({URL: Pagina(URL, "", "nao_consultado", "HTTP 429", DATA)})
    resp = pesquisar_web(ALVO, hermes, http)
    assert resp["evidencias"][0]["url"] == URL and resp["evidencias"][0]["tipo"] == "link"
    assert not resp["evidencias"][0]["trecho"] and not hermes.leituras


def test_modo_registros_e_alvos_excluidos():
    assert pesquisar_web(ALVO, None, None)["consultas"][0]["estado"] == "nao_configurado"
    cliente = Hermes([], {})
    for alteracao in [{"tipo":"PJ"}, {"papel":"testemunha"}, {"nome":"JOÃO 12345678909 EXEMPLO"}]:
        pesquisar_web(ALVO | alteracao, cliente, Paginas({}))
    assert not cliente.pesquisas


def test_politica_ausente_nao_envia_nome(tmp_path):
    cfg = carregar_config(tmp_path / ".env", {"PESSOAS_BUSCA":"hermes", "PESSOAS_HERMES_KEY":"teste",
                                              "PESSOAS_HERMES_MODELO":"hermes-agent"})
    with pytest.raises(PoliticaIndisponivel):
        pesquisar_web(ALVO, ClienteHermes(cfg), Paginas({}))


def test_despachante_em_memoria_nega_antes_do_efeito(tmp_path):
    cfg = carregar_config(tmp_path / ".env", {"PESSOAS_BUSCA":"hermes", "PESSOAS_HERMES_KEY":"teste",
                                              "PESSOAS_HERMES_MODELO":"hermes-agent"})
    efeitos = []
    class Despachante:
        def exigir_politica(self):
            pass

        def enviar_restrito(self, url, payload, *, modo, argumentos):
            # Simulação do contrato do servidor. Só uma rota gratuita, no modo busca,
            # aceita exatamente os argumentos pré-autorizados para o turno.
            permitida = modo == "busca"
            for ferramenta, args, rota in [
                ("web_search", {"query":"TERCEIRO EXEMPLO","limit":3}, "gratuita"),
                ("web_extract", argumentos, "gratuita"), ("terminal", argumentos, "gratuita"),
                ("web_search", argumentos, "paga"), ("web_search", argumentos, "gratuita"),
                ("web_search", argumentos, "gratuita")]:
                if permitida and ferramenta == "web_search" and args == argumentos and rota == "gratuita":
                    efeitos.append((modo, ferramenta, args, rota))
                    permitida = False
            if modo == "busca":
                import json
                return {"status":"completed","id":"resp_teste","output":[
                    {"type":"function_call","call_id":"call_teste","status":"completed",
                     "name":"web_search","arguments":json.dumps(argumentos)},
                    {"type":"function_call_output","call_id":"call_teste","status":"completed",
                     "output":'{"success":true,"data":{"web":[]}}'}]}
            return {"status":"completed","id":"resp_ler","output":[
                {"type":"message","role":"assistant","content":[{"type":"output_text","text":"[]"}]}]}
    cliente = ClienteHermes(cfg, Despachante())
    cliente.buscar('"JOÃO EXEMPLO" profissional')
    cliente.propor("João Exemplo", dict(nome=NOME, papel="devedor", url=URL))
    assert efeitos == [("busca", "web_search", {"query":'"JOÃO EXEMPLO" profissional', "limit":3}, "gratuita")]


def test_contato_publico_so_em_pagina_de_credor_ou_advogado():
    trecho = "JOÃO EXEMPLO, contato profissional joao@example.test"
    proposta = achado(trecho=trecho) | {"categoria":"contato_profissional"}
    for papel in ("advogado", "credor", "devedor"):
        hermes = Hermes([ResultadoBusca(URL, "Página profissional", "")], {URL: [proposta]})
        http = Paginas({URL: Pagina(URL, trecho, "consultado", data=DATA)})
        resp = pesquisar_web(ALVO | {"papel":papel}, hermes, http)
        if papel == "devedor":
            assert not resp["contatos"] and "joao@example.test" not in str(resp)
        else:
            assert [(c["tipo"], c["valor"], c["data_fonte"]) for c in resp["contatos"]] == [
                ("email", "joao@example.test", DATA)]


def test_snippets_diferentes_da_mesma_url_boletim_de_busca():
    resultados = [ResultadoBusca(URL, "Página profissional", "João Exemplo de Cidade Exemplo."),
                  ResultadoBusca(URL, "Página profissional", "João Exemplo em Outra Cidade.")]
    hermes = Hermes(resultados, {})
    http = Paginas({URL: Pagina(URL, "", "nao_consultado", "HTTP 403", DATA)})
    resp = pesquisar_web(ALVO, hermes, http)
    assert http.chamadas == [URL] and len(resp["candidatos"]) == 2
    assert all(e["titulo"] == "Página profissional" for e in resp["evidencias"])


def test_negacao_nao_vira_emprego_documentado():
    trecho = "João Exemplo nunca trabalhou na Empresa Exemplo."
    proposta = achado(trecho=trecho, empregador="Empresa Exemplo") | {"categoria":"emprego"}
    hermes = Hermes([ResultadoBusca(URL, NOME, "")], {URL:[proposta]})
    http = Paginas({URL: Pagina(URL, trecho, "consultado", data=DATA)})
    assert not pesquisar_web(ALVO, hermes, http)["candidatos"]


def test_falha_da_leitura_preserva_proveniencia_e_primeira_pagina():
    from guicredito.pessoas.evidencias import ErroPesquisaParcial
    from guicredito.pessoas.hermes import ErroProtocolo
    class Leitor(Hermes):
        def propor(self, texto, alvo):
            if alvo["url"].endswith("segunda"):
                raise ErroProtocolo()
            return [achado()]
    segunda = URL + "/segunda"
    cliente = Leitor([ResultadoBusca(URL, NOME, ""), ResultadoBusca(segunda, NOME, "")], {})
    http = Paginas({url: Pagina(url, NOME, "consultado", data=DATA) for url in (URL, segunda)})
    with pytest.raises(ErroPesquisaParcial) as erro:
        pesquisar_web(ALVO, cliente, http)
    parcial = erro.value.parcial
    assert parcial["consultas"][0]["id_resposta"] == "resp_teste"
    assert len(parcial["evidencias"]) == 1
    assert parcial["consultas"][-1]["estado"] == "interrompido" and NOME not in str(erro.value)


def test_identificadores_e_contatos_privados_ficam_fora_da_leitura():
    texto = "João Exemplo, 123.456.789-09, (11) 99999-9999, contato@example.test."
    hermes = Hermes([ResultadoBusca(URL, NOME, "")], {URL:[]})
    pesquisar_web(ALVO, hermes, Paginas({URL: Pagina(URL, texto, "consultado", data=DATA)}))
    enviado = hermes.leituras[0][0]
    assert NOME.casefold() in enviado.casefold()
    assert all(x not in enviado for x in ("123.456.789-09", "99999-9999", "@example.test"))


def test_nome_empresarial_com_digito_sem_enviar_documentos():
    hermes = Hermes([], {})
    pesquisar_web(ALVO | {"nome":"3 EXEMPLO S.A.", "tipo":"PJ", "papel":"credor"}, hermes, Paginas({}))
    assert '3 EXEMPLO S.A.' in hermes.pesquisas[0]
