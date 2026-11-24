"""Extensão do API Server do Hermes. Cada pedido tem um único turno, sem histórico."""
import asyncio
import ipaddress
import json
import re
import uuid


POLITICA = "guicredito-parallel-anon-v1"
MODELO_API = "hermes-agent"
BASE_LOCAL = "http://127.0.0.1:18434/v1"
MAX_BYTES = 5_000_000
SESSAO_PARALLEL = uuid.uuid4().hex


class FalhaDeLeitura(ValueError):
    pass


def objeto_unico(pares):
    obj = {}
    for k, v in pares:
        if k in obj:
            raise ValueError("JSON ambíguo")
        obj[k] = v
    return obj


def validar(pedido):
    if (not isinstance(pedido, dict)
            or set(pedido) != {"model", "input", "instructions", "store", "policy", "modo"}
            or pedido["model"] != MODELO_API or pedido["policy"] != POLITICA or pedido["store"] is not False
            or pedido["modo"] not in ("busca", "leitura")):
        raise ValueError("Pedido fora do contrato")
    for campo, limite in (("instructions", 8192), ("input", 512 if pedido["modo"] == "busca" else MAX_BYTES)):
        texto = pedido[campo]
        if not isinstance(texto, str) or not texto.strip() or len(texto.encode()) > limite:
            raise ValueError("Entrada inválida")


def executar(pedido, chamar_modelo, buscar):
    validar(pedido)
    escolha = chamar_modelo(pedido["instructions"], pedido["input"], pedido["modo"])
    msg = escolha["message"]
    calls = msg.get("tool_calls") or []
    if pedido["modo"] == "leitura":
        if calls or msg.get("function_call"):
            raise FalhaDeLeitura("ferramenta_na_leitura")
        if escolha["finish_reason"] == "length":
            raise FalhaDeLeitura("leitura_truncada")
        if escolha["finish_reason"] != "stop" or not isinstance(msg.get("content"), str) or not msg["content"].strip():
            raise FalhaDeLeitura("leitura_incompleta")
        saida = [{"type": "message", "role": "assistant",
                  "content": [{"type": "output_text", "text": msg["content"]}]}]
    else:
        if (msg.get("function_call") or escolha["finish_reason"] != "tool_calls"
                or not isinstance(calls, list) or len(calls) != 1):
            raise ValueError("Esperada uma única chamada")
        call = calls[0]
        fn = call["function"]
        if (call["type"] != "function" or fn["name"] != "web_search"
                or not re.fullmatch(r"[\w.-]{1,128}", call["id"], re.ASCII)):
            raise ValueError("Ferramenta ou ID inválido")
        args = json.loads(fn["arguments"], object_pairs_hook=objeto_unico)
        if (args != {"query": pedido["input"], "limit": 3} or type(args["limit"]) is not int):
            raise ValueError("Argumentos divergentes")
        # O único ponto de despacho. Usa o pedido autorizado, após conferir a decisão do modelo.
        itens = buscar(pedido["input"])
        resultado = {"success": True, "data": {"web": itens, "served_by": "parallel"}}
        comum = {"status": "completed", "call_id": call["id"]}
        saida = [dict(comum, type="function_call", name="web_search", arguments=fn["arguments"]),
                 dict(comum, type="function_call_output", output=json.dumps(resultado, ensure_ascii=False))]
    return {"id": "resp_" + uuid.uuid4().hex, "status": "completed", "output": saida}


def buscar_anonimo(query):
    """A mesma ferramenta MCP web_search do provedor Parallel do Hermes, sem autenticação nem failover."""
    import httpx
    from plugins.web.keyless_mcp import PARALLEL_MCP_URL, _parse_mcp_body
    if PARALLEL_MCP_URL != "https://search.parallel.ai/mcp":
        raise ValueError("Endpoint anônimo do Hermes mudou")
    body = {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": "web_search",
            "arguments": {"objective": query, "search_queries": [query], "session_id": SESSAO_PARALLEL}}}
    # Cliente novo e anônimo. Nunca importa chaves do gateway, cookies, proxy ou credenciais de ambiente.
    with httpx.Client(trust_env=False, follow_redirects=False, timeout=30) as client:
        with client.stream("POST", PARALLEL_MCP_URL, json=body,
                           headers={"Accept": "application/json, text/event-stream", "Accept-Encoding": "identity"}) as r:
            r.raise_for_status()
            if r.headers.get("Content-Encoding", "identity").lower() != "identity":
                raise ValueError("Codificação inesperada")
            data = bytearray()
            for parte in r.iter_raw(65536):
                data.extend(parte)
                if len(data) > MAX_BYTES:
                    raise ValueError("Resposta extensa")
    resultados = json.loads(_parse_mcp_body(data.decode("utf-8")))["results"]
    if not isinstance(resultados, list):
        raise ValueError("Resultados incompatíveis")
    itens = []
    for row in resultados[:3]:
        if (not isinstance(row, dict) or not isinstance(row.get("url"), str) or not row["url"]
                or not isinstance(row.get("excerpts", []), list)):
            raise ValueError("Item incompatível")
        itens.append({"url": row["url"], "title": row.get("title") or "",
                      "description": " ".join(row.get("excerpts", []))})
    return itens


def modelo_local():
    from gateway.run import _load_gateway_config, _resolve_runtime_agent_kwargs, _resolve_gateway_model
    cfg = _load_gateway_config()
    model = cfg.get("model") or {}
    if (not isinstance(model, dict) or model.get("base_url", "").rstrip("/") != BASE_LOCAL
            or model.get("provider") != "llamacpp" or not _resolve_gateway_model(cfg)
            or (cfg.get("web") or {}).get("keyless_fallback") is False):
        raise ValueError("Modelo local ou acesso anônimo indisponível")
    runtime = _resolve_runtime_agent_kwargs()
    if (runtime.get("_fallback_notice") or (runtime.get("base_url") or "").rstrip("/") != BASE_LOCAL
            or not runtime.get("api_key")):
        raise ValueError("Runtime local indisponível")
    return _resolve_gateway_model(cfg), runtime["api_key"]


def chamar_modelo(instructions, entrada, modo):
    import httpx
    from openai import OpenAI
    from tools.web_tools import WEB_SEARCH_SCHEMA

    model, key = modelo_local()
    opcoes = {}
    if modo == "busca":
        opcoes = {"tools": [{"type": "function", "function": WEB_SEARCH_SCHEMA}],
                  "tool_choice": {"type": "function", "function": {"name": "web_search"}}}
    else:
        texto = {"type": "string"}
        campos = {"nome": texto, "url": texto, "trecho": texto,
                  "categoria": {"type": "string", "enum": ["identidade", "emprego", "processo", "contato_profissional"]},
                  "indicios": {"type": "object", "additionalProperties": False,
                               "properties": dict.fromkeys(("cidade", "empregador", "faixa_etaria"), texto)}}
        schema = {"type": "array", "items": {"type": "object", "properties": campos,
                  "additionalProperties": False, "required": list(campos)}}
        opcoes = {"response_format": {"type": "json_schema", "json_schema": {"name": "achados", "schema": schema}},
                  "extra_body": {"chat_template_kwargs": {"enable_thinking": False}}}
    mensagens = [{"role": "system", "content": instructions}, {"role": "user", "content": entrada}]
    # O próprio plugin do gateway despacha a ferramenta. O SDK do modelo só devolve sua decisão.
    with OpenAI(base_url=BASE_LOCAL, api_key=key, max_retries=0,
                http_client=httpx.Client(trust_env=False, follow_redirects=False, timeout=110)) as llm:
        resp = llm.chat.completions.create(model=model, messages=mensagens, temperature=0,
                                           max_tokens=4096 if modo == "leitura" else 2048, **opcoes)
    if len(resp.choices) != 1:
        raise ValueError("Esperada uma única escolha do modelo")
    return resp.choices[0].model_dump()


def registrar_rotas(app, adapter):
    from aiohttp import web
    from gateway.platforms.api_server import _reserve_pending_api_work
    tarefa = None

    def autenticar(request):
        if (not request.remote or not ipaddress.ip_address(request.remote).is_loopback
                or not adapter._expected_api_key()):
            raise web.HTTPForbidden()
        erro = adapter._check_auth(request)
        if erro is not None:
            raise web.HTTPUnauthorized()

    async def politica(request):
        autenticar(request)
        try:
            modelo_local()
        except Exception:
            raise web.HTTPServiceUnavailable(text="Runtime local indisponível") from None
        return web.json_response({"model": MODELO_API, "policy": POLITICA})

    async def turno(pedido):
        with _reserve_pending_api_work(adapter):
            return await asyncio.to_thread(executar, pedido, chamar_modelo, buscar_anonimo)

    async def responder(request):
        nonlocal tarefa
        autenticar(request)
        try:
            pedido = json.loads(await request.text(), object_pairs_hook=objeto_unico)
            validar(pedido)
        except (ValueError, TypeError, RecursionError):
            raise web.HTTPBadRequest(text="Pedido inválido") from None
        if (tarefa and not tarefa.done()) or adapter._draining_response() is not None:
            raise web.HTTPServiceUnavailable(text="Gateway ocupado")
        tarefa = asyncio.create_task(turno(pedido))
        try:
            return web.json_response(await asyncio.shield(tarefa))
        except FalhaDeLeitura as erro:
            raise web.HTTPBadGateway(text="Leitura interrompida", headers={"X-Guicredito-Erro": str(erro)}) from None
        except Exception:
            # Nunca propaga prompts, corpos do provedor, chaves ou detalhes de conexão.
            raise web.HTTPBadGateway(text="Turno restrito não concluído") from None

    app.router.add_get("/v1/guicredito/policy", politica)
    app.router.add_post("/v1/guicredito/responses", responder)


def register(ctx):
    ctx.register_platform_handler("api_server", registrar_rotas)
