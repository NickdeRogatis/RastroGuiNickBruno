"""Descoberta, verificação de integridade e consulta avulsa de capas do TJSP.

Reaproveita capas compatíveis já existentes em ``saida/aprofundamento/``
(somente leitura) e em ``saida/DG__mais_de_600_mil/capas/``. Novas consultas
avulsas usam o cliente e o extrator do pacote ``aprofundamento`` e gravam
evidências exclusivamente em ``saida/DG__mais_de_600_mil/capas/<cnj>/``.
"""

import hashlib
import json
import os
import re
import tempfile
from collections.abc import Iterable
from pathlib import Path

from guicredito.aprofundamento.cliente import FalhaConsulta
from guicredito.aprofundamento.cnj import normalizar as normalizar_cnj_tjsp
from guicredito.aprofundamento.cnj import url_consulta
from guicredito.aprofundamento.fluxo import PARAR, agora, gravar_json
from guicredito.aprofundamento.pagina import extrair, link_detalhe
from guicredito.dg_mais_de_600_mil.modelos import (
    MotivoPendencia,
    StatusValor,
    VerificacaoValor,
)
from guicredito.dg_mais_de_600_mil.valores import acima_do_corte, interpretar_valor_causa

_ARQUIVOS_CAPA_PRIORIDADE = ("detalhe.html.txt", "consulta.html.txt", "importada.html.txt")
_CNJ_20_DIGITOS = re.compile(r"^\d{20}$")


def _salvar_pagina_atomico(pasta: Path, nome: str, html: str) -> dict[str, str]:
    pasta.mkdir(parents=True, exist_ok=True)
    conteudo = html.encode("utf-8")
    destino = pasta / nome
    fd, temporario = tempfile.mkstemp(dir=pasta, suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as arquivo:
            arquivo.write(conteudo)
        os.replace(temporario, destino)
    finally:
        Path(temporario).unlink(missing_ok=True)
    return {"arquivo": nome, "sha256": hashlib.sha256(conteudo).hexdigest()}


def _evidencia_principal(resultado: dict) -> dict | None:
    evidencias = resultado.get("evidencias")
    if not isinstance(evidencias, list):
        return None
    por_nome = {
        e["arquivo"]: e
        for e in evidencias
        if isinstance(e, dict)
        and isinstance(e.get("arquivo"), str)
        and isinstance(e.get("sha256"), str)
    }
    for nome in _ARQUIVOS_CAPA_PRIORIDADE:
        if nome in por_nome:
            return por_nome[nome]
    return None


def _ler_evidencia_integra(pasta_caso: Path, evidencia: dict) -> tuple[str | None, str | None]:
    nome = evidencia["arquivo"]
    hash_esperado = evidencia["sha256"].strip().lower()
    base = pasta_caso.resolve()
    alvo = (pasta_caso / nome).resolve()
    try:
        alvo.relative_to(base)
    except ValueError:
        return None, "caminho de evidência fora da pasta do caso"
    if not alvo.is_file():
        return None, f"arquivo de evidência ausente ({nome})"
    try:
        conteudo = alvo.read_bytes()
    except OSError as erro:
        return None, f"falha ao ler evidência ({erro})"
    hash_real = hashlib.sha256(conteudo).hexdigest().lower()
    if hash_real != hash_esperado:
        return None, f"hash SHA-256 divergente para {nome}"
    return conteudo.decode("utf-8", errors="replace"), None


def _prioridade_verificacao(verificacao: VerificacaoValor) -> tuple[int, str]:
    if verificacao.status in {StatusValor.CONFIRMADO_ACIMA, StatusValor.CONFIRMADO_ATE}:
        tier = 4
    elif verificacao.resolvido_localmente and verificacao.motivo in {
        MotivoPendencia.CAPA_SEM_VALOR,
        MotivoPendencia.VALOR_AMBIGUO,
        MotivoPendencia.NAO_LOCALIZADO,
        MotivoPendencia.CONSULTAR_EPROC,
    }:
        tier = 3
    elif verificacao.motivo in {
        MotivoPendencia.CAPA_CNJ_DIVERGENTE,
        MotivoPendencia.EVIDENCIA_INVALIDA,
    }:
        tier = 2
    else:
        tier = 1
    return (tier, verificacao.consultado_em or "")


def verificar_capa_salva(
    caminho_resultado: Path,
    *,
    numero_esperado: str | None = None,
) -> tuple[str | None, VerificacaoValor | None]:
    """Valida integridade, CNJ e valor da causa de um ``resultado.json`` local.

    Retorna ``(numero_cnj_normalizado, VerificacaoValor)``.
    Se o arquivo estiver ilegível e sem CNJ identificável, retorna ``(None, None)``.
    """
    pasta_caso = caminho_resultado.parent
    cnj_pasta: str | None = None
    if _CNJ_20_DIGITOS.fullmatch(pasta_caso.name):
        try:
            cnj_pasta = normalizar_cnj_tjsp(pasta_caso.name)
        except ValueError:
            cnj_pasta = None

    alvo = numero_esperado or cnj_pasta

    try:
        dados = json.loads(caminho_resultado.read_text(encoding="utf-8"))
    except (OSError, ValueError) as erro:
        if alvo is None:
            return None, None
        return alvo, VerificacaoValor(
            numero_processo=alvo,
            status=StatusValor.PENDENTE,
            motivo=MotivoPendencia.EVIDENCIA_INVALIDA,
            detalhe=f"resultado.json ilegível ({erro})",
            evidencia_arquivo=str(caminho_resultado),
            resolvido_localmente=False,
        )

    if not isinstance(dados, dict):
        if alvo is None:
            return None, None
        return alvo, VerificacaoValor(
            numero_processo=alvo,
            status=StatusValor.PENDENTE,
            motivo=MotivoPendencia.EVIDENCIA_INVALIDA,
            detalhe="resultado.json em formato inválido",
            evidencia_arquivo=str(caminho_resultado),
            resolvido_localmente=False,
        )

    cnj_json: str | None = None
    bruto_json = dados.get("numero_processo")
    if isinstance(bruto_json, str) and bruto_json.strip():
        try:
            cnj_json = normalizar_cnj_tjsp(bruto_json)
        except ValueError:
            cnj_json = None

    chave = alvo or cnj_json
    if chave is None:
        return None, None

    fonte = str(dados.get("fonte") or "TJSP e-SAJ — consulta pública de 1º grau")
    url_fonte = str(dados.get("url_pagina") or dados.get("url_consulta") or "") or None
    consultado_em = str(dados.get("consultado_em") or "") or None

    if cnj_json is None or cnj_json != chave:
        return chave, VerificacaoValor(
            numero_processo=chave,
            status=StatusValor.PENDENTE,
            motivo=MotivoPendencia.CAPA_CNJ_DIVERGENTE,
            detalhe=f"numero_processo divergente no resultado ({bruto_json!r})",
            fonte=fonte,
            url_fonte=url_fonte,
            consultado_em=consultado_em,
            evidencia_arquivo=str(caminho_resultado),
            resolvido_localmente=True,
        )

    status_salvo = str(dados.get("status") or "")
    if status_salvo == "processo_divergente":
        return chave, VerificacaoValor(
            numero_processo=chave,
            status=StatusValor.PENDENTE,
            motivo=MotivoPendencia.CAPA_CNJ_DIVERGENTE,
            detalhe="página retornou número de processo diferente do CNJ",
            fonte=fonte,
            url_fonte=url_fonte,
            consultado_em=consultado_em,
            evidencia_arquivo=str(caminho_resultado),
            resolvido_localmente=True,
        )
    if status_salvo == "nao_localizado":
        return chave, VerificacaoValor(
            numero_processo=chave,
            status=StatusValor.PENDENTE,
            motivo=MotivoPendencia.NAO_LOCALIZADO,
            detalhe="não localizado na consulta pública do e-SAJ",
            fonte=fonte,
            url_fonte=url_fonte,
            consultado_em=consultado_em,
            evidencia_arquivo=str(caminho_resultado),
            resolvido_localmente=True,
        )
    if status_salvo == "consultar_eproc":
        return chave, VerificacaoValor(
            numero_processo=chave,
            status=StatusValor.PENDENTE,
            motivo=MotivoPendencia.CONSULTAR_EPROC,
            detalhe="processo indicado como migrado ou tramitando no eproc",
            fonte=fonte,
            url_fonte=url_fonte,
            consultado_em=consultado_em,
            evidencia_arquivo=str(caminho_resultado),
            resolvido_localmente=True,
        )
    if status_salvo not in {"coletado", "coletado_parcial"}:
        detalhe = str(dados.get("motivo") or dados.get("mensagem") or status_salvo or "pendente")
        return chave, VerificacaoValor(
            numero_processo=chave,
            status=StatusValor.PENDENTE,
            motivo=MotivoPendencia.CONSULTA_INTERROMPIDA,
            detalhe=detalhe,
            fonte=fonte,
            url_fonte=url_fonte,
            consultado_em=consultado_em,
            evidencia_arquivo=str(caminho_resultado),
            resolvido_localmente=False,
        )

    evidencia = _evidencia_principal(dados)
    if evidencia is None:
        return chave, VerificacaoValor(
            numero_processo=chave,
            status=StatusValor.PENDENTE,
            motivo=MotivoPendencia.EVIDENCIA_INVALIDA,
            detalhe="nenhuma evidência HTML registrada em resultado.json",
            fonte=fonte,
            url_fonte=url_fonte,
            consultado_em=consultado_em,
            evidencia_arquivo=str(caminho_resultado),
            resolvido_localmente=False,
        )

    html, erro_evidencia = _ler_evidencia_integra(pasta_caso, evidencia)
    if html is None:
        return chave, VerificacaoValor(
            numero_processo=chave,
            status=StatusValor.PENDENTE,
            motivo=MotivoPendencia.EVIDENCIA_INVALIDA,
            detalhe=erro_evidencia or "evidência inválida",
            fonte=fonte,
            url_fonte=url_fonte,
            consultado_em=consultado_em,
            evidencia_arquivo=str(pasta_caso / evidencia["arquivo"]),
            evidencia_sha256=evidencia["sha256"].lower(),
            resolvido_localmente=False,
        )

    extraido = extrair(html, chave)
    status_ext = extraido.get("status")
    caminho_evidencia = str(pasta_caso / evidencia["arquivo"])
    hash_evidencia = evidencia["sha256"].lower()

    if status_ext == "processo_divergente":
        return chave, VerificacaoValor(
            numero_processo=chave,
            status=StatusValor.PENDENTE,
            motivo=MotivoPendencia.CAPA_CNJ_DIVERGENTE,
            detalhe="CNJ na capa HTML diverge do processo consultado",
            fonte=fonte,
            url_fonte=url_fonte,
            consultado_em=consultado_em,
            evidencia_arquivo=caminho_evidencia,
            evidencia_sha256=hash_evidencia,
            resolvido_localmente=True,
        )
    if status_ext == "nao_localizado":
        return chave, VerificacaoValor(
            numero_processo=chave,
            status=StatusValor.PENDENTE,
            motivo=MotivoPendencia.NAO_LOCALIZADO,
            detalhe="não localizado na evidência HTML",
            fonte=fonte,
            url_fonte=url_fonte,
            consultado_em=consultado_em,
            evidencia_arquivo=caminho_evidencia,
            evidencia_sha256=hash_evidencia,
            resolvido_localmente=True,
        )
    if status_ext == "consultar_eproc":
        return chave, VerificacaoValor(
            numero_processo=chave,
            status=StatusValor.PENDENTE,
            motivo=MotivoPendencia.CONSULTAR_EPROC,
            detalhe="processo no eproc conforme evidência HTML",
            fonte=fonte,
            url_fonte=url_fonte,
            consultado_em=consultado_em,
            evidencia_arquivo=caminho_evidencia,
            evidencia_sha256=hash_evidencia,
            resolvido_localmente=True,
        )
    if status_ext not in {"coletado", "coletado_parcial"}:
        return chave, VerificacaoValor(
            numero_processo=chave,
            status=StatusValor.PENDENTE,
            motivo=MotivoPendencia.CONSULTA_INTERROMPIDA,
            detalhe=f"status da evidência: {status_ext}",
            fonte=fonte,
            url_fonte=url_fonte,
            consultado_em=consultado_em,
            evidencia_arquivo=caminho_evidencia,
            evidencia_sha256=hash_evidencia,
            resolvido_localmente=False,
        )

    campos = extraido.get("campos") or {}
    valor_texto = campos.get("valor_da_causa_texto")
    valor_reais, valor_centavos, erro_valor = interpretar_valor_causa(valor_texto)
    if erro_valor is not None or valor_centavos is None or valor_reais is None:
        detalhe = (
            f"campo valor da causa ambíguo: {valor_texto!r}"
            if erro_valor == MotivoPendencia.VALOR_AMBIGUO
            else "capa válida sem campo valor da causa preenchido"
        )
        return chave, VerificacaoValor(
            numero_processo=chave,
            status=StatusValor.PENDENTE,
            motivo=erro_valor or MotivoPendencia.CAPA_SEM_VALOR,
            detalhe=detalhe,
            valor_texto=valor_texto,
            fonte=fonte,
            url_fonte=url_fonte,
            consultado_em=consultado_em,
            evidencia_arquivo=caminho_evidencia,
            evidencia_sha256=hash_evidencia,
            resolvido_localmente=True,
        )

    status_final = (
        StatusValor.CONFIRMADO_ACIMA
        if acima_do_corte(valor_centavos)
        else StatusValor.CONFIRMADO_ATE
    )
    return chave, VerificacaoValor(
        numero_processo=chave,
        status=status_final,
        motivo=None,
        detalhe="",
        valor_centavos=valor_centavos,
        valor_reais=valor_reais,
        valor_texto=valor_texto,
        fonte=fonte,
        url_fonte=url_fonte,
        consultado_em=consultado_em,
        evidencia_arquivo=caminho_evidencia,
        evidencia_sha256=hash_evidencia,
        resolvido_localmente=True,
    )


def indexar_capas_locais(
    pastas_leitura: Iterable[Path],
    pasta_capas_filtro: Path,
) -> dict[str, VerificacaoValor]:
    """Indexa e valida todas as capas locais em leitura e na pasta do filtro."""
    melhores: dict[str, VerificacaoValor] = {}
    raizes = [*pastas_leitura, pasta_capas_filtro]
    for raiz in raizes:
        if not raiz.is_dir():
            continue
        for caminho in sorted(raiz.rglob("resultado.json")):
            chave, verificacao = verificar_capa_salva(caminho)
            if chave is None or verificacao is None:
                continue
            atual = melhores.get(chave)
            if atual is None or _prioridade_verificacao(verificacao) >= _prioridade_verificacao(atual):
                melhores[chave] = verificacao
    return melhores


def consultar_capa_esaj(
    numero_cnj: str,
    cliente: object,
    pasta_capas: Path,
) -> tuple[VerificacaoValor, str | None]:
    """Consulta a capa pública de um processo no e-SAJ e salva evidência local.

    Retorna ``(VerificacaoValor, motivo_parada)``, onde ``motivo_parada`` é
    preenchido quando o portal retorna bloqueio, captcha ou outra falha que
    deve interromper imediatamente novas consultas na rodada.
    """
    n = normalizar_cnj_tjsp(numero_cnj)
    url = url_consulta(n)
    pasta = pasta_capas / n
    resultado: dict[str, object] = {
        "numero_processo": n,
        "consultado_em": agora(),
        "fonte": "TJSP e-SAJ — consulta pública de 1º grau",
        "url_consulta": url,
        "url_pagina": url,
        "evidencias": [],
    }
    try:
        html = cliente.get(url)  # type: ignore[attr-defined]
        resultado["evidencias"].append(_salvar_pagina_atomico(pasta, "consulta.html.txt", html))  # type: ignore[union-attr]
        extraido = extrair(html, n)
        if extraido["status"] == "layout_nao_reconhecido":
            detalhe = link_detalhe(html, n)
            if detalhe:
                html = cliente.get(detalhe)  # type: ignore[attr-defined]
                resultado["url_pagina"] = detalhe
                resultado["evidencias"].append(  # type: ignore[union-attr]
                    _salvar_pagina_atomico(pasta, "detalhe.html.txt", html)
                )
                extraido = extrair(html, n)
        resultado.update(extraido)
    except FalhaConsulta as erro:
        resultado.update(status=erro.status, mensagem=str(erro))

    caminho_resultado = pasta / "resultado.json"
    gravar_json(caminho_resultado, resultado)
    _chave, verificacao = verificar_capa_salva(caminho_resultado, numero_esperado=n)
    assert verificacao is not None
    status_bruto = str(resultado.get("status") or "")
    motivo_parada = status_bruto if status_bruto in PARAR else None
    return verificacao, motivo_parada


def importar_capa_html(
    numero_cnj: str,
    caminho_html: Path,
    pasta_capas: Path,
) -> VerificacaoValor:
    """Incorpora uma página HTML salva manualmente na pasta ``capas/`` do filtro."""
    n = normalizar_cnj_tjsp(numero_cnj)
    pasta = pasta_capas / n
    html = Path(caminho_html).read_text(encoding="utf-8-sig")
    evidencia = _salvar_pagina_atomico(pasta, "importada.html.txt", html)
    extraido = extrair(html, n)
    resultado = {
        "numero_processo": n,
        **extraido,
        "consultado_em": agora(),
        "fonte": "HTML fornecido pelo usuário — conteúdo não consultado online",
        "url_consulta": url_consulta(n),
        "url_pagina": url_consulta(n),
        "evidencias": [evidencia],
    }
    caminho_resultado = pasta / "resultado.json"
    gravar_json(caminho_resultado, resultado)
    _chave, verificacao = verificar_capa_salva(caminho_resultado, numero_esperado=n)
    assert verificacao is not None
    return verificacao
