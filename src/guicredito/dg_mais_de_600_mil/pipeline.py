"""Pipeline da pesquisa DJEN acima de R$ 600.000,00.

Reaproveita integralmente a seleção, consolidação, marcação de acordos e
pontuação do pacote ``djen``, sem aplicar o corte inicial de 300 linhas.
Verifica o valor da causa apenas a partir de capas válidas do próprio processo
e grava toda saída exclusivamente sob ``saida/DG__mais_de_600_mil/``.
"""

from collections import Counter
from collections.abc import Iterable
from dataclasses import replace
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

from guicredito.aprofundamento.cliente import Cliente as ClienteEsaj
from guicredito.aprofundamento.cliente import FalhaConsulta
from guicredito.aprofundamento.cnj import normalizar as normalizar_cnj_tjsp
from guicredito.aprofundamento.pagina import diagnostico
from guicredito.dg_mais_de_600_mil.cadernos import obter_caderno
from guicredito.dg_mais_de_600_mil.capas import consultar_capa_esaj, indexar_capas_locais
from guicredito.dg_mais_de_600_mil.estado import (
    carregar_cache_rodada,
    gravar_candidatos_diario_csv,
    gravar_pendentes_csv,
    gravar_resumo_rodada,
    pasta_rodada,
    registrar_evento_verificacao,
    salvar_cache_rodada,
)
from guicredito.dg_mais_de_600_mil.modelos import (
    CandidatoDiario,
    CasoConfirmado,
    CasoPendente,
    MotivoPendencia,
    ResumoRodadaFiltrada,
    StatusValor,
    VerificacaoValor,
)
from guicredito.dg_mais_de_600_mil.planilha import escrever_planilha_filtrada
from guicredito.dg_mais_de_600_mil.valores import mencao_valor_alto_no_texto
from guicredito.djen.casos import marcar_acordos, montar_casos, resumir
from guicredito.djen.fonte import (
    ClienteHttp,
    ClienteUrllib,
    dias_uteis,
    dias_uteis_antes,
)
from guicredito.djen.leitura import ler_caderno
from guicredito.djen.modelos import (
    CadernoInfo,
    CasoPontuado,
    Publicacao,
    ResumoPublicacao,
    TipoCredor,
)
from guicredito.djen.partes import classe_de_cobranca
from guicredito.djen.pontuacao import pontuar, recente


def _chave_ordenacao(item: CasoPontuado) -> tuple[int, int, str]:
    return (-item.pontos.total, item.caso.ano_divida, item.caso.numero_processo)


def _resumos_de_cobranca(
    cadernos: Iterable[tuple[CadernoInfo, Path]],
) -> Iterable[ResumoPublicacao]:
    for _info, caminho in cadernos:
        for pub in ler_caderno(caminho):
            if classe_de_cobranca(pub.classe):
                yield resumir(pub)


def _publicacoes_dos_casos(
    cadernos: Iterable[tuple[CadernoInfo, Path]],
    numeros: set[str],
) -> dict[str, list[Publicacao]]:
    if not numeros:
        return {}
    publicacoes: dict[str, list[Publicacao]] = {numero: [] for numero in numeros}
    for _info, caminho in cadernos:
        for pub in ler_caderno(caminho):
            if pub.numero_processo in numeros:
                publicacoes[pub.numero_processo].append(pub)
    return publicacoes


def _verificacao_nao_consultado(numero_processo: str) -> VerificacaoValor:
    return VerificacaoValor(
        numero_processo=numero_processo,
        status=StatusValor.PENDENTE,
        motivo=MotivoPendencia.NAO_CONSULTADO,
        detalhe="aguardando consulta avulsa ou incorporação de capa local",
        resolvido_localmente=False,
    )


def _verificacao_cnj_invalido(numero_processo: str, erro: str) -> VerificacaoValor:
    return VerificacaoValor(
        numero_processo=numero_processo,
        status=StatusValor.PENDENTE,
        motivo=MotivoPendencia.CNJ_INVALIDO,
        detalhe=erro,
        resolvido_localmente=True,
    )


def rodar_mais_de_600_mil(
    inicio: date,
    fim: date,
    *,
    sigla: str = "TJSP",
    limite: int | None = None,
    historico: int = 0,
    pasta_dados: Path = Path("dados/cadernos"),
    pasta_aprofundamento: Path = Path("saida/aprofundamento"),
    pasta_filtro: Path = Path("saida/DG__mais_de_600_mil"),
    pastas_capas_extras: Iterable[Path] = (),
    cliente_djen: ClienteHttp | None = None,
    cliente_esaj: object | None = None,
    somente_capas_locais: bool = False,
    so_mencao_diario: bool = False,
    usar_cache_rodada: bool = True,
    max_consultas: int = 10,
    intervalo: float = 5.0,
    agora: datetime | None = None,
) -> tuple[Path, ResumoRodadaFiltrada]:
    """Executa a pesquisa filtrada (> R$ 600.000,00) com isolamento de escrita."""
    if historico < 0:
        raise ValueError("--historico não pode ser negativo.")
    if limite is not None and limite < 0:
        raise ValueError("--limite não pode ser negativo.")
    if max_consultas < 0:
        raise ValueError("--max-consultas não pode ser negativo.")

    momento = agora or datetime.now()
    pasta_cadernos_filtro = pasta_filtro / "cadernos"
    pasta_capas_filtro = pasta_filtro / "capas"
    pasta_da_rodada = pasta_rodada(pasta_filtro, sigla, inicio, fim)

    http_djen = cliente_djen if cliente_djen is not None else ClienteUrllib()
    preferir_caderno_local = somente_capas_locais and cliente_djen is None

    cadernos_brutos: list[tuple[CadernoInfo, Path]] = []
    dias_sem_caderno: list[date] = []
    for dia in dias_uteis(inicio, fim):
        baixado = obter_caderno(
            http_djen,
            sigla,
            dia,
            pasta_leitura=pasta_dados,
            pasta_escrita=pasta_cadernos_filtro,
            preferir_local=preferir_caderno_local,
        )
        if baixado is None:
            dias_sem_caderno.append(dia)
            print(f"sem caderno em {dia:%d/%m}")
            continue
        cadernos_brutos.append(baixado)

    cadernos_historico: list[tuple[CadernoInfo, Path]] = []
    for dia in dias_uteis_antes(inicio, historico):
        baixado = obter_caderno(
            http_djen,
            sigla,
            dia,
            pasta_leitura=pasta_dados,
            pasta_escrita=pasta_cadernos_filtro,
            preferir_local=preferir_caderno_local,
        )
        if baixado is None:
            print(f"sem caderno em {dia:%d/%m}")
            continue
        cadernos_historico.append(baixado)

    cache = (
        carregar_cache_rodada(
            pasta_da_rodada,
            cadernos=cadernos_brutos,
            cadernos_historico=cadernos_historico,
            sigla=sigla,
            inicio=inicio,
            fim=fim,
            historico=historico,
            ano_referencia=momento.year,
        )
        if usar_cache_rodada
        else None
    )

    cache_cadernos_reutilizado = cache is not None
    pubs_candidatos_cache: dict[str, list[Publicacao]] = {}

    if cache is not None:
        contagens = cache["contagens"]  # type: ignore[assignment]
        publicacoes_lidas = int(contagens["publicacoes_lidas"])
        publicacoes_cobranca = int(contagens["publicacoes_cobranca"])
        total_processos = int(contagens["processos"])
        total_so_empresa = int(contagens["processos_so_empresa"])
        total_banco = int(contagens["processos_banco"])
        total_acordo = int(contagens["processos_acordo"])
        total_recentes = int(contagens["processos_recentes"])
        elegiveis_ordenados: list[CasoPontuado] = cache["elegiveis"]  # type: ignore[assignment]
        mencoes_altas: dict[str, Decimal] = cache["mencoes_altas"]  # type: ignore[assignment]
        pubs_candidatos_cache = cache["pubs_candidatos"]  # type: ignore[assignment]
        totais_comunicacoes: list[int] = cache["totais_comunicacoes"]  # type: ignore[assignment]
        cadernos = [
            (
                replace(info, total_comunicacoes=total)
                if info.total_comunicacoes == 0 and total > 0
                else info,
                caminho,
            )
            for (info, caminho), total in zip(cadernos_brutos, totais_comunicacoes, strict=True)
        ]
    else:
        publicacoes_lidas = 0
        publicacoes_cobranca = 0
        resumos: list[ResumoPublicacao] = []
        mencoes_altas = {}
        cadernos = []
        totais_comunicacoes = []

        for info, caminho in cadernos_brutos:
            lidas_no_caderno = 0
            for pub in ler_caderno(caminho):
                lidas_no_caderno += 1
                publicacoes_lidas += 1
                if classe_de_cobranca(pub.classe):
                    publicacoes_cobranca += 1
                    resumos.append(resumir(pub))
                    mencao = mencao_valor_alto_no_texto(pub.texto)
                    if mencao is not None:
                        anterior = mencoes_altas.get(pub.numero_processo)
                        if anterior is None or mencao > anterior:
                            mencoes_altas[pub.numero_processo] = mencao
            totais_comunicacoes.append(lidas_no_caderno)
            if info.total_comunicacoes == 0 and lidas_no_caderno > 0:
                info = replace(info, total_comunicacoes=lidas_no_caderno)
            cadernos.append((info, caminho))

        resumos_historico = list(_resumos_de_cobranca(cadernos_historico))

        # Mesmas regras de seleção, consolidação, acordos e pontuação do DJEN normal,
        # porém mantendo todo o universo elegível antes do corte de 300.
        casos = montar_casos(resumos)
        casos = marcar_acordos(casos, casos + montar_casos(resumos_historico))
        so_empresa = [caso for caso in casos if caso.so_empresa]
        restantes = [caso for caso in casos if not caso.so_empresa]
        banco = [caso for caso in restantes if caso.tipo_credor is TipoCredor.BANCO]
        restantes = [caso for caso in restantes if caso.tipo_credor is not TipoCredor.BANCO]
        com_acordo = [caso for caso in restantes if caso.acordo_vigente]
        restantes = [caso for caso in restantes if not caso.acordo_vigente]
        recentes = [caso for caso in restantes if recente(caso, momento.year)]
        restantes = [caso for caso in restantes if not recente(caso, momento.year)]

        total_processos = len(casos)
        total_so_empresa = len(so_empresa)
        total_banco = len(banco)
        total_acordo = len(com_acordo)
        total_recentes = len(recentes)

        elegiveis_ordenados = sorted(
            (CasoPontuado(caso, pontuar(caso)) for caso in restantes),
            key=_chave_ordenacao,
        )

        # Guarda em cache as publicações dos candidatos com menção > 600k para
        # permitir retomadas quase instantâneas sem reler todos os zips.
        numeros_mencao_elegiveis = {
            item.caso.numero_processo
            for item in elegiveis_ordenados
            if item.caso.numero_processo in mencoes_altas
        }
        pubs_candidatos_cache = _publicacoes_dos_casos(cadernos, numeros_mencao_elegiveis)

        if usar_cache_rodada:
            salvar_cache_rodada(
                pasta_da_rodada,
                cadernos=cadernos_brutos,
                cadernos_historico=cadernos_historico,
                sigla=sigla,
                inicio=inicio,
                fim=fim,
                historico=historico,
                ano_referencia=momento.year,
                contagens={
                    "publicacoes_lidas": publicacoes_lidas,
                    "publicacoes_cobranca": publicacoes_cobranca,
                    "processos": total_processos,
                    "processos_so_empresa": total_so_empresa,
                    "processos_banco": total_banco,
                    "processos_acordo": total_acordo,
                    "processos_recentes": total_recentes,
                },
                totais_comunicacoes=totais_comunicacoes,
                elegiveis_ordenados=elegiveis_ordenados,
                mencoes_altas=mencoes_altas,
                pubs_candidatos=pubs_candidatos_cache,
            )

    capas_locais = indexar_capas_locais(
        [pasta_aprofundamento, *pastas_capas_extras],
        pasta_capas_filtro,
    )

    verificacoes: dict[str, VerificacaoValor] = {}
    cnjs_validos: dict[str, str] = {}
    reutilizados_locais = 0

    for item in elegiveis_ordenados:
        numero_raw = item.caso.numero_processo
        try:
            cnj_norm = normalizar_cnj_tjsp(numero_raw)
        except ValueError as erro:
            verificacoes[numero_raw] = _verificacao_cnj_invalido(numero_raw, str(erro))
            continue
        cnjs_validos[numero_raw] = cnj_norm
        local = capas_locais.get(cnj_norm)
        if local is not None:
            verificacoes[numero_raw] = local
            reutilizados_locais += 1
        else:
            verificacoes[numero_raw] = _verificacao_nao_consultado(cnj_norm)

    consultas_nesta_rodada = 0
    interrompido_por: str | None = None

    if not somente_capas_locais and max_consultas > 0:
        candidatos_consulta = [
            item
            for item in elegiveis_ordenados
            if item.caso.numero_processo in cnjs_validos
            and not verificacoes[item.caso.numero_processo].resolvido_localmente
            and (not so_mencao_diario or item.caso.numero_processo in mencoes_altas)
        ]
        # Prioriza processos com menção no diário > R$ 600 mil (sem confirmar),
        # preservando score e desempates dentro de cada faixa.
        candidatos_consulta.sort(
            key=lambda item: (
                0 if item.caso.numero_processo in mencoes_altas else 1,
                _chave_ordenacao(item),
            )
        )
        fila = candidatos_consulta[:max_consultas]
        if fila:
            esaj = cliente_esaj if cliente_esaj is not None else ClienteEsaj(intervalo=intervalo)
            iniciado = False
            try:
                for item in fila:
                    if not iniciado:
                        try:
                            impedimento = diagnostico(esaj.iniciar())  # type: ignore[attr-defined]
                            if impedimento:
                                interrompido_por = impedimento
                                break
                        except FalhaConsulta as erro:
                            interrompido_por = erro.status
                            break
                        iniciado = True

                    numero_raw = item.caso.numero_processo
                    cnj_norm = cnjs_validos[numero_raw]
                    verificacao, motivo_parada = consultar_capa_esaj(
                        cnj_norm,
                        esaj,
                        pasta_capas_filtro,
                    )
                    consultas_nesta_rodada += 1
                    verificacoes[numero_raw] = verificacao
                    registrar_evento_verificacao(pasta_da_rodada, verificacao)
                    if motivo_parada is not None:
                        interrompido_por = motivo_parada
                        break
            except KeyboardInterrupt:
                interrompido_por = "interrompido_pelo_usuario"

    confirmados_acima: list[CasoConfirmado] = []
    confirmados_ate: list[CasoPontuado] = []
    pendentes: list[CasoPendente] = []
    candidatos_diario: list[CandidatoDiario] = []
    candidatos_mencao_pendentes = 0
    contagem_motivos: Counter[str] = Counter()

    for item in elegiveis_ordenados:
        numero_raw = item.caso.numero_processo
        ver = verificacoes[numero_raw]
        mencao = mencoes_altas.get(numero_raw)
        if mencao is not None:
            candidatos_diario.append(CandidatoDiario(item, ver, mencao))
            if not ver.resolvido_localmente:
                candidatos_mencao_pendentes += 1
        if ver.status is StatusValor.CONFIRMADO_ACIMA:
            confirmados_acima.append(CasoConfirmado(item, ver))
        elif ver.status is StatusValor.CONFIRMADO_ATE:
            confirmados_ate.append(item)
        else:
            pendentes.append(
                CasoPendente(
                    item,
                    ver,
                    mencao_valor_alto=mencao,
                )
            )
            contagem_motivos[ver.motivo or MotivoPendencia.NAO_CONSULTADO] += 1

    assert (
        len(confirmados_acima) + len(confirmados_ate) + len(pendentes)
        == len(elegiveis_ordenados)
    )

    exportados = (
        confirmados_acima if limite is None else confirmados_acima[:limite]
    )
    numeros_exportados = {
        item.caso_pontuado.caso.numero_processo for item in exportados
    }
    publicacoes: dict[str, list[Publicacao]] = {}
    faltantes_pubs: set[str] = set()
    for numero in numeros_exportados:
        if numero in pubs_candidatos_cache:
            publicacoes[numero] = pubs_candidatos_cache[numero]
        else:
            faltantes_pubs.add(numero)
    if faltantes_pubs:
        publicacoes.update(_publicacoes_dos_casos(cadernos, faltantes_pubs))

    caminho_planilha = pasta_filtro / f"casos_djen_{inicio:%Y-%m-%d}_a_{fim:%Y-%m-%d}.xlsx"
    resumo = ResumoRodadaFiltrada(
        inicio=inicio,
        fim=fim,
        tribunal=sigla,
        cadernos=[info for info, _caminho in cadernos],
        dias_sem_caderno=dias_sem_caderno,
        publicacoes_lidas=publicacoes_lidas,
        publicacoes_cobranca=publicacoes_cobranca,
        processos=total_processos,
        processos_so_empresa=total_so_empresa,
        processos_banco=total_banco,
        processos_acordo=total_acordo,
        processos_recentes=total_recentes,
        dias_historico=len(cadernos_historico),
        elegiveis=len(elegiveis_ordenados),
        confirmados_acima_corte=len(confirmados_acima),
        confirmados_ate_corte=len(confirmados_ate),
        pendentes=len(pendentes),
        exportados=len(exportados),
        limite_exibicao=limite,
        consultas_nesta_rodada=consultas_nesta_rodada,
        reutilizados_locais=reutilizados_locais,
        somente_capas_locais=somente_capas_locais,
        gerado_em=momento,
        interrompido_por=interrompido_por,
        pendencias_por_motivo=dict(contagem_motivos),
        so_mencao_diario=so_mencao_diario,
        candidatos_mencao_diario=len(candidatos_diario),
        candidatos_mencao_pendentes=candidatos_mencao_pendentes,
        cache_cadernos_reutilizado=cache_cadernos_reutilizado,
    )

    gravar_pendentes_csv(pasta_da_rodada, pendentes)
    gravar_candidatos_diario_csv(pasta_da_rodada, candidatos_diario)
    escrever_planilha_filtrada(
        caminho_planilha,
        exportados,
        publicacoes,
        pendentes,
        resumo,
        candidatos_diario=candidatos_diario if so_mencao_diario else None,
    )
    gravar_resumo_rodada(pasta_da_rodada, resumo, caminho_planilha)
    return caminho_planilha, resumo
