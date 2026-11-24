"""Reuso somente leitura de cadernos existentes e download isolado para o filtro.

Cadernos já disponíveis em ``dados/cadernos/`` são lidos sem qualquer escrita
ou alteração nessa pasta. Cadernos que precisarem ser baixados são gravados
exclusivamente em ``saida/DG__mais_de_600_mil/cadernos/``.
"""

import hashlib
import re
import time
import zipfile
from collections.abc import Callable
from datetime import date
from pathlib import Path

from guicredito.djen.fonte import (
    ClienteHttp,
    ErroDownload,
    HttpErro,
    buscar_metadados,
)
from guicredito.djen.modelos import CadernoInfo

_BLOCO = 1024 * 1024


def _sha256(caminho: Path) -> str:
    resumo = hashlib.sha256()
    with caminho.open("rb") as arquivo:
        while bloco := arquivo.read(_BLOCO):
            resumo.update(bloco)
    return resumo.hexdigest()


def _info_de_zip_local(caminho: Path, sigla: str, dia: date, versao: int) -> CadernoInfo | None:
    try:
        with zipfile.ZipFile(caminho) as zf:
            paginas = sum(1 for nome in zf.namelist() if nome.endswith(".json"))
    except (zipfile.BadZipFile, OSError):
        return None
    return CadernoInfo(
        sigla=sigla,
        data=dia,
        versao=versao,
        total_comunicacoes=0,
        numero_paginas=paginas,
        tamanho_bytes=caminho.stat().st_size,
        hash=_sha256(caminho),
        url=f"local://{caminho.name}",
    )


def encontrar_caderno_local(
    pastas: list[Path],
    sigla: str,
    dia: date,
) -> tuple[CadernoInfo, Path] | None:
    """Procura o caderno local mais recente (maior versão) para sigla e data."""
    padrao = re.compile(rf"^{re.escape(sigla)}-D-{re.escape(dia.isoformat())}_v(\d+)\.zip$")
    candidatos: list[tuple[int, int, Path]] = []
    for prioridade, pasta in enumerate(pastas):
        if not pasta.is_dir():
            continue
        for arquivo in pasta.iterdir():
            if not arquivo.is_file():
                continue
            m = padrao.match(arquivo.name)
            if m:
                candidatos.append((int(m.group(1)), -prioridade, arquivo))
    for versao, _prio, caminho in sorted(candidatos, reverse=True):
        info = _info_de_zip_local(caminho, sigla, dia, versao)
        if info is not None:
            return info, caminho
    return None


def obter_caderno(
    cliente: ClienteHttp | None,
    sigla: str,
    dia: date,
    *,
    pasta_leitura: Path,
    pasta_escrita: Path,
    preferir_local: bool = False,
    espera: Callable[[float], None] = time.sleep,
) -> tuple[CadernoInfo, Path] | None:
    """Obtém o caderno de um dia preservando ``pasta_leitura`` somente leitura.

    - Se ``preferir_local`` for True (ou ``cliente`` for None), reaproveita
      qualquer zip íntegro já salvo em ``pasta_leitura`` ou ``pasta_escrita``
      sem consultar a rede.
    - Caso contrário, consulta os metadados na API DJEN: se o hash já existir
      em ``pasta_leitura``, reutiliza o arquivo sem escrever nada fora do filtro;
      se já existir em ``pasta_escrita``, reutiliza; se faltar, baixa apenas
      dentro de ``pasta_escrita``.
    - Em falha de conexão (status 0) na consulta de metadados, faz fallback
      seguro para um zip local válido quando disponível.
    """
    if preferir_local or cliente is None:
        local = encontrar_caderno_local([pasta_leitura, pasta_escrita], sigla, dia)
        if local is not None:
            return local
        if cliente is None:
            return None

    motivo = "falha desconhecida"
    ultima_falha_conexao = False
    for tentativa in range(1, 4):
        try:
            info = buscar_metadados(cliente, sigla, dia)
        except HttpErro as erro:
            if erro.status == 404:
                return None
            ultima_falha_conexao = erro.status == 0
            motivo = str(erro)
            if tentativa < 3:
                espera(2 if tentativa == 1 else 4)
            continue

        if info is None:
            return None

        nome = f"{sigla}-D-{dia.isoformat()}_v{info.versao}.zip"
        hash_esperado = info.hash.lower()

        existente_leitura = pasta_leitura / nome
        if existente_leitura.is_file() and _sha256(existente_leitura) == hash_esperado:
            return info, existente_leitura

        destino = pasta_escrita / nome
        if destino.is_file() and _sha256(destino) == hash_esperado:
            return info, destino

        pasta_escrita.mkdir(parents=True, exist_ok=True)
        parcial = pasta_escrita / f"{nome}.part"
        try:
            cliente.baixar(info.url, parcial)
            if _sha256(parcial) != hash_esperado:
                motivo = "hash não confere"
                parcial.unlink(missing_ok=True)
            else:
                parcial.replace(destino)
                return info, destino
        except (HttpErro, TimeoutError, OSError) as erro:
            motivo = erro.args[0] if erro.args else type(erro).__name__
            if isinstance(erro, HttpErro):
                motivo = str(erro)
            parcial.unlink(missing_ok=True)
        if tentativa < 3:
            espera(2 if tentativa == 1 else 4)

    if ultima_falha_conexao:
        local = encontrar_caderno_local([pasta_leitura, pasta_escrita], sigla, dia)
        if local is not None:
            return local

    raise ErroDownload(f"{dia.isoformat()}: {motivo}")
