import json

import pytest

from guicredito.pessoas.http import PoliticaIndisponivel, TransporteLocal
from tests.pessoas.test_http import Conexao, http
from tests.pessoas.test_hermes import config


def test_capacidade_e_post_exclusivos_do_plugin(tmp_path):
    from guicredito.pessoas.http import POLITICA_PILOTO
    from contextlib import nullcontext
    from types import SimpleNamespace

    corpo = {"policy": POLITICA_PILOTO, "model": "hermes-agent"}
    probe = Conexao("127.0.0.1", http(json.dumps(corpo).encode()))
    post = Conexao("127.0.0.1", http(b'{"id":"resp-1"}'))
    sockets = iter([probe, post])
    tx = TransporteLocal(config(tmp_path), conectar=lambda *_: next(sockets),
                         ritmo=SimpleNamespace(requisicao=nullcontext))
    tx.exigir_politica()
    payload = {"model": "hermes-agent", "input": "FICTICIO", "instructions": "buscar", "store": False}
    resposta = tx.enviar_restrito("http://127.0.0.1:8642/v1/responses", payload,
                                  modo="busca", argumentos={"query": "FICTICIO", "limit": 3})
    assert resposta["id"] == "resp-1"
    assert b'GET /v1/guicredito/policy ' in probe.enviados and b'FICTICIO' not in probe.enviados
    assert b'POST /v1/guicredito/responses ' in post.enviados
    assert json.loads(post.enviados.split(b'\r\n\r\n')[1]) == dict(payload, policy=POLITICA_PILOTO, modo="busca")


def plugin():
    from integracoes.hermes import guicredito_pessoas
    return guicredito_pessoas


def pedido(modo):
    return dict(model="hermes-agent", input="Caso fictício", instructions="Instruções", store=False,
                policy=plugin().POLITICA, modo=modo)


def chamada(nome="web_search", args='{"query":"Caso fictício","limit":3}'):
    return {"id": "call_123", "type": "function", "function": {"name": nome, "arguments": args}}


def escolha(calls, finish="tool_calls", content=""):
    return {"finish_reason": finish, "message": {"tool_calls": calls, "content": content}}


@pytest.mark.parametrize("calls", [[], [chamada(), chamada()], [chamada("web_extract")],
    [chamada(args='{"query":"outro","limit":3}')], [chamada(args='{"query":"Caso fictício","limit":4}')],
    [chamada(args='{"query":"outro","query":"Caso fictício","limit":3}')]])
def test_veta_antes_do_backend(calls):
    p = plugin()
    with pytest.raises(ValueError):
        p.executar(pedido("busca"), lambda *_: escolha(calls), lambda *_: pytest.fail("despacho"))


def test_busca_realmente_despachada_uma_vez_e_raiz_da_evidencia():
    p = plugin()
    despachos = []
    def buscar(query):
        despachos.append(query)
        return [{"url": "https://example.org/", "title": "Exemplo", "description": "Trecho"}]
    resp = p.executar(pedido("busca"), lambda *_: escolha([chamada()]), buscar)
    call, result = resp["output"]
    assert call["call_id"] == result["call_id"] == "call_123"
    assert despachos == ["Caso fictício"]
    assert json.loads(result["output"])["data"]["served_by"] == "parallel"
    assert resp["status"] == "completed"


@pytest.mark.parametrize("choice", [escolha([chamada()]), escolha([], "length", "[]")])
def test_leitura_rejeita_ferramentas_e_truncamento(choice):
    p = plugin()
    with pytest.raises(ValueError):
        p.executar(pedido("leitura"), lambda *_: choice, lambda *_: pytest.fail("despacho"))


def test_leitura_so_texto():
    p = plugin()
    resp = p.executar(pedido("leitura"), lambda *_: escolha([], "stop", "[]"), lambda *_: pytest.fail("despacho"))
    assert resp["output"][0]["content"][0]["text"] == "[]"


@pytest.mark.parametrize("alteracao", [{"model": "outro"}, {"store": True}, {"tools": []}, {"policy": "outra"}])
def test_pedido_invalido_nao_chega_ao_modelo(alteracao):
    p = plugin()
    with pytest.raises(ValueError):
        p.executar(pedido("busca") | alteracao, lambda *_: pytest.fail("modelo"), lambda *_: pytest.fail("despacho"))
