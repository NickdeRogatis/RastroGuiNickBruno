"""Passagem opcional de contatos. O piloto não instala nenhum fornecedor."""
import hashlib
import inspect
import json
import re
from datetime import datetime, timezone
from uuid import uuid4


class ProvedorIncompativel(ValueError):
    pass


def _digito(numeros, pesos):
    resto = sum(n * p for n, p in zip(numeros, pesos, strict=True)) % 11
    return 0 if resto < 2 else 11 - resto


def validar_cpf(valor: str) -> str:
    if not isinstance(valor, str) or not re.fullmatch(r"[0-9]{11}|[0-9]{3}\.[0-9]{3}\.[0-9]{3}-[0-9]{2}", valor):
        raise ValueError("CPF inválido.")
    n = re.sub(r"\D", "", valor)
    numeros = list(map(int, n))
    if len(set(n)) == 1 or any(_digito(numeros[:k], range(k+1, 1, -1)) != numeros[k] for k in (9, 10)):
        raise ValueError("CPF inválido.")
    return n


def validar_cnpj(valor: str) -> str:
    if not isinstance(valor, str) or not re.fullmatch(
        r"[A-Z0-9]{12}[0-9]{2}|[A-Z0-9]{2}\.[A-Z0-9]{3}\.[A-Z0-9]{3}/[A-Z0-9]{4}-[0-9]{2}", valor
    ):
        raise ValueError("CNPJ inválido.")
    n = re.sub(r"[./-]", "", valor)
    nums = [ord(c) - ord("0") for c in n]
    if len(set(n)) == 1 or any(_digito(nums[:k], tuple((k - i - 1) % 8 + 2 for i in range(k))) != nums[k]
                               for k in (12, 13)):
        raise ValueError("CNPJ inválido.")
    return n


def _identificador(alvo, candidato, decisao, capacidades):
    if alvo["tipo"] == "PJ":
        cnpj = candidato.get("cnpj")
        return {"cnpj": validar_cnpj(cnpj)} if cnpj and "cnpj" in capacidades else None
    cpf = decisao.get("CPF")
    if cpf:
        return {"cpf": validar_cpf(cpf)} if "cpf" in capacidades else None
    if "nome" in capacidades:
        indicios = {k: candidato[k] for k in ("cidade", "faixa_etaria") if candidato.get(k)}
        if indicios:
            return {"nome": candidato["nome"], **indicios}
    return None


def _momento():
    return datetime.now(timezone.utc).isoformat()


def _chave(*partes):
    dados = json.dumps(partes, ensure_ascii=False).encode()
    return hashlib.sha256(dados).hexdigest()[:32]


def _texto_minimo(valor, campo):
    if not isinstance(valor, str) or not valor.strip() or len(valor) > 160:
        raise ValueError("Campo de desambiguação inválido.")
    valor = valor.strip()
    if not all(c.isalnum() or c in " .,'’&/()-–" for c in valor):
        raise ValueError("Campo de desambiguação inválido.")
    if re.search(r"(?:[0-9][ .()/-]*){8}", valor):
        raise ValueError("Identificador ou contato na projeção de descoberta.")
    if campo == "faixa_etaria" and not re.fullmatch(
        r"(?:[0-9]{1,3}(?:\s*(?:a|até|[-–])\s*[0-9]{1,3})?(?: anos)?|adulto|idoso)", valor, re.I
    ):
        raise ValueError("Faixa etária inválida.")
    return valor


def _opcoes(resposta, cid):
    if not isinstance(resposta, list):
        raise ValueError("Resposta de identificação inválida.")
    itens, ids = [], set()
    for r in resposta:
        externo = r["id"]
        if (not isinstance(externo, str) or not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9_-]{0,127}", externo)
                or re.fullmatch(r"(?:[0-9][_-]?){8,15}", externo)
                or re.search(r"(?<![a-zA-Z0-9])[0-9]{8,15}(?![a-zA-Z0-9])", externo)
                or re.fullmatch(r"(?:cpf|cnpj|tel|telefone|whatsapp)[_-]?[0-9-]+", externo, re.I)
                or externo in ids):
            raise ValueError("Identificador opaco inválido ou repetido.")
        ids.add(externo)
        indicios = {k: _texto_minimo(r[k], k) for k in ("cidade", "faixa_etaria") if r.get(k) is not None}
        itens.append({"id": _chave(cid, externo), "id_externo": externo, "candidato_id": cid,
                      "nome": _texto_minimo(r["nome"], "nome"), "indicios": indicios})
    return itens


def _opcao(caso, cid, decisoes):
    opcoes = [r for r in caso["provedor"] if r["candidato_id"] == cid]
    marcas = decisoes.get("provedor", {})
    if len(opcoes) == 1 and marcas.get(opcoes[0]["id"], {}).get("Confirmado") != "não":
        return opcoes[0]
    escolhidas = [r for r in opcoes if marcas.get(r["id"], {}).get("Confirmado") == "sim"]
    if len(escolhidas) > 1:
        raise ValueError("Confirme uma única opção do provedor por candidato.")
    return escolhidas[0] if escolhidas else None


def _assinatura(provedor, identidade):
    return hashlib.sha256(json.dumps([provedor, identidade], sort_keys=True).encode()).hexdigest()


def validar_escolhas(caso, decisoes):
    """Preserva a identidade à qual um contato pertence, inclusive ao regenerar relatórios."""
    candidatos = {c["id"]: c for c in caso.get("candidatos", [])}
    alvos = {a["id"]: a for a in caso.get("alvos", [])}
    for cid, pedido in caso.get("pedidos", {}).items():
        if pedido.get("estado") == "encerrado":
            continue
        if pedido.get("tipo_identificador"):
            c = candidatos[cid]
            identidade = _identificador(alvos[c["alvo_id"]], c, decisoes["candidatos"].get(cid, {}),
                                        {pedido["tipo_identificador"]})
            if _assinatura(pedido["provedor"], identidade) != pedido["assinatura"]:
                raise ValueError("Identidade ou fornecedor mudou. Revise o pedido anterior.")
        vinculada = pedido.get("opcao_id")
        if vinculada or pedido.get("estado") == "concluido":
            selecao = _opcao(caso, cid, decisoes)
            if vinculada is None:
                # Um lote anterior só permite inferência quando a descoberta teve uma única opção.
                antigas = [r for r in caso["provedor"] if r["candidato_id"] == cid]
                vinculada = antigas[0]["id"] if len(antigas) == 1 else None
            if not selecao or selecao["id"] != vinculada:
                raise ValueError("A opção confirmada diverge do contato solicitado.")


def _autorizado(marca):
    return marca.get("Confirmado") == "sim" and marca.get("Autorizar consulta paga") == "sim"


def _exigir_contrato(provedor):
    nome = getattr(provedor, "nome", None)
    identificadores = getattr(provedor, "identificadores", None)
    if (not isinstance(nome, str) or not nome.strip()
            or not isinstance(identificadores, (set, frozenset, list, tuple))
            or not all(i in ("cpf", "cnpj", "nome") for i in identificadores)):
        raise ProvedorIncompativel("Identificação ou capacidades do provedor inválidas.")
    if getattr(provedor, "descoberta_separada", False) is not True:
        raise ProvedorIncompativel("Provedor sem descoberta separada de contatos.")
    try:
        for nome in ("identificar", "obter_contatos"):
            inspect.signature(getattr(provedor, nome)).bind("identidade", requisicao="chave")
    except (ValueError, TypeError, AttributeError):
        raise ProvedorIncompativel("Provedor sem suporte à identificação das requisições.") from None


def _iniciar(pedido, etapa, gravar):
    chaves = pedido.setdefault("chaves_requisicao", {})
    if etapa not in chaves:
        chaves[etapa] = uuid4().hex
    pedido.update(estado="incerto", etapa=etapa, requisicao=chaves[etapa], iniciado_em=_momento())
    gravar()
    return pedido["requisicao"]


def _registrar_resposta(caso, cid, pedido, resposta):
    if pedido["etapa"] == "identificar":
        opcoes = _opcoes(resposta, cid)
        caso["provedor"].extend(opcoes)
        pedido["estado"] = "identificado" if opcoes else "sem_resultados"
        return
    if pedido["etapa"] != "obter_contatos" or not isinstance(resposta, list):
        raise ValueError("Resposta de contatos inválida.")
    contatos = {}
    for item in resposta:
        tipo, valor = item["tipo"], item["valor"]
        if tipo not in {"telefone", "WhatsApp", "e-mail", "endereço"} or not isinstance(valor, str) or not valor.strip():
            raise ValueError("Contato recebido inválido.")
        data_fonte = item.get("data_fonte") or ""
        if not isinstance(data_fonte, str):
            raise ValueError("Data do contato inválida.")
        chave = _chave(cid, pedido["opcao_id"], tipo, valor.strip())
        contatos[chave] = dict(id=chave, candidato_id=cid, origem=pedido["provedor"],
                               opcao_id=pedido["opcao_id"], id_externo=pedido["id_externo"],
                               requisicao=pedido["requisicao"], tipo=tipo, valor=valor.strip(),
                               data_fonte=data_fonte, data_consulta=pedido["iniciado_em"])
    caso["contatos"].extend(contatos.values())
    pedido.update(estado="concluido", concluido_em=_momento())


def _executar(caso, cid, pedido, etapa, operacao, argumento, gravar):
    requisicao = _iniciar(pedido, etapa, gravar)
    try:
        resposta = operacao(argumento, requisicao=requisicao)
        _registrar_resposta(caso, cid, pedido, resposta)
    except Exception:
        raise ValueError("Resultado pago incerto. Conciliar com o fornecedor antes de repetir.") from None
    gravar()


def conciliar_pedido(caso, decisoes, requisicao, resultado, resposta=None):
    """Registra o resultado verificado com o fornecedor sem disparar nova operação."""
    encontrados = [(cid, p) for cid, p in caso.get("pedidos", {}).items()
                   if p.get("requisicao") == requisicao and p.get("estado") == "incerto"]
    if len(encontrados) != 1:
        raise ValueError("Requisição incerta não encontrada.")
    cid, pedido = encontrados[0]
    if resultado == "encerrar" and resposta is None:
        pedido["estado"] = "encerrado"
    elif pedido.get("etapa") not in {"identificar", "obter_contatos"}:
        raise ValueError("Pedido anterior sem identificação da operação. Confira o registro do fornecedor.")
    elif resultado == "nao_executado" and resposta is None:
        pedido["estado"] = "identificado" if pedido["etapa"] == "obter_contatos" else "pendente"
    elif resultado == "executado" and _autorizado(decisoes["candidatos"].get(cid, {})):
        validar_escolhas(caso, decisoes)
        try:
            _registrar_resposta(caso, cid, pedido, resposta)
        except (ValueError, TypeError, KeyError):
            raise ValueError("Resposta do fornecedor inválida para a conciliação.") from None
    else:
        raise ValueError("Resultado de conciliação ou autorização incompatível.")
    pedido.setdefault("conciliacoes", []).append(dict(requisicao=requisicao, resultado=resultado, data=_momento()))


def processar(caso, decisoes, provedor, gravar):
    """Persiste a intenção antes de cada operação paga e o resultado antes da próxima."""
    validar_escolhas(caso, decisoes)
    if provedor is None:
        return
    _exigir_contrato(provedor)
    alvos = {a["id"]: a for a in caso["alvos"]}
    pedidos = caso.setdefault("pedidos", {})
    for c in caso["candidatos"]:
        cid = c["id"]
        marca = decisoes["candidatos"].get(cid, {})
        if not _autorizado(marca):
            continue
        pedido = pedidos.setdefault(cid, {})
        if pedido.get("estado") == "incerto":
            raise ValueError("Pedido incerto. Conciliação manual necessária.")
        if pedido.get("estado") == "encerrado":
            continue
        identidade = _identificador(alvos[c["alvo_id"]], c, marca, provedor.identificadores)
        if not identidade:
            if "assinatura" in pedido:
                raise ValueError("Identidade ou fornecedor mudou. Revise o pedido anterior.")
            pedido["estado"] = "identificador_necessario"
            continue
        assinatura = _assinatura(provedor.nome, identidade)
        if pedido.get("assinatura", assinatura) != assinatura:
            raise ValueError("Identidade ou fornecedor mudou. Revise o pedido anterior.")
        tipo = next(k for k in ("cnpj", "cpf", "nome") if k in identidade)
        pedido.update(assinatura=assinatura, provedor=provedor.nome, tipo_identificador=tipo)
        if pedido.get("estado") in {"concluido", "sem_resultados"}:
            continue
        if pedido.get("estado") != "identificado":
            _executar(caso, cid, pedido, "identificar", provedor.identificar, identidade, gravar)
        escolhida = _opcao(caso, cid, decisoes)
        if escolhida and _autorizado(decisoes["candidatos"].get(cid, {})):
            pedido.update(opcao_id=escolhida["id"], id_externo=escolhida["id_externo"])
            _executar(caso, cid, pedido, "obter_contatos", provedor.obter_contatos, escolhida["id_externo"], gravar)
