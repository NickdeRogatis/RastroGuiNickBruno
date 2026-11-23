"""Coordena fontes, revisão e descarte de um lote, sem modificar as entradas."""
import copy
import hashlib
import json
import re
import secrets
from datetime import datetime, timezone
from hmac import compare_digest

from . import contatos as dados_pagos
from .lote import FORMATO, Lote, escrever_json, ler_json
from .planilha import gravar_planilha, ler_decisoes
from .relatorio import projetar_revisao, renderizar, renderizar_revisao

SEPARADOS = ("consultas", "contatos", "evidencias")


def _agora():
    return datetime.now(timezone.utc).isoformat()


def _hash(obj):
    return hashlib.sha256(json.dumps(obj, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def _carregar(lote):
    m = lote.manifesto()
    if not m:
        return None
    casos = []
    for numero in m["numeros"]:
        c = ler_json(lote.caminho(f"{numero}/pessoas.json"))
        if c.get("processo") != numero:
            raise ValueError("Identidade do caso diverge do manifesto.")
        for secao in SEPARADOS:
            c[secao] = ler_json(lote.caminho(f"{numero}/{secao}.json"))
        casos.append(c)
    return {**{k: m[k] for k in ("lote", "origem", "suprimidas")}, "casos": casos}


def _salvar(lote, dados, decisoes):
    for caso in dados["casos"]:
        for candidato in caso["candidatos"]:
            marca = decisoes.get("candidatos", {}).get(candidato["id"])
            if marca is not None:
                anterior = candidato.get("decisao", {})
                atual = {k: marca.get(k, "") for k in ("Confirmado", "Autorizar consulta paga")}
                if any(anterior.get(k) != v for k, v in atual.items()):
                    candidato["decisao"] = {**atual, "lida_em": _agora()}

    def montar(base):
        m = {k: dados[k] for k in ("lote", "origem", "suprimidas")}
        m.update(formato=FORMATO, numeros=[c["processo"] for c in dados["casos"]])
        escrever_json(base / "manifesto.json", m)
        for caso in dados["casos"]:
            pasta = base / caso["processo"]
            lote.caminho(f"{caso['processo']}/pessoas.json")
            pasta.mkdir(mode=0o700)
            escrever_json(pasta / "pessoas.json", {k: v for k, v in caso.items() if k not in SEPARADOS})
            for secao in SEPARADOS:
                escrever_json(pasta / f"{secao}.json", caso[secao])
            for ev in caso["evidencias"]:
                trecho = ev.get("trecho", "")
                if trecho:
                    sha = hashlib.sha256(trecho.encode()).hexdigest()
                    (pasta / f"evidencia-{sha}.txt").write_text(trecho, encoding="utf-8")
        gravar_planilha(base / "pessoas.xlsx", dados, decisoes)
        (base / "relatorio.html").write_text(renderizar(dados, decisoes), encoding="utf-8")
        fichas = projetar_revisao(dados, decisoes)
        (base / "revisao.html").write_text(renderizar_revisao(fichas), encoding="utf-8")
    lote.publicar(montar)


def _novo(entrada, origem):
    casos = copy.deepcopy(entrada.casos)
    aliases = list(range(1, len(casos) + 1))
    secrets.SystemRandom().shuffle(aliases)
    for ordem, (c, alias) in enumerate(zip(casos, aliases, strict=True)):
        c.update(rotulo=f"Caso {alias:02}", ordem=ordem)
        for campo in (*SEPARADOS, "provedor", "oab", "candidatos", "limitacoes"):
            c.setdefault(campo, [])
    return {"lote": secrets.token_hex(8), "origem": origem, "casos": casos, "suprimidas": []}


def _unir(destino, itens):
    ids = {r["id"] for r in destino}
    for r in itens:
        if r["id"] not in ids:
            destino.append(r)
            ids.add(r["id"])


def _registros(caso, alvo, indice, oab):
    if alvo["papel"] == "advogado":
        from .oab import CaptchaOAB, consulta_oab

        consulta = _consulta(caso, alvo, "OAB")
        if consulta["estado"] in {"consultado", "sem_resultados", "nao_verificado"}:
            return
        linha = consulta_oab(alvo)
        try:
            consultar = getattr(oab, "consultar", oab)
            resposta = consultar(alvo)
            itens = [resposta] if isinstance(resposta, dict) else resposta
            if not isinstance(itens, list) or any(r.get("alvo_id") != alvo["id"] for r in itens):
                raise ValueError("Resposta OAB incompatível com o alvo.")
            if len(itens) == 1 and itens[0].get("estado") in {"pendente", "captcha", "nao_verificado"}:
                linha.update(itens[0])
                linha["estado"] = "pendente"
                estado = "nao_verificado"
            else:
                estado = "consultado" if itens else "sem_resultados"
                linha.update(estado=estado, motivo="")
                for item in itens:
                    candidato = dict(item)
                    evidencias = candidato.pop("evidencias", [])
                    _unir(caso["evidencias"], evidencias)
                    _unir(caso["candidatos"], [candidato])
        except CaptchaOAB:
            estado = "nao_verificado"
            linha.update(estado="pendente", motivo="captcha")
        except Exception:
            consulta.update(estado="interrompido", motivo="Falha no cadastro OAB.", data=_agora())
            raise ValueError("Cadastro OAB indisponível.") from None
        _unir(caso["oab"], [linha])
        consulta.update(estado=estado, motivo=linha["motivo"], data=_agora())
        return
    if alvo["tipo"] != "PJ" and alvo["papel"] != "devedor":
        return
    consulta = _consulta(caso, alvo, "CNPJ")
    if consulta["estado"] in ("consultado", "sem_resultados"):
        return
    if indice is None:
        consulta.update(estado="nao_configurado", motivo="Índice CNPJ ausente.")
        return
    try:
        rows = indice.consultar(alvo)
    except FileNotFoundError:
        consulta.update(estado="nao_configurado", motivo="Índice CNPJ ausente.")
        return
    except Exception:
        consulta.update(estado="interrompido", motivo="Falha no índice CNPJ.")
        raise ValueError("Índice CNPJ indisponível.") from None
    for row in rows:
        row = dict(row)
        evidencias = row.pop("evidencias", [])
        _unir(caso["evidencias"], evidencias)
        _unir(caso["candidatos"], [row])
    consulta.update(estado="consultado" if rows else "sem_resultados", data=_agora(), motivo="")


def _consulta(caso, alvo, fonte):
    chave = _hash([alvo["id"], fonte])
    for item in caso["consultas"]:
        if item.get("id") == chave:
            return item
    item = dict(id=chave, alvo_id=alvo["id"], fonte=fonte, estado="nao_consultado", data=_agora())
    caso["consultas"].append(item)
    return item


def _web(caso, alvo, cliente, http, gravar):
    if alvo["tipo"] == "PJ" and alvo["papel"] == "devedor":
        return
    consulta = _consulta(caso, alvo, "Hermes")
    if consulta["estado"] in {"sem_resultados", "consultado"}:
        return
    if consulta["estado"] == "incerto":
        raise ValueError("Pesquisa interrompida após possível envio. Confira o lote antes de nova consulta.")
    if cliente is None:
        consulta.update(estado="nao_configurado", motivo="Busca não configurada.")
        return
    from .evidencias import pesquisar_web
    consulta.update(estado="incerto", motivo="Pesquisa iniciada.", data=_agora())
    gravar()
    try:
        resposta = pesquisar_web(alvo, cliente, http)
        for k in ("candidatos", "evidencias", "contatos"):
            _unir(caso[k], resposta.get(k, []))
        caso["consultas"].extend(resposta["consultas"])
    except Exception:
        raise ValueError("Falha na pesquisa Hermes. Resultado incerto. Lote parcial preservado.") from None
    estado = resposta["consultas"][0]["estado"]
    consulta.update(estado=estado, motivo="", data=_agora())
    gravar()


def pesquisar(entrada, config, servicos, saida):
    from .cnpj import IndiceCNPJ
    from .oab import consulta_oab
    from .hermes import criar_servicos_web
    if config.diagnosticos:
        raise ValueError("Configuração inválida: " + ", ".join(config.diagnosticos))
    assinatura = _hash([entrada.hashes, [(c["processo"], c["posicao_original"]) for c in entrada.casos]])
    with Lote(saida, criar=True) as lote:
        anterior = _carregar(lote)
        if anterior and anterior["origem"] != assinatura:
            raise ValueError("A entrada mudou. Escolha outro lote.")
        dados = anterior or _novo(entrada, assinatura)
        decisoes = ler_decisoes(lote.caminho("pessoas.xlsx"), anterior) if anterior else {}
        ativos = [c for c in dados["casos"] if
                  decisoes.get("casos", {}).get(c["processo"], {}).get("Descartar") != "sim"]
        cliente = http = None
        if config.busca and ativos:
            if "hermes" in servicos:
                cliente, http = servicos["hermes"], servicos["http"]
            else:
                cliente, http = criar_servicos_web(config)
            cliente.exigir_politica()  # falha antes de enviar qualquer nome ou iniciar uma fonte
            falhas = cliente.verificar()
            if falhas:
                raise ValueError("Falha na configuração do gateway: " + ", ".join(falhas))
        indice = servicos.get("cnpj")
        if indice is None and config.indice_cnpj is not None:
            indice = IndiceCNPJ(config.indice_cnpj)
        oab = servicos.get("oab", consulta_oab)
        salvar = lambda: _salvar(lote, dados, decisoes)
        try:
            for caso in ativos:
                for alvo in caso["alvos"]:
                    _registros(caso, alvo, indice, oab)
                    _web(caso, alvo, cliente, http, salvar)
        except ValueError:
            salvar()
            raise
        _incorporar_conferencias(dados, decisoes)
        salvar()
        return dados


def contatos(pasta, provedor=None):
    with Lote(pasta) as lote:
        dados = _carregar(lote)
        d = ler_decisoes(lote.caminho("pessoas.xlsx"), dados)
        _incorporar_conferencias(dados, d)
        for marca in d["candidatos"].values():
            if marca.get("CPF"):
                dados_pagos.validar_cpf(marca["CPF"])
        salvar = lambda: _salvar(lote, dados, d)
        if provedor is None:
            salvar()
            return {"estado": "nao_configurado", "casos": len(dados["casos"])}
        for caso in dados["casos"]:
            if d["casos"][caso["processo"]].get("Descartar") != "sim":
                dados_pagos.processar(caso, d, provedor, salvar)
        salvar()
        return {"estado": "concluido", "casos": len(dados["casos"])}


def _previa(dados, decisoes, marca_excel):
    marcados = [c for c in dados["casos"] if decisoes["casos"][c["processo"]].get("Descartar") == "sim"]
    codigo = _hash([dados["lote"], marca_excel, [c["ordem"] for c in marcados]])[:24]
    return marcados, {"rotulos": [c["rotulo"] for c in marcados], "codigo": codigo}


def prever_descarte(pasta):
    with Lote(pasta) as lote:
        dados = _carregar(lote)
        d = ler_decisoes(lote.caminho("pessoas.xlsx"), dados)
        return _previa(dados, d, lote.marca_excel)[1]


def confirmar_descarte(pasta, codigo):
    with Lote(pasta) as lote:
        dados = _carregar(lote)
        d = ler_decisoes(lote.caminho("pessoas.xlsx"), dados)
        marcados, previa = _previa(dados, d, lote.marca_excel)
        if not marcados or not compare_digest(previa["codigo"].encode(), codigo.encode()):
            raise ValueError("Prévia vencida ou incompatível. Confira novamente as marcações.")
        suprimir = {c["ordem"] for c in marcados}
        dados["casos"] = [c for c in dados["casos"] if c["ordem"] not in suprimir]
        dados["suprimidas"] = sorted(set(dados["suprimidas"]) | suprimir)
        _salvar(lote, dados, d)
        return len(marcados)


def _incorporar_conferencias(dados, decisoes):
    from .oab import importar_manual
    for caso in dados["casos"]:
        if decisoes.get("casos", {}).get(caso["processo"], {}).get("Descartar") == "sim":
            continue
        for row in caso["oab"]:
            manual = decisoes.get("oab", {}).get(row["id"], {})
            if not manual.get("Dados profissionais conferidos") or not manual.get("Data da conferência"):
                continue  # Conservar preenchimento parcial no Excel.
            inscricao = manual.get("OAB/UF conferida") or f"{row.get('oab', '')}/{row.get('uf', '')}"
            partes = re.split(r"[/\s-]+", inscricao.upper().strip())
            if len(partes) != 2:
                raise ValueError("Inscrição OAB manual inválida.")
            oab, uf = partes if partes[0][:1].isdigit() else partes[::-1]
            registro = importar_manual({
                "alvo_id": row["alvo_id"], "nome": row["nome"], "url": row["url"], "oab": oab, "uf": uf,
                "dados_profissionais": manual["Dados profissionais conferidos"], "data": manual["Data da conferência"],
            })
            evidencias = registro.pop("evidencias")
            _unir(caso["evidencias"], evidencias)
            anterior = next((c for c in caso["candidatos"] if c["id"] == registro["id"]), None)
            if anterior is None:
                caso["candidatos"].append(registro)
            else:
                anterior.update(registro)


def importar_oab(pasta, arquivo):
    """Conferência em JSON equivale à edição das três colunas OAB no Excel."""
    from .oab import importar_manual
    with Lote(pasta) as lote:
        dados = _carregar(lote)
        decisoes = ler_decisoes(lote.caminho("pessoas.xlsx"), dados)
        permitidos = {row["alvo_id"]: row for c in dados["casos"]
                      if decisoes["casos"][c["processo"]].get("Descartar") != "sim" for row in c["oab"]}
        bruto = ler_json(arquivo)
        registros = bruto if isinstance(bruto, list) else [bruto]
        vistos = set()
        for item in registros:
            validado = importar_manual(item)
            chave = validado["alvo_id"]
            row = permitidos.get(chave)
            if chave in vistos or not row or row["nome"] != validado["nome"] or row["url"] != validado["url"]:
                raise ValueError("OAB sem correspondência com o alvo do lote.")
            vistos.add(chave)
            prof = validado["dados_profissionais"]
            decisoes["oab"][row["id"]] = {
                "OAB/UF conferida": f"{validado['oab']}/{validado['uf']}",
                "Dados profissionais conferidos": prof if isinstance(prof, str) else json.dumps(prof, ensure_ascii=False),
                "Data da conferência": validado["data"][:10],
            }
        _incorporar_conferencias(dados, decisoes)
        _salvar(lote, dados, decisoes)
        return len(vistos)
