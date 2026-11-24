"""Persistência incremental de progresso, pendências, candidatos e cache da rodada.

Todos os arquivos são gravados sob ``saida/DG__mais_de_600_mil/rodadas/<chave>/``
com escrita atômica (arquivo temporário na mesma pasta + ``os.replace``).
"""

import csv
import gzip
import json
import os
import tempfile
from datetime import date
from decimal import Decimal
from pathlib import Path

from guicredito.aprofundamento.fluxo import gravar_json
from guicredito.dg_mais_de_600_mil.modelos import (
    CandidatoDiario,
    CasoPendente,
    ResumoRodadaFiltrada,
    StatusValor,
    VerificacaoValor,
    rotulo_motivo,
)
from guicredito.djen.modelos import (
    Bloco,
    CadernoInfo,
    Caso,
    CasoPontuado,
    Destinatario,
    Pontuacao,
    Publicacao,
    Sinal,
    TipoCredor,
)
from guicredito.djen.texto import formatar_cnj

_VERSAO_CACHE = 1


def pasta_rodada(pasta_filtro: Path, sigla: str, inicio: date, fim: date) -> Path:
    chave = f"{sigla.upper()}_{inicio:%Y-%m-%d}_a_{fim:%Y-%m-%d}"
    return pasta_filtro / "rodadas" / chave


def registrar_evento_verificacao(
    pasta_da_rodada: Path,
    verificacao: VerificacaoValor,
) -> None:
    """Acrescenta um evento de verificação concluída para rastreabilidade imediata."""
    pasta_da_rodada.mkdir(parents=True, exist_ok=True)
    caminho = pasta_da_rodada / "eventos.jsonl"
    linha = json.dumps(verificacao.para_dict(), ensure_ascii=False) + "\n"
    with caminho.open("a", encoding="utf-8") as arquivo:
        arquivo.write(linha)
        arquivo.flush()


def gravar_pendentes_csv(
    pasta_da_rodada: Path,
    pendentes: list[CasoPendente],
) -> Path:
    """Grava a lista completa de pendentes em CSV de forma atômica."""
    pasta_da_rodada.mkdir(parents=True, exist_ok=True)
    destino = pasta_da_rodada / "pendentes.csv"
    fd, temporario = tempfile.mkstemp(dir=pasta_da_rodada, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as arquivo:
            escritor = csv.writer(arquivo)
            escritor.writerow(
                [
                    "Processo",
                    "CNJ_digitos",
                    "Pontos",
                    "Ano_divida",
                    "Motivo_codigo",
                    "Motivo",
                    "Detalhe",
                    "Mencao_diario_maior_600k",
                ]
            )
            for item in pendentes:
                caso = item.caso_pontuado.caso
                ver = item.verificacao
                escritor.writerow(
                    [
                        formatar_cnj(caso.numero_processo),
                        caso.numero_processo,
                        item.caso_pontuado.pontos.total,
                        caso.ano_divida,
                        ver.motivo or "",
                        rotulo_motivo(ver.motivo),
                        ver.detalhe,
                        str(item.mencao_valor_alto) if item.mencao_valor_alto is not None else "",
                    ]
                )
        os.replace(temporario, destino)
    finally:
        Path(temporario).unlink(missing_ok=True)
    return destino


def gravar_candidatos_diario_csv(
    pasta_da_rodada: Path,
    candidatos: list[CandidatoDiario],
) -> Path:
    """Grava os candidatos com menção > R$ 600 mil no diário em CSV atômico."""
    pasta_da_rodada.mkdir(parents=True, exist_ok=True)
    destino = pasta_da_rodada / "candidatos_diario.csv"
    fd, temporario = tempfile.mkstemp(dir=pasta_da_rodada, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as arquivo:
            escritor = csv.writer(arquivo)
            escritor.writerow(
                [
                    "Processo",
                    "CNJ_digitos",
                    "Pontos",
                    "Ano_divida",
                    "Comarca",
                    "Credor",
                    "Devedor",
                    "Maior_mencao_diario_reais",
                    "Situacao_capa",
                    "Valor_causa_confirmado_reais",
                    "Detalhe",
                ]
            )
            for item in candidatos:
                caso = item.caso_pontuado.caso
                ver = item.verificacao
                if ver.status is StatusValor.CONFIRMADO_ACIMA:
                    situacao = "Confirmado acima de R$ 600.000,00"
                elif ver.status is StatusValor.CONFIRMADO_ATE:
                    situacao = "Confirmado até R$ 600.000,00"
                else:
                    situacao = rotulo_motivo(ver.motivo)
                escritor.writerow(
                    [
                        formatar_cnj(caso.numero_processo),
                        caso.numero_processo,
                        item.caso_pontuado.pontos.total,
                        caso.ano_divida,
                        caso.comarca,
                        caso.credor or "",
                        caso.devedor or "não identificado",
                        str(item.mencao_valor_alto),
                        situacao,
                        str(ver.valor_reais) if ver.valor_reais is not None else "",
                        ver.detalhe,
                    ]
                )
        os.replace(temporario, destino)
    finally:
        Path(temporario).unlink(missing_ok=True)
    return destino


def gravar_resumo_rodada(
    pasta_da_rodada: Path,
    resumo: ResumoRodadaFiltrada,
    caminho_planilha: Path,
) -> Path:
    """Grava ``resumo.json`` com métricas completas da rodada filtrada."""
    destino = pasta_da_rodada / "resumo.json"
    payload = {
        "inicio": resumo.inicio.isoformat(),
        "fim": resumo.fim.isoformat(),
        "tribunal": resumo.tribunal,
        "gerado_em": resumo.gerado_em.isoformat(),
        "planilha": str(caminho_planilha),
        "cobertura_parcial": resumo.cobertura_parcial,
        "somente_capas_locais": resumo.somente_capas_locais,
        "so_mencao_diario": resumo.so_mencao_diario,
        "cache_cadernos_reutilizado": resumo.cache_cadernos_reutilizado,
        "interrompido_por": resumo.interrompido_por,
        "publicacoes_lidas": resumo.publicacoes_lidas,
        "publicacoes_cobranca": resumo.publicacoes_cobranca,
        "processos": resumo.processos,
        "processos_so_empresa": resumo.processos_so_empresa,
        "processos_banco": resumo.processos_banco,
        "processos_acordo": resumo.processos_acordo,
        "processos_recentes": resumo.processos_recentes,
        "dias_historico": resumo.dias_historico,
        "elegiveis": resumo.elegiveis,
        "candidatos_mencao_diario": resumo.candidatos_mencao_diario,
        "candidatos_mencao_pendentes": resumo.candidatos_mencao_pendentes,
        "confirmados_acima_corte": resumo.confirmados_acima_corte,
        "confirmados_ate_corte": resumo.confirmados_ate_corte,
        "pendentes": resumo.pendentes,
        "exportados": resumo.exportados,
        "limite_exibicao": resumo.limite_exibicao,
        "consultas_nesta_rodada": resumo.consultas_nesta_rodada,
        "reutilizados_locais": resumo.reutilizados_locais,
        "pendencias_por_motivo": resumo.pendencias_por_motivo,
    }
    gravar_json(destino, payload)
    return destino


def _assinatura_cadernos(
    cadernos: list[tuple[CadernoInfo, Path]],
    cadernos_historico: list[tuple[CadernoInfo, Path]],
    *,
    sigla: str,
    inicio: date,
    fim: date,
    historico: int,
    ano_referencia: int,
) -> dict[str, object]:
    return {
        "versao": _VERSAO_CACHE,
        "sigla": sigla,
        "inicio": inicio.isoformat(),
        "fim": fim.isoformat(),
        "historico": historico,
        "ano_referencia": ano_referencia,
        "cadernos": [
            [info.data.isoformat(), info.versao, info.hash.lower()]
            for info, _ in cadernos
        ],
        "cadernos_historico": [
            [info.data.isoformat(), info.versao, info.hash.lower()]
            for info, _ in cadernos_historico
        ],
    }


def _serializar_caso_pontuado(item: CasoPontuado) -> list[object]:
    c = item.caso
    p = item.pontos
    return [
        c.numero_processo,
        c.classe,
        c.orgao,
        c.comarca,
        c.link,
        c.credor,
        c.tipo_credor.value if c.tipo_credor is not None else None,
        c.devedor,
        c.avalista,
        c.so_empresa,
        c.ano_divida,
        [[s.chave, s.bloco.value, s.pontos, s.rotulo, s.trecho] for s in c.sinais],
        c.ultima_data.isoformat(),
        c.ultimo_tipo,
        c.n_publicacoes,
        c.acordo_vigente,
        [
            p.acordo_anterior,
            p.imovel,
            p.transito,
            p.desgaste,
            p.veiculo,
            p.credor,
            p.descontos,
            p.total,
        ],
    ]


def _desserializar_caso_pontuado(dado: list[object]) -> CasoPontuado:
    tipo = TipoCredor(dado[6]) if dado[6] is not None else None
    sinais = tuple(
        Sinal(str(s[0]), Bloco(str(s[1])), int(s[2]), str(s[3]), str(s[4]))
        for s in dado[11]  # type: ignore[union-attr]
    )
    caso = Caso(
        numero_processo=str(dado[0]),
        classe=str(dado[1]),
        orgao=str(dado[2]),
        comarca=str(dado[3]),
        link=str(dado[4]),
        credor=str(dado[5]) if dado[5] is not None else None,
        tipo_credor=tipo,
        devedor=str(dado[7]) if dado[7] is not None else None,
        avalista=bool(dado[8]),
        so_empresa=bool(dado[9]),
        ano_divida=int(dado[10]),
        sinais=sinais,
        ultima_data=date.fromisoformat(str(dado[12])),
        ultimo_tipo=str(dado[13]),
        n_publicacoes=int(dado[14]),
        acordo_vigente=bool(dado[15]),
    )
    pt = dado[16]
    pontos = Pontuacao(
        acordo_anterior=int(pt[0]),  # type: ignore[index]
        imovel=int(pt[1]),  # type: ignore[index]
        transito=int(pt[2]),  # type: ignore[index]
        desgaste=int(pt[3]),  # type: ignore[index]
        veiculo=int(pt[4]),  # type: ignore[index]
        credor=int(pt[5]),  # type: ignore[index]
        descontos=int(pt[6]),  # type: ignore[index]
        total=int(pt[7]),  # type: ignore[index]
    )
    return CasoPontuado(caso, pontos)


def _serializar_pub(pub: Publicacao) -> list[object]:
    return [
        pub.id,
        pub.data.isoformat(),
        pub.tipo,
        pub.orgao,
        pub.numero_processo,
        pub.classe,
        pub.texto,
        pub.link,
        [[d.nome, d.polo] for d in pub.destinatarios],
    ]


def _desserializar_pub(dado: list[object]) -> Publicacao:
    return Publicacao(
        id=int(dado[0]),
        data=date.fromisoformat(str(dado[1])),
        tipo=str(dado[2]),
        orgao=str(dado[3]),
        numero_processo=str(dado[4]),
        classe=str(dado[5]),
        texto=str(dado[6]),
        link=str(dado[7]),
        destinatarios=tuple(
            Destinatario(str(d[0]), str(d[1])) for d in dado[8]  # type: ignore[union-attr]
        ),
    )


def salvar_cache_rodada(
    pasta_da_rodada: Path,
    *,
    cadernos: list[tuple[CadernoInfo, Path]],
    cadernos_historico: list[tuple[CadernoInfo, Path]],
    sigla: str,
    inicio: date,
    fim: date,
    historico: int,
    ano_referencia: int,
    contagens: dict[str, int],
    totais_comunicacoes: list[int],
    elegiveis_ordenados: list[CasoPontuado],
    mencoes_altas: dict[str, Decimal],
    pubs_candidatos: dict[str, list[Publicacao]],
) -> Path:
    """Grava cache compactado dos elegíveis e menções para retomadas em segundos."""
    pasta_da_rodada.mkdir(parents=True, exist_ok=True)
    destino = pasta_da_rodada / "cache_rodada.json.gz"
    payload = {
        "assinatura": _assinatura_cadernos(
            cadernos,
            cadernos_historico,
            sigla=sigla,
            inicio=inicio,
            fim=fim,
            historico=historico,
            ano_referencia=ano_referencia,
        ),
        "contagens": contagens,
        "totais_comunicacoes": totais_comunicacoes,
        "elegiveis": [_serializar_caso_pontuado(item) for item in elegiveis_ordenados],
        "mencoes_altas": {k: str(v) for k, v in mencoes_altas.items()},
        "pubs_candidatos": {
            num: [_serializar_pub(pub) for pub in pubs]
            for num, pubs in pubs_candidatos.items()
        },
    }
    fd, temporario = tempfile.mkstemp(dir=pasta_da_rodada, suffix=".tmp.gz")
    try:
        with os.fdopen(fd, "wb") as bruto:
            with gzip.GzipFile(fileobj=bruto, mode="wb", compresslevel=3) as gz:
                gz.write(json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))
        os.replace(temporario, destino)
    finally:
        Path(temporario).unlink(missing_ok=True)
    return destino


def carregar_cache_rodada(
    pasta_da_rodada: Path,
    *,
    cadernos: list[tuple[CadernoInfo, Path]],
    cadernos_historico: list[tuple[CadernoInfo, Path]],
    sigla: str,
    inicio: date,
    fim: date,
    historico: int,
    ano_referencia: int,
) -> dict[str, object] | None:
    """Carrega o cache se a assinatura de cadernos e parâmetros conferir exatamente."""
    caminho = pasta_da_rodada / "cache_rodada.json.gz"
    if not caminho.is_file():
        return None
    esperada = _assinatura_cadernos(
        cadernos,
        cadernos_historico,
        sigla=sigla,
        inicio=inicio,
        fim=fim,
        historico=historico,
        ano_referencia=ano_referencia,
    )
    try:
        with gzip.open(caminho, "rt", encoding="utf-8") as arquivo:
            dados = json.load(arquivo)
        if dados.get("assinatura") != esperada:
            return None
        elegiveis = [_desserializar_caso_pontuado(item) for item in dados["elegiveis"]]
        mencoes = {str(k): Decimal(str(v)) for k, v in dados["mencoes_altas"].items()}
        pubs = {
            str(num): [_desserializar_pub(pub) for pub in lista]
            for num, lista in dados.get("pubs_candidatos", {}).items()
        }
        return {
            "contagens": dict(dados["contagens"]),
            "totais_comunicacoes": [int(x) for x in dados["totais_comunicacoes"]],
            "elegiveis": elegiveis,
            "mencoes_altas": mencoes,
            "pubs_candidatos": pubs,
        }
    except (OSError, ValueError, KeyError, TypeError):
        return None
