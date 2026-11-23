import hashlib
import json
import os
import tempfile
from datetime import datetime, timezone
from html import escape
from pathlib import Path

from .cliente import FalhaConsulta
from .cnj import formatar, normalizar, url_consulta
from .pagina import VERSAO_EXTRATOR, diagnostico, extrair, extrair_movimentacoes, link_detalhe, url_movimentacoes


def agora():
    return datetime.now(timezone.utc).isoformat()


def gravar_json(caminho, valor):
    caminho = Path(caminho)
    caminho.parent.mkdir(parents=True, exist_ok=True)
    fd, temporario = tempfile.mkstemp(dir=caminho.parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(valor, f, ensure_ascii=False, indent=2)
            f.write("\n")
        os.replace(temporario, caminho)
    finally:
        Path(temporario).unlink(missing_ok=True)


def posicoes(texto):
    valores = []
    for parte in texto.split(","):
        pedacos = parte.strip().split("-")
        if len(pedacos) == 1:
            valores.append(int(pedacos[0]))
        elif len(pedacos) == 2:
            a, b = map(int, pedacos)
            if b < a or b - a > 9:
                raise ValueError("Selecione no máximo 10 posições em ordem crescente por intervalo.")
            valores.extend(range(a, b + 1))
        else:
            raise ValueError("Use posições como 1-10 ou 1,3,5,8.")
    if not 1 <= len(valores) <= 10 or min(valores) < 1 or len(set(valores)) != len(valores):
        raise ValueError("Escolha de 1 a 10 posições positivas, sem repetir.")
    return valores


def selecionar(planilha, escolhidas):
    from openpyxl import load_workbook

    planilha = Path(planilha).resolve()
    wb = load_workbook(planilha, read_only=True, data_only=True)
    try:
        if "Casos" not in wb.sheetnames:
            raise ValueError("A planilha não tem a aba Casos.")
        linhas = iter(wb["Casos"].values)
        cabecalho = next(linhas, ())
        if not {"#", "Processo", "Pontos"}.issubset(cabecalho):
            raise ValueError("A aba Casos precisa das colunas #, Processo e Pontos.")
        candidatos = {}
        for valores in linhas:
            row = dict(zip(cabecalho, valores))
            if row["#"] in escolhidas:
                candidatos[row["#"]] = {
                    "numero_processo": normalizar(str(row["Processo"])),
                    "posicao_original": row["#"], "pontuacao_original": row["Pontos"],
                }
        faltam = set(escolhidas) - candidatos.keys()
        if faltam:
            raise ValueError(f"Posições não encontradas: {sorted(faltam)}")
        casos = [candidatos[n] for n in escolhidas]
        validar_casos(casos)
        return {"versao": 1, "selecionado_em": agora(), "origem_planilha": str(planilha), "casos": casos}
    finally:
        wb.close()


def validar_casos(casos):
    if not isinstance(casos, list) or not 1 <= len(casos) <= 10:
        raise ValueError("O lote deve conter de 1 a 10 casos.")
    numeros = [normalizar(c["numero_processo"]) for c in casos]
    if len(set(numeros)) != len(numeros):
        raise ValueError("Há processos repetidos no lote.")
    for c, n in zip(casos, numeros):
        c["numero_processo"] = n


def ler_selecao(caminho):
    dados = json.loads(Path(caminho).read_text(encoding="utf-8"))
    validar_casos(dados["casos"])
    return dados


def salvar_pagina(pasta, nome, html):
    pasta.mkdir(parents=True, exist_ok=True)
    # Texto, não HTML executável: o relatório só apresenta conteúdo escapado.
    conteudo = html.encode("utf-8")
    (pasta / nome).write_bytes(conteudo)
    return {"arquivo": nome, "sha256": hashlib.sha256(conteudo).hexdigest()}


def consultar_caso(caso, cliente, pasta):
    n = caso["numero_processo"]
    url = url_consulta(n)
    resultado = {**caso, "consultado_em": agora(), "fonte": "TJSP e-SAJ — consulta pública de 1º grau", "url_consulta": url, "url_pagina": url, "evidencias": []}
    try:
        html = cliente.get(url)
        resultado["evidencias"].append(salvar_pagina(pasta, "consulta.html.txt", html))
        extraido = extrair(html, n)
        if extraido["status"] == "layout_nao_reconhecido":
            detalhe = link_detalhe(html, n)
            if detalhe:
                html = cliente.get(detalhe)
                resultado["url_pagina"] = detalhe
                resultado["evidencias"].append(salvar_pagina(pasta, "detalhe.html.txt", html))
                extraido = extrair(html, n)
        resultado.update(extraido)
        if extraido.get("movimentacoes_status") == "aguardando_carregamento":
            url_mov = url_movimentacoes(html)
            if url_mov:
                resultado["url_movimentacoes"] = url_mov
                try:
                    fragmento = cliente.get(url_mov)
                    resultado["evidencias"].append(salvar_pagina(pasta, "movimentacoes.html.txt", fragmento))
                    movs = extrair_movimentacoes(fragmento)
                    resultado.update(movs)
                    if movs["movimentacoes_status"] == "primeira_pagina":
                        resultado["status"] = "coletado"
                    elif movs["movimentacoes_status"] in {"bloqueado", "captcha"}:
                        resultado["interromper_lote"] = movs["movimentacoes_status"]
                except FalhaConsulta as e:
                    resultado["movimentacoes_status"] = e.status
                    resultado["mensagem"] = str(e)
                    resultado["interromper_lote"] = e.status
    except FalhaConsulta as e:
        resultado.update(status=e.status, mensagem=str(e))
    gravar_json(pasta / "resultado.json", resultado)
    return resultado


PARAR = {"bloqueado", "captcha", "erro_rede", "erro_http", "redirecionamento_manual", "layout_nao_reconhecido"}


def rodar(selecao, cliente, saida):
    validar_casos(selecao["casos"])
    saida = Path(saida)
    saida.mkdir(parents=True, exist_ok=True)
    selecao_anterior = saida / "selecao.json"
    if selecao_anterior.exists():
        antiga = ler_selecao(selecao_anterior)
        if [c["numero_processo"] for c in antiga["casos"]] != [c["numero_processo"] for c in selecao["casos"]]:
            raise ValueError("A pasta de saída pertence a outra seleção. Use outra --saida.")
    resultados = []
    parar = None
    iniciou = False
    gravar_json(saida / "selecao.json", selecao)
    for caso in selecao["casos"]:
        n = caso["numero_processo"]
        pasta = saida / n
        cache = pasta / "resultado.json"
        anterior = None
        if cache.exists():
            try:
                anterior = json.loads(cache.read_text(encoding="utf-8"))
            except (ValueError, OSError):
                pass
        if anterior and anterior.get("status") in {"coletado", "coletado_parcial"} and anterior.get("numero_processo") == n and anterior.get("versao_extrator") == VERSAO_EXTRATOR:
            resultado = {**anterior, **caso, "reutilizado": True}
            gravar_json(cache, resultado)
        else:
            if not iniciou and not parar:
                try:
                    impedimento = diagnostico(cliente.iniciar())
                    if impedimento:
                        parar = impedimento
                except FalhaConsulta as e:
                    parar = e.status
                iniciou = True
            if parar:
                resultado = {**caso, "status": "pendente", "motivo": parar, "url_consulta": url_consulta(n)}
                gravar_json(cache, resultado)
            else:
                resultado = consultar_caso(caso, cliente, pasta)
                if resultado["status"] in PARAR:
                    parar = resultado["status"]
                if resultado.get("interromper_lote"):
                    parar = resultado["interromper_lote"]
        resultados.append(resultado)
        gravar_json(saida / "resumo.json", {"gerado_em": agora(), "resultados": resultados})
        relatorio(saida, resultados)
        print(f"Caso {len(resultados)}/{len(selecao['casos'])}: {resultado['status']}", flush=True)
    return resultados


def relatorio(saida, resultados):
    rotulos = {
        "coletado": "Informações coletadas", "coletado_parcial": "Capa coletada — movimentações pendentes", "pendente": "Pendente de consulta",
        "bloqueado": "Acesso bloqueado pelo site", "captcha": "Verificação humana necessária",
        "erro_rede": "Sem conexão com o TJSP", "erro_http": "Site indisponível",
        "layout_nao_reconhecido": "Página não reconhecida — conferir no navegador",
        "processo_divergente": "Número retornado diferente do selecionado",
        "nao_localizado": "Não localizado nesta consulta", "consultar_eproc": "Conferir no eproc",
        "redirecionamento_manual": "Site encaminhou para outro serviço — conferir no navegador",
    }
    blocos = []
    for r in resultados:
        n = r["numero_processo"]
        link = escape(url_consulta(n), quote=True)
        titulo = escape(formatar(n))
        status = escape(rotulos.get(r["status"], r["status"]))
        metadados = f"Posição original: {escape(str(r.get('posicao_original', '—')))} · Score original: {escape(str(r.get('pontuacao_original', '—')))}"
        detalhes = ""
        if r.get("campos"):
            detalhes += "<dl>" + "".join(f"<dt>{escape(k)}</dt><dd>{escape(str(v)) if v is not None else 'Não disponível nesta página'}</dd>" for k, v in r["campos"].items()) + "</dl>"
        if r.get("movimentacoes_status") == "primeira_pagina":
            detalhes += "<p>Movimentações: primeira página retornada pelo site. Pode haver páginas anteriores; confira o histórico completo no TJSP.</p>"
        elif r.get("status") == "coletado_parcial":
            detalhes += "<p>A capa foi coletada, mas as movimentações não foram carregadas. Use o botão Exibir movimentações na consulta do TJSP.</p>"
        for campo, rotulo in (("partes_linhas", "Partes exibidas"), ("movimentacoes_linhas", "Movimentações exibidas")):
            linhas = r.get(campo, [])
            detalhes += f"<h3>{rotulo} ({len(linhas)})</h3>"
            if linhas:
                detalhes += "<table>" + "".join("<tr>" + "".join(f"<td>{escape(c)}</td>" for c in row) + "</tr>" for row in linhas) + "</table>"
            else:
                detalhes += "<p>Não coletadas.</p>"
        motivo_original = str(r.get("motivo") or r.get("mensagem") or "")
        motivo = escape(rotulos.get(motivo_original, motivo_original))
        quando = escape(str(r.get("consultado_em", "Consulta não concluída")))
        alerta = '<p><strong>O histórico menciona eproc.</strong> Confira na Consulta Unificada se há movimentações mais recentes no outro sistema.</p>' if r.get("referencia_eproc") else ""
        blocos.append(f'<section><h2>{titulo}</h2><p>{metadados}</p><p>Status: <strong>{status}</strong> {motivo}</p>{alerta}<p>{quando}</p><p><a href="{link}" target="_blank" rel="noopener noreferrer">Consultar no TJSP</a> · <a href="{n}/resultado.json">Dados e origem</a></p><details><summary>Ver informações coletadas</summary>{detalhes}</details></section>')
    html = '''<!doctype html><html lang="pt-BR"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Aprofundamento dos casos</title><style>body{font:16px/1.5 system-ui;max-width:1100px;margin:32px auto;padding:0 20px;color:#202b35;background:#f8fafb}section{background:white;border:1px solid #ccd5dd;border-radius:8px;padding:20px;margin:20px 0}a{color:#075b9a}td{border-bottom:1px solid #ddd;padding:8px;vertical-align:top;overflow-wrap:anywhere}table{width:100%;border-collapse:collapse}dt{font-weight:bold}dd{margin-bottom:8px}summary{cursor:pointer}h2{font-size:1.15rem}</style><h1>Aprofundamento dos casos</h1><p>Segunda etapa de leitura. O score original foi preservado; nenhuma nova pontuação foi calculada.</p><p>Conteúdo público da página consultada, não os autos completos. Valor da causa não é saldo atualizado. Uma pendência ou campo ausente não significa inexistência de bens, dívida ou movimentações.</p>'''
    (Path(saida) / "relatorio.html").write_text(html + "".join(blocos) + "</html>", encoding="utf-8")


def importar(selecao, numero, pagina, saida):
    n = normalizar(numero)
    caso = next((c for c in selecao["casos"] if c["numero_processo"] == n), None)
    if caso is None:
        raise ValueError("O processo precisa estar na seleção.")
    pasta = Path(saida) / n
    html = Path(pagina).read_text(encoding="utf-8-sig")
    evidencia = salvar_pagina(pasta, "importada.html.txt", html)
    r = {**caso, **extrair(html, n), "consultado_em": agora(), "fonte": "HTML fornecido pelo usuário — conteúdo não consultado online", "url_consulta": url_consulta(n), "evidencias": [evidencia]}
    gravar_json(pasta / "resultado.json", r)
    resultados = []
    for c in selecao["casos"]:
        arquivo = Path(saida) / c["numero_processo"] / "resultado.json"
        resultados.append(json.loads(arquivo.read_text(encoding="utf-8")) if arquivo.exists() else {**c, "status": "pendente"})
    gravar_json(Path(saida) / "resumo.json", {"gerado_em": agora(), "resultados": resultados})
    relatorio(saida, resultados)
    return r


def reprocessar(saida):
    """Reextrai as respostas verificadas, sem rede nem alteração da data de consulta."""
    saida = Path(saida)
    selecao = ler_selecao(saida / "selecao.json")
    resultados = []
    for caso in selecao["casos"]:
        pasta = saida / caso["numero_processo"]
        r = json.loads((pasta / "resultado.json").read_text(encoding="utf-8"))
        if r.get("numero_processo") != caso["numero_processo"]:
            raise ValueError("Identidade do resultado diferente da seleção.")
        evidencias = {e["arquivo"]: e for e in r.get("evidencias", [])}

        def ler(nome):
            conteudo = (pasta / nome).read_bytes()
            if hashlib.sha256(conteudo).hexdigest() != evidencias[nome]["sha256"]:
                raise ValueError("Uma resposta salva mudou; reprocessamento interrompido.")
            return conteudo.decode("utf-8")

        principal = next((n for n in ("detalhe.html.txt", "consulta.html.txt", "importada.html.txt") if n in evidencias), None)
        if principal:
            extraido = extrair(ler(principal), caso["numero_processo"])
            if extraido["status"] in {"coletado", "coletado_parcial"}:
                r.update(extraido)
                if "movimentacoes.html.txt" in evidencias:
                    movs = extrair_movimentacoes(ler("movimentacoes.html.txt"))
                    r.update(movs)
                    if movs["movimentacoes_status"] == "primeira_pagina":
                        r["status"] = "coletado"
                r["reprocessado_em"] = agora()
                gravar_json(pasta / "resultado.json", r)
        resultados.append(r)
    gravar_json(saida / "resumo.json", {"gerado_em": agora(), "resultados": resultados})
    relatorio(saida, resultados)
    return resultados
