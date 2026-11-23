import hashlib
import json
from urllib.parse import parse_qs, urlsplit

import pytest
from openpyxl import Workbook

from guicredito.aprofundamento.__main__ import main
from guicredito.aprofundamento.cliente import Cliente, FalhaConsulta, Redirecionamento, destino_permitido
from guicredito.aprofundamento.cnj import formatar, normalizar, url_consulta
from guicredito.aprofundamento.fluxo import importar, posicoes, reprocessar, rodar, selecionar, validar_casos
from guicredito.aprofundamento.pagina import diagnostico, extrair, link_detalhe, url_movimentacoes, extrair_movimentacoes


def incidente(i=1):
    return f'''<div id="containerDadosPrincipaisProcesso"><span class="unj-larger">Cumprimento de sentença ({formatar(cnj(i))})</span>
    <a class="processoPrinc">{formatar(cnj(20))}</a><span id="foroProcesso">Foro de Exemplo</span></div>
    <a id="btnExibirMovimentacoes">Exibir movimentações</a>
    <script>$.saj.movimentacoes = {{codigoProcesso: 'EXEMPLO0000'}};</script>'''


def test_incidente_confere_numero_proprio_e_nao_o_principal():
    r = extrair(incidente(), cnj())
    assert r["status"] == "coletado_parcial"
    assert r["campos"]["classe"] == "Cumprimento de sentença"
    assert r["campos"]["processo_principal_texto"] == formatar(cnj(20))
    assert extrair(incidente(), cnj(20))["status"] == "processo_divergente"


def test_movimentacoes_sob_demanda(tmp_path):
    fragmento = '<table id="tabelaTodasMovimentacoes"><tr><td>01/11/2026</td><td>Decisão fictícia</td></tr></table>'
    c = ClienteFalso([incidente(), fragmento])
    r = rodar({"casos": [caso()]}, c, tmp_path)[0]
    assert r["status"] == "coletado"
    assert r["movimentacoes_status"] == "primeira_pagina"
    assert len(r["movimentacoes_linhas"]) == 1
    assert c.urls[-1] == url_movimentacoes(incidente())
    assert r["evidencias"][-1]["arquivo"] == "movimentacoes.html.txt"


def test_erro_movimentacoes_preserva_capa_e_interrompe_bloqueio(tmp_path):
    c = ClienteFalso([incidente(), FalhaConsulta("bloqueado", "HTTP 403")])
    r = rodar({"casos": [caso(), caso(2)]}, c, tmp_path)
    assert r[0]["status"] == "coletado_parcial"
    assert r[0]["campos"]["classe"] == "Cumprimento de sentença"
    assert r[1]["status"] == "pendente"


def test_mensagem_de_erro_nao_vira_lista_vazia_de_movimentos():
    assert extrair_movimentacoes('<div class="mensagemErroMovimentacoes">Não foi possível realizar a operação requisitada</div>') == {"movimentacoes_status": "resposta_nao_reconhecida"}


def test_cache_antigo_e_atualizado(tmp_path):
    pasta = tmp_path / cnj()
    pasta.mkdir()
    (pasta / 'resultado.json').write_text(json.dumps({**caso(), "status": "coletado"}))
    c = ClienteFalso([pagina()])
    r = rodar({"casos": [caso()]}, c, tmp_path)
    assert c.urls
    assert r[0]["versao_extrator"] == 3


def test_tabela_nova_com_mencao_eproc_preserva_movimentos():
    html = '<table><tbody id="tabelaPrimeiraPaginaMovimentacoes"><tr><td>01/11/2026</td><td>Processo migrado para eproc</td></tr></tbody></table>'
    r = extrair_movimentacoes(html)
    assert r["movimentacoes_status"] == "primeira_pagina"
    assert len(r["movimentacoes_linhas"]) == 1
    assert r["referencia_eproc"] is True


def test_reprocessamento_preserva_data_e_valida_evidencia(tmp_path):
    r = rodar({"casos": [caso()]}, ClienteFalso([pagina()]), tmp_path)[0]
    novo = reprocessar(tmp_path)[0]
    assert novo["consultado_em"] == r["consultado_em"]
    assert novo["pontuacao_original"] == r["pontuacao_original"]
    assert novo["reprocessado_em"]
    (tmp_path / cnj() / 'consulta.html.txt').write_text('resposta alterada')
    with pytest.raises(ValueError, match="resposta salva mudou"):
        reprocessar(tmp_path)


def cnj(i=1):
    base = f"{i:07d}20208260001"
    dd = 98 - int(base + "00") % 97
    return f"{i:07d}{dd:02d}20208260001"


def caso(i=1):
    return {"numero_processo": cnj(i), "posicao_original": i, "pontuacao_original": 80 - i}


def pagina(i=1):
    return f'''<html><span id="numeroProcesso">{formatar(cnj(i))}</span>
    <div id="classeProcesso">Execução de título extrajudicial</div>
    <div id="valorAcaoProcesso">R$ 123.456,78</div>
    <table id="tableTodasPartes"><tr><td>Exeqte.</td><td>EMPRESA EXEMPLO LTDA</td></tr>
    <tr><td>Executado</td><td>PESSOA FICTÍCIA EXEMPLO</td></tr></table>
    <table id="tabelaUltimasMovimentacoes"><tr><td>20/11/2026</td><td>Último ato</td></tr></table>
    <table id="tabelaTodasMovimentacoes"><tr><th>Data</th><th>Ato</th></tr>
    <tr><td>20/11/2026</td><td></td><td>Decisão <span>Intime-se.</span></td></tr>
    <tr><td>10/11/2026</td><td></td><td>Petição juntada</td></tr></table></html>'''


class ClienteFalso:
    def __init__(self, respostas, inicial="<html>Consulta de processos</html>"):
        self.respostas = list(respostas)
        self.urls = []
        self.inicial = inicial
        self.inicios = 0

    def iniciar(self):
        self.inicios += 1
        if isinstance(self.inicial, Exception):
            raise self.inicial
        return self.inicial

    def get(self, url):
        self.urls.append(url)
        resposta = self.respostas.pop(0)
        if isinstance(resposta, Exception):
            raise resposta
        return resposta


def test_numero_e_url():
    n = cnj()
    assert normalizar(formatar(n)) == n
    params = parse_qs(urlsplit(url_consulta(n)).query)
    assert params["numeroDigitoAnoUnificado"] == [formatar(n)[:15]]
    assert params["foroNumeroUnificado"] == ["0001"]
    assert params["dadosConsulta.valorConsultaNuUnificado"] == [formatar(n)]
    with pytest.raises(ValueError):
        normalizar(n[:-1] + "2")
    with pytest.raises(ValueError):
        normalizar("../arquivo")


def test_extrai_apenas_numero_exato_e_preserva_todos_movimentos():
    r = extrair(pagina(), cnj())
    assert r["status"] == "coletado"
    assert r["campos"]["valor_da_causa_texto"] == "R$ 123.456,78"
    assert len(r["partes_linhas"]) == 2
    assert len(r["movimentacoes_linhas"]) == 2
    assert r["movimentacoes_linhas"][0][-1] == "Decisão Intime-se."
    assert r["campos"]["situacao_texto"] is None
    assert extrair(pagina(2), cnj())["status"] == "processo_divergente"
    assert extrair("<html>Consulta de processos</html>", cnj())["status"] == "layout_nao_reconhecido"


@pytest.mark.parametrize("html,esperado", [
    ("<h1>Access denied</h1>", "bloqueado"),
    ("<p>Não sou um robô</p>", "captcha"),
    ("<p>Processo migrado para o eproc</p>", "consultar_eproc"),
    ("<p>Não foram encontrados processos</p>", "nao_localizado"),
    ('<script src="recaptcha.js"></script><p>Consulta pública</p>', None),
])
def test_classifica_respostas_sem_inventar_dados(html, esperado):
    assert diagnostico(html) == esperado


def test_link_detalhe_somente_numero_e_dominio_corretos():
    n = formatar(cnj())
    html = f'<a href="show.do?processo.codigo=EXEMPLO">{n}</a>'
    assert link_detalhe(html, cnj()).startswith("https://esaj.tjsp.jus.br/cpopg/show.do?")
    assert link_detalhe(html, cnj(2)) is None
    assert link_detalhe(f'<a href="https://outro.example/show.do">{n}</a>', cnj()) is None
    assert link_detalhe(html + f'<a href="show.do?processo.codigo=OUTRO">{n}</a>', cnj()) is None


def test_selecao_da_planilha_nao_modifica_original(tmp_path):
    caminho = tmp_path / "rodada.xlsx"
    wb = Workbook()
    ws = wb.active
    ws.title = "Casos"
    ws.append(["#", "Pontos", "Processo"])
    for i in range(1, 13):
        ws.append([i, 80 - i, formatar(cnj(i))])
    wb.save(caminho)
    antes = caminho.read_bytes()
    selecao = selecionar(caminho, posicoes("2,4,6-8"))
    assert [c["posicao_original"] for c in selecao["casos"]] == [2, 4, 6, 7, 8]
    assert selecao["casos"][0]["pontuacao_original"] == 78
    assert caminho.read_bytes() == antes
    with pytest.raises(ValueError):
        selecionar(caminho, [99])


@pytest.mark.parametrize("valor", ["1-11", "1,1", "0", "10-1", "-2", "abc"])
def test_selecao_invalida(valor):
    with pytest.raises(ValueError):
        posicoes(valor)


def test_lote_rejeita_repeticao_e_excesso():
    with pytest.raises(ValueError):
        validar_casos([caso(), caso()])
    with pytest.raises(ValueError):
        validar_casos([caso(i) for i in range(1, 12)])


def test_lote_dez_casos_salva_origem_e_score_sem_recalcular(tmp_path):
    selecao = {"casos": [caso(i) for i in range(1, 11)]}
    cliente = ClienteFalso([pagina(i) for i in range(1, 11)])
    resultados = rodar(selecao, cliente, tmp_path)
    assert all(r["status"] == "coletado" for r in resultados)
    assert cliente.inicios == 1
    assert len(cliente.urls) == 10
    assert resultados[0]["pontuacao_original"] == 79
    bruto = tmp_path / cnj() / "consulta.html.txt"
    assert resultados[0]["evidencias"][0]["sha256"] == hashlib.sha256(bruto.read_bytes()).hexdigest()
    assert (tmp_path / "relatorio.html").exists()
    assert len(json.loads((tmp_path / "resumo.json").read_text())["resultados"]) == 10
    sem_rede = ClienteFalso([])
    novamente = rodar(selecao, sem_rede, tmp_path)
    assert all(r["reutilizado"] for r in novamente)
    assert sem_rede.inicios == 0


def test_bloqueio_interrompe_lote_e_preserva_sucesso(tmp_path):
    c = ClienteFalso([pagina(), FalhaConsulta("bloqueado", "HTTP 429")])
    r = rodar({"casos": [caso(i) for i in range(1, 11)]}, c, tmp_path)
    assert [x["status"] for x in r] == ["coletado", "bloqueado"] + ["pendente"] * 8
    assert len(c.urls) == 2
    assert all(x["motivo"] == "bloqueado" for x in r[2:])


def test_falha_inicial_nao_faz_dez_tentativas(tmp_path):
    c = ClienteFalso([], inicial=FalhaConsulta("erro_rede", "sem rede"))
    r = rodar({"casos": [caso(i) for i in range(1, 11)]}, c, tmp_path)
    assert c.inicios == 1
    assert not c.urls
    assert all(x["status"] == "pendente" and x["motivo"] == "erro_rede" for x in r)


def test_busca_segue_detalhe_exato(tmp_path):
    c = ClienteFalso([f'<a href="show.do?processo.codigo=EXEMPLO">{formatar(cnj())}</a>', pagina()])
    r = rodar({"casos": [caso()]}, c, tmp_path)
    assert r[0]["status"] == "coletado"
    assert len(r[0]["evidencias"]) == 2
    assert "show.do" in r[0]["url_pagina"]


def test_layout_desconhecido_interrompe(tmp_path):
    c = ClienteFalso(["<h1>Site mudou</h1>"])
    r = rodar({"casos": [caso(), caso(2)]}, c, tmp_path)
    assert [x["status"] for x in r] == ["layout_nao_reconhecido", "pendente"]
    assert len(c.urls) == 1


def test_nao_mistura_selecoes(tmp_path):
    rodar({"casos": [caso()]}, ClienteFalso([pagina()]), tmp_path)
    with pytest.raises(ValueError, match="outra seleção"):
        rodar({"casos": [caso(2)]}, ClienteFalso([]), tmp_path)


def test_importacao_confere_identidade_e_escapa_html(tmp_path):
    html = tmp_path / "salva.html"
    html.write_text(pagina().replace("Intime-se.", "&lt;script&gt;alert(1)&lt;/script&gt;"), encoding="utf-8")
    saida = tmp_path / "saida"
    r = importar({"casos": [caso()]}, cnj(), html, saida)
    assert r["status"] == "coletado"
    assert "não consultado online" in r["fonte"]
    relatorio = (saida / "relatorio.html").read_text()
    assert "<script>" not in relatorio
    assert "&lt;script&gt;" in relatorio
    with pytest.raises(ValueError):
        importar({"casos": [caso()]}, cnj(2), html, saida)


def test_restricoes_do_cliente():
    assert destino_permitido(url_consulta(cnj()))
    assert not destino_permitido("http://esaj.tjsp.jus.br/cpopg/open.do")
    assert not destino_permitido("https://esaj.tjsp.jus.br.evil.example/cpopg/")
    with pytest.raises(ValueError):
        Cliente(intervalo=0)
    with pytest.raises(FalhaConsulta):
        Redirecionamento().redirect_request(None, None, 302, "", {}, "https://outro.example/")


def test_cli_recusa_sobrescrever_selecao(tmp_path):
    destino = tmp_path / "selecao.json"
    destino.write_text("preservar")
    with pytest.raises(SystemExit) as e:
        main(["selecionar", "--planilha", "qualquer.xlsx", "--destino", str(destino)])
    assert e.value.code == 2
    assert destino.read_text() == "preservar"
