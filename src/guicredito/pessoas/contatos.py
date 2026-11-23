"""Passagem opcional de contatos. O piloto não instala nenhum fornecedor."""
import hashlib
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


def _opcoes(raw, cid):
    if not isinstance(raw, list):
        raise ValueError
    itens = []
    ids = set()
    for r in raw:
        externo = r["id"]
        if not isinstance(externo, str) or not externo or externo in ids:
            raise ValueError
        ids.add(externo)
        row_id = hashlib.sha256(json.dumps([cid, externo]).encode()).hexdigest()[:32]
        itens.append({"id": row_id, "id_externo": externo, "candidato_id": cid, "nome": r["nome"],
                      "indicios": {k: r[k] for k in ("cidade", "faixa_etaria") if isinstance(r.get(k), str)}})
    return itens


def _executar(pedido, gravar, chamada):
    pedido.update(estado="incerto", requisicao=uuid4().hex, iniciado_em=_momento())
    gravar()  # Registro durável antes de qualquer operação faturável.
    try:
        return chamada()
    except Exception:
        raise ValueError("Resultado pago incerto. Conciliar com o fornecedor antes de repetir.") from None


def processar(caso, decisoes, provedor, gravar):
    """A chamada gravar persiste o caso antes de cada despacho e depois de cada resultado."""
    if provedor is None:
        return
    if not all(callable(getattr(provedor, nome, None)) for nome in ("identificar", "obter_contatos")):
        raise ProvedorIncompativel("Provedor sem consultas separadas de identidade e contato.")
    alvos = {a["id"]: a for a in caso["alvos"]}
    pedidos = caso.setdefault("pedidos", {})
    for c in caso["candidatos"]:
        cid = c["id"]
        marca = decisoes["candidatos"].get(cid, {})
        if marca.get("Confirmado") != "sim" or marca.get("Autorizar consulta paga") != "sim":
            continue
        pedido = pedidos.setdefault(cid, {})
        if pedido.get("estado") == "incerto":
            raise ValueError("Pedido incerto. Conciliação manual necessária.")
        identidade = _identificador(alvos[c["alvo_id"]], c, marca, provedor.identificadores)
        if not identidade:
            if "assinatura" in pedido:
                raise ValueError("Identidade ou fornecedor mudou. Revise o pedido anterior.")
            pedido["estado"] = "identificador_necessario"
            continue
        assinatura = hashlib.sha256(json.dumps([provedor.nome, identidade], sort_keys=True).encode()).hexdigest()
        if pedido.get("assinatura", assinatura) != assinatura:
            raise ValueError("Identidade ou fornecedor mudou. Revise o pedido anterior.")
        pedido["assinatura"] = assinatura
        if pedido.get("estado") in {"concluido", "sem_resultados"}:
            continue
        if pedido.get("estado") != "identificado":
            opcoes = _executar(pedido, gravar, lambda: _opcoes(provedor.identificar(identidade), cid))
            caso["provedor"].extend(opcoes)
            pedido["estado"] = "identificado" if opcoes else "sem_resultados"
            gravar()
        opcoes = [r for r in caso["provedor"] if r["candidato_id"] == cid]
        if len(opcoes) > 1:
            opcoes = [r for r in opcoes if decisoes["provedor"].get(r["id"], {}).get("Confirmado") == "sim"]
        if len(opcoes) != 1:
            continue

        def obter():
            resposta = provedor.obter_contatos(opcoes[0]["id_externo"])
            if not isinstance(resposta, list):
                raise ValueError
            contatos = []
            for item in resposta:
                if item.get("tipo") not in {"telefone", "WhatsApp", "e-mail", "endereço"} or not isinstance(item.get("valor"), str):
                    raise ValueError
                contatos.append({"candidato_id": cid, "origem": provedor.nome, "tipo": item["tipo"],
                                 "valor": item["valor"], "data_fonte": item.get("data_fonte", ""), "data_consulta": _momento()})
            return contatos
        caso["contatos"].extend(_executar(pedido, gravar, obter))
        pedido.update(estado="concluido", concluido_em=_momento())
        gravar()
