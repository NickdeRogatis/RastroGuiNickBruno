"""Offline acceptance through the public CLI, using the preceding stages' file formats."""
import json
import re
import socket

from openpyxl import load_workbook

from guicredito.pessoas.__main__ import main
from guicredito.pessoas.config import carregar_config
from guicredito.pessoas.hermes import ClienteHermes
from guicredito.pessoas.http import Pagina
from .test_cnpj import snapshot
from .test_contatos import Provedor
from .test_entrada import cnj, entradas
from .test_evidencias import Paginas
from .test_hermes import mensagem


URL = "https://exemplo.test/profissional"
TRECHO = "JOÃO EXEMPLO trabalha na EMPRESA FICTÍCIA."


class GatewayEmMemoria:
    def __init__(self):
        self.buscas = []
        self.leituras = []

    def exigir_politica(self):
        pass  # Dublê da política de despacho. Não comprova configuração de um gateway instalado.

    def enviar(self, url, payload):
        assert url.endswith("/v1/models") and payload is None
        return {"data": [{"id": "hermes-agent"}]}

    def enviar_restrito(self, url, payload, *, modo, argumentos):
        assert url.endswith("/v1/responses") and payload["store"] is False
        if modo == "leitura":
            assert argumentos == {}
            item = json.loads(payload["input"])
            assert set(item) == {"papel", "nome", "texto", "url"} and item["texto"] == TRECHO
            self.leituras.append(item["url"])
            achado = {"nome": item["nome"], "url": item["url"], "trecho": TRECHO,
                      "categoria": "emprego", "indicios": {"empregador": "EMPRESA FICTÍCIA"}}
            return {"status": "completed", "id": "resp_leitura", "output": [mensagem(json.dumps([achado]))]}

        assert modo == "busca" and argumentos == {"limit": 3, "query": payload["input"]}
        consulta = argumentos["query"]
        self.buscas.append(consulta)
        escolheu = '"JOÃO EXEMPLO"' in consulta
        sufixo = "teste" if escolheu else str(len(self.buscas))
        resultados = [{"url": URL, "title": "Perfil fictício", "description": TRECHO}] if escolheu else []
        chamada = {"type": "function_call", "name": "web_search", "status": "completed",
                   "call_id": "call_" + sufixo, "arguments": json.dumps(argumentos)}
        retorno = {"type": "function_call_output", "status": "completed", "call_id": chamada["call_id"],
                   "output": json.dumps({"success": True, "data": {"web": resultados, "served_by": "busca_ficticia"}})}
        return {"status": "completed", "id": "resp_" + sufixo, "output": [retorno, chamada]}


def _bytes(arquivos):
    return {a: a.read_bytes() for a in arquivos if a.is_file()}


def _json(caminho):
    return json.loads(caminho.read_text(encoding="utf-8"))


def _editar(aba, chave, valor, mudancas):
    colunas = {c.value: c.column for c in aba[1]}
    linha, = [r for r in range(2, aba.max_row + 1) if aba.cell(r, colunas[chave]).value == valor]
    for coluna, novo in mudancas.items():
        aba.cell(linha, colunas[coluna]).value = novo


def _inverter(aba):
    linhas = list(aba.values)[1:]
    aba.delete_rows(2, len(linhas))
    for linha in reversed(linhas):
        aba.append(linha)


def test_duas_passagens_dois_casos_sem_rede(tmp_path, monkeypatch, capsys, entradas, snapshot):
    monkeypatch.chdir(tmp_path)
    tentativas = []
    def sem_rede(*args, **kwargs):
        tentativas.append(True)
        raise AssertionError("Tentativa de rede real durante o aceite")
    monkeypatch.setattr(socket, "socket", sem_rede)
    monkeypatch.setattr(socket, "getaddrinfo", sem_rede)
    for k, v in {"BUSCA": "hermes", "HERMES_URL": "http://127.0.0.1:8642/v1",
                 "HERMES_MODELO": "hermes-agent", "HERMES_KEY": "chave-ficticia-do-aceite",
                 "INDICE_CNPJ": str(snapshot[3])}.items():
        monkeypatch.setenv("PESSOAS_" + k, v)

    selecao, pasta, planilha = entradas
    capa = pasta / cnj(1) / "resultado.json"
    conteudo = _json(capa)
    conteudo["partes_linhas"][0][1] += " Advogada: ANA EXEMPLO (OAB 123/SP)"
    capa.write_text(json.dumps(conteudo), encoding="utf-8")
    fontes = [selecao, planilha, snapshot[1], *pasta.rglob("*"), *snapshot[0].rglob("*")]
    originais = _bytes(fontes)
    assert main(["preparar-cnpj", "--snapshot", str(snapshot[0]), "--layout", str(snapshot[1]),
                 "--competencia", snapshot[2], "--indice", str(snapshot[3])]) == 0
    indice_original = snapshot[3].read_bytes()
    tx = GatewayEmMemoria()
    paginas = Paginas({URL: Pagina(URL, TRECHO, "consultado", data="2026-11-23T12:00:00Z")})
    gratuito = {"hermes": ClienteHermes(carregar_config(), tx), "http": paginas}
    provedor = Provedor()
    lote = tmp_path / "lote"
    pesquisar = ["pesquisar", "--selecao", str(selecao), "--aprofundamento", str(pasta),
                 "--planilha", str(planilha), "--saida", str(lote)]
    contatos = ["contatos", "--lote", str(lote)]
    descartar = ["descartar", "--lote", str(lote)]
    assert main(pesquisar, gratuito) == 0
    assert not provedor.chamadas and main(contatos) == 2
    inicial = (lote / "revisao.html").read_text()
    assert "vínculo empresarial pendente de confirmação" in inicial and "de 100 mil" not in inicial
    consulta, = [q for q in _json(lote / cnj(1) / "consultas.json") if q.get("id_resposta") == "resp_teste"]
    assert (consulta["id_chamada"], consulta["backend"]) == ("call_teste", "busca_ficticia")
    assert paginas.chamadas == tx.leituras == [URL]
    alvos = {re.match(r'^"([^"]+)"', b)[1] for b in tx.buscas}
    assert alvos == {"JOÃO EXEMPLO", "ANA EXEMPLO", "FIADORA EXEMPLO", "COOBRIGADO EXEMPLO",
                     "AVALISTA EXEMPLO", "BANCO EXEMPLO S.A.", "DEVEDOR EXEMPLO", "CREDORA EXEMPLO"}
    buscas_originais = list(tx.buscas)
    caso_path = lote / cnj(1) / "pessoas.json"
    caso = _json(caso_path)
    assert caso["pontuacao_original"] == 60 and caso["posicao_original"] == 1
    oab, = caso["oab"]
    assert oab["estado"] == "pendente" and oab["nome"] == "ANA EXEMPLO"
    socio, = [c for c in caso["candidatos"] if c["fonte"] == "CNPJ" and c["categoria"] == "participação empresarial"
              and c["empresa"] == "BANCO EXEMPLO S.A."]
    escolhido = socio["id"]
    excel = lote / "pessoas.xlsx"
    wb = load_workbook(excel)
    _editar(wb["OAB"], "Alvo ID", oab["alvo_id"], {"OAB/UF conferida": "123/SP",
            "Dados profissionais conferidos": "Escritório fictício", "Data da conferência": "2026-11-23"})
    _editar(wb["Candidatos"], "Candidato ID", escolhido, {"Confirmado": "sim", "CPF": "01234567890"})
    _inverter(wb["Candidatos"])
    wb.save(excel)
    wb.close()
    assert main(pesquisar, gratuito) == 0
    assert any(c.get("verificacao") == "manual" and c["alvo_id"] == oab["alvo_id"] for c in _json(caso_path)["candidatos"])
    revisao = (lote / "revisao.html").read_text()
    assert "capital social declarado" in revisao and "de 100 mil a menos de 1 milhão" in revisao
    assert "conferência manual pendente" not in revisao
    for privado in ("JOÃO", "ANA EXEMPLO", cnj(1), "BANCO EXEMPLO", URL, "01234567890", "100000,00"):
        assert privado not in revisao

    pago = {"provedor": provedor}
    assert main(contatos, pago) == 0 and not provedor.chamadas
    wb = load_workbook(excel)
    _editar(wb["Candidatos"], "Candidato ID", escolhido, {"Autorizar consulta paga": "sim"})
    wb.save(excel)
    wb.close()
    assert main(pesquisar, gratuito | pago) == 0 and not provedor.chamadas
    assert main(contatos, pago) == 0 and len(provedor.chamadas) == 1
    ambiguo = _json(caso_path)
    assert len(ambiguo["provedor"]) == 2 and _json(lote / cnj(1) / "contatos.json") == []
    assert "CONTATO_SENTINELA" not in caso_path.read_text()
    opcao, = [o for o in ambiguo["provedor"] if o["id_externo"] == "y"]
    wb = load_workbook(excel)
    _editar(wb["Provedor"], "Provedor ID", opcao["id"], {"Confirmado": "sim"})
    _inverter(wb["Provedor"])
    wb.save(excel)
    wb.close()
    assert main(contatos, pago) == 0
    assert main(contatos, pago) == 0 and provedor.chamadas == [{"cpf": "01234567890"}, "y"]
    contato, = _json(lote / cnj(1) / "contatos.json")
    assert contato["candidato_id"] == escolhido and contato["valor"] == "FICTÍCIO"

    wb = load_workbook(excel)
    _editar(wb["Casos"], "Processo", cnj(1), {"Descartar": "sim"})
    wb.save(excel)
    wb.close()
    antes_previa = _bytes(lote.rglob("*"))
    mantido = _json(lote / cnj(2) / "pessoas.json")
    capsys.readouterr()
    assert main(descartar) == 0
    previa = capsys.readouterr().out
    codigo = re.search(r"confirmar ([0-9a-f]+)", previa)[1]
    assert caso["rotulo"] in previa and cnj(1) not in previa
    assert _bytes(lote.rglob("*")) == antes_previa
    assert main([*descartar, "--confirmar", codigo]) == 0
    assert main(pesquisar, gratuito) == 0
    assert main(contatos, pago) == 0
    assert not (lote / cnj(1)).exists() and cnj(1) not in (lote / "manifesto.json").read_text()
    assert "JOÃO EXEMPLO" not in (lote / "relatorio.html").read_text()
    assert _json(lote / cnj(2) / "pessoas.json")["rotulo"] == mantido["rotulo"]
    assert len(provedor.chamadas) == 2 and tx.buscas == buscas_originais and paginas.chamadas == [URL]
    assert _bytes(fontes) == originais and snapshot[3].read_bytes() == indice_original
    assert not tentativas
