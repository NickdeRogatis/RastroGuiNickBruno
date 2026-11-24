"""Coordena fontes, revisão e descarte de um lote, sem modificar as entradas."""
import copy
import hashlib
import json
import re
import secrets
from datetime import datetime, timezone
from hmac import compare_digest

from . import contatos as dados_pagos
from .evidencias import ErroPesquisaParcial, pesquisar_web, salvar_recorte
from .http import ErroGateway
from .lote import FORMATO, Lote, escrever_json, ler_json
from .planilha import gravar_planilha, ler_decisoes
from .relatorio import projetar_revisao, renderizar, renderizar_revisao

SEPARADOS = ("consultas", "contatos", "evidencias")


# Retorna a data e hora atuais em UTC no formato ISO para registrar operações.
def _agora():
    return datetime.now(timezone.utc).isoformat()


# Gera uma assinatura SHA-256 do objeto serializado em JSON com chaves ordenadas.
def _hash(obj):
    return hashlib.sha256(json.dumps(obj, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


# Reconstitui os casos e suas seções a partir do manifesto e dos arquivos do lote.
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


# Atualiza as decisões dos candidatos e publica os dados, a planilha e os relatórios do lote.
def _salvar(lote, dados, decisoes):
    for caso in dados["casos"]:
        for candidato in caso["candidatos"]:
            marca = decisoes.get("candidatos", {}).get(candidato["id"])
            if marca is not None:
                anterior = candidato.get("decisao", {})
                atual = {k: marca.get(k, "") for k in ("Confirmado", "Autorizar consulta paga")}
                if any(anterior.get(k) != v for k, v in atual.items()):
                    candidato["decisao"] = {**atual, "lida_em": _agora()}

    # Monta os arquivos do lote, incluindo recortes de evidências e páginas de revisão.
    def montar(base):
        m = {k: dados[k] for k in ("lote", "origem", "suprimidas")}
        m.update(formato=FORMATO, numeros=[c["processo"] for c in dados["casos"]])
        escrever_json(base / "manifesto.json", m)
        for caso in dados["casos"]:
            pasta = base / caso["processo"]
            lote.caminho(f"{caso['processo']}/pessoas.json")
            pasta.mkdir(mode=0o700)
            escrever_json(pasta / "pessoas.json", {k: v for k, v in caso.items() if k not in SEPARADOS})
            for ev in caso["evidencias"]:
                trecho = ev.get("trecho", "")
                if trecho:
                    ev.update(salvar_recorte(pasta, ev, trecho))
            for secao in SEPARADOS:
                escrever_json(pasta / f"{secao}.json", caso[secao])
        gravar_planilha(base / "pessoas.xlsx", dados, decisoes)
        (base / "relatorio.html").write_text(renderizar(dados, decisoes), encoding="utf-8")
        fichas = projetar_revisao(dados, decisoes)
        (base / "revisao.html").write_text(renderizar_revisao(fichas), encoding="utf-8")
    lote.publicar(montar)


# Cria um lote a partir de uma cópia da entrada, inicializando seções e rótulos aleatórios.
def _novo(entrada, origem):
    casos = copy.deepcopy(entrada.casos)
    aliases = list(range(1, len(casos) + 1))
    secrets.SystemRandom().shuffle(aliases)
    for ordem, (c, alias) in enumerate(zip(casos, aliases, strict=True)):
        c.update(rotulo=f"Caso {alias:02}", ordem=ordem)
        for campo in (*SEPARADOS, "provedor", "oab", "candidatos", "limitacoes"):
            c.setdefault(campo, [])
    return {"lote": secrets.token_hex(8), "origem": origem, "casos": casos, "suprimidas": []}


# Acrescenta registros ao destino sem duplicar identificadores já presentes.
def _unir(destino, itens):
    ids = {r["id"] for r in destino}
    for r in itens:
        if r["id"] not in ids:
            destino.append(r)
            ids.add(r["id"])


# Consulta OAB ou CNPJ conforme o alvo e incorpora candidatos, evidências e o estado da consulta.
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


# Obtém ou cria o registro que acompanha a consulta de um alvo em uma fonte.
def _consulta(caso, alvo, fonte):
    chave = _hash([alvo["id"], fonte])
    for item in caso["consultas"]:
        if item.get("id") == chave:
            return item
    item = dict(id=chave, alvo_id=alvo["id"], fonte=fonte, estado="nao_consultado",
                motivo="Aguardando processamento.", data=_agora())
    caso["consultas"].append(item)
    return item


# Executa a pesquisa Hermes para o alvo elegível, salvando o estado e preservando resultados parciais.
def _web(caso, alvo, cliente, http, gravar, retomar_leituras=False):
    if alvo["tipo"] == "PJ" and alvo["papel"] == "devedor":
        return
    consulta = _consulta(caso, alvo, "Hermes")
    if consulta["estado"] in {"sem_resultados", "consultado"}:
        return
    registro = next((q for q in caso["consultas"] if q["alvo_id"] == alvo["id"]
                     and q["fonte"] == "web_search" and isinstance(q.get("urls"), list)), None)
    if consulta["estado"] in ("incerto", "leitura_pendente") and registro is None:
        raise ValueError("Pesquisa interrompida após possível envio. Confira o lote antes de nova consulta.")
    if consulta["estado"] == "leitura_pendente" and not retomar_leituras:
        raise ValueError("Busca salva. Use --retomar-leituras para continuar sem repetir a busca.")
    if cliente is None:
        if registro is None:
            consulta.update(estado="nao_configurado", motivo="Busca não configurada.")
        return
    if registro is None:
        consulta.update(estado="incerto", motivo="Pesquisa iniciada.", data=_agora())
        gravar()

    def guardar_busca(q):
        _unir(caso["consultas"], [q])
        consulta.update(estado="leitura_pendente", motivo="Busca salva. Leitura pendente.", data=_agora())
        gravar()

    def incorporar(resposta):
        for k in ("candidatos", "evidencias", "contatos"):
            _unir(caso[k], resposta.get(k, []))
        por_id = {q["id"]: q for q in caso["consultas"]}
        for q in resposta["consultas"]:
            if q["id"] in por_id:
                por_id[q["id"]].update(q)
            else:
                caso["consultas"].append(q)
            if q.get("concluida"):
                caso["consultas"][:] = [r for r in caso["consultas"]
                    if not (r["fonte"] == "leitura Hermes" and r["alvo_id"] == alvo["id"]
                            and r.get("url") == q.get("url") and r["estado"] == "interrompido")]

    prontas = {q["url"] for q in caso["consultas"] if q["alvo_id"] == alvo["id"] and q.get("concluida")}
    try:
        resposta = pesquisar_web(alvo, cliente, http, registrar_busca=guardar_busca,
                                 registro=registro, paginas_concluidas=prontas)
    except ErroPesquisaParcial as erro:
        incorporar(erro.parcial)
        raise ValueError("Busca salva. Use --retomar-leituras para continuar sem repetir a busca.") from None
    except Exception:
        raise ValueError("Falha na pesquisa Hermes. Resultado incerto. Lote parcial preservado.") from None
    incorporar(resposta)
    estado = resposta["consultas"][0]["estado"]
    consulta.update(estado=estado, motivo="", data=_agora())
    gravar()


# Cria ou retoma o lote, coordena as pesquisas dos casos ativos e salva resultados e conferências.
def pesquisar(entrada, config, servicos, saida, *, retomar_leituras=False):
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
        for caso in ativos:
            for alvo in caso["alvos"]:
                if alvo["papel"] == "advogado":
                    _consulta(caso, alvo, "OAB")
                elif alvo["tipo"] == "PJ" or alvo["papel"] == "devedor":
                    _consulta(caso, alvo, "CNPJ")
                if (alvo["tipo"], alvo["papel"]) != ("PJ", "devedor"):
                    _consulta(caso, alvo, "Hermes")
        cliente = http = None
        indice = servicos.get("cnpj")
        if indice is None and config.indice_cnpj is not None:
            indice = IndiceCNPJ(config.indice_cnpj)
        oab = servicos.get("oab", consulta_oab)
        salvar = lambda: _salvar(lote, dados, decisoes)
        try:
            if config.busca and ativos:
                if "hermes" in servicos:
                    cliente, http = servicos["hermes"], servicos["http"]
                else:
                    cliente, http = criar_servicos_web(config)
                cliente.exigir_politica()
                if cliente.verificar():
                    raise ErroGateway("Falha na configuração do gateway.")
            for caso in ativos:
                for alvo in caso["alvos"]:
                    _registros(caso, alvo, indice, oab)
                    _web(caso, alvo, cliente, http, salvar, retomar_leituras)
        except (ValueError, ErroGateway):
            salvar()
            raise
        _incorporar_conferencias(dados, decisoes)
        salvar()
        return dados


# Lê as decisões da planilha, valida CPFs e processa consultas de contatos quando há provedor.
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


# Seleciona os casos marcados para descarte e gera um código vinculado à versão da planilha.
def _previa(dados, decisoes, marca_excel):
    marcados = [c for c in dados["casos"] if decisoes["casos"][c["processo"]].get("Descartar") == "sim"]
    codigo = _hash([dados["lote"], marca_excel, [c["ordem"] for c in marcados]])[:24]
    return marcados, {"rotulos": [c["rotulo"] for c in marcados], "codigo": codigo}


# Retorna os rótulos dos casos marcados para descarte e o código necessário para confirmá-lo.
def prever_descarte(pasta):
    with Lote(pasta) as lote:
        dados = _carregar(lote)
        d = ler_decisoes(lote.caminho("pessoas.xlsx"), dados, para_descarte=True)
        return _previa(dados, d, lote.marca_excel)[1]


# Valida o código da prévia e remove os casos marcados e os registros relacionados antes de salvar.
def confirmar_descarte(pasta, codigo):
    with Lote(pasta) as lote:
        dados = _carregar(lote)
        d = ler_decisoes(lote.caminho("pessoas.xlsx"), dados, para_descarte=True)
        marcados, previa = _previa(dados, d, lote.marca_excel)
        if not marcados or not compare_digest(previa["codigo"].encode(), codigo.encode()):
            raise ValueError("Prévia vencida ou incompatível. Confira novamente as marcações.")
        suprimir = {c["ordem"] for c in marcados}
        numeros = {c["processo"] for c in marcados}
        dados["casos"] = [c for c in dados["casos"] if c["ordem"] not in suprimir]
        for caso in dados["casos"]:
            relacionados = {c["id"] for c in caso["candidatos"] if c.get("processo_referenciado") in numeros}
            caso["candidatos"] = [c for c in caso["candidatos"] if c["id"] not in relacionados]
            for secao in ("evidencias", "contatos", "provedor"):
                caso[secao] = [r for r in caso[secao] if r.get("candidato_id") not in relacionados]
            for cid in relacionados:
                caso.get("pedidos", {}).pop(cid, None)
        dados["suprimidas"] = sorted(set(dados["suprimidas"]) | suprimir)
        _salvar(lote, dados, d)
        return len(marcados)


# Incorpora conferências manuais completas da OAB aos candidatos e às evidências dos casos ativos.
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


# Valida conferências OAB em JSON, associa-as aos alvos do lote e salva as decisões e os registros.
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


# Resolve uma requisição de contatos incerta com o resultado conferido e salva o lote sem nova consulta.
def conciliar_contatos(pasta, requisicao, resultado, arquivo=None):
    """Incorpora a conferência de Nick no pedido incerto sem chamar o provedor."""
    with Lote(pasta) as lote:
        dados = _carregar(lote)
        decisoes = ler_decisoes(lote.caminho("pessoas.xlsx"), dados)
        casos = [c for c in dados["casos"] if decisoes["casos"][c["processo"]].get("Descartar") != "sim"
                 and any(p.get("requisicao") == requisicao and p.get("estado") == "incerto"
                         for p in c.get("pedidos", {}).values())]
        if len(casos) != 1:
            raise ValueError("Requisição incerta não encontrada.")
        if (arquivo is not None) != (resultado == "executado"):
            raise ValueError("Informe o arquivo da resposta apenas para a operação executada.")
        resposta = ler_json(arquivo) if arquivo is not None else None
        dados_pagos.conciliar_pedido(casos[0], decisoes, requisicao, resultado, resposta)
        _salvar(lote, dados, decisoes)
