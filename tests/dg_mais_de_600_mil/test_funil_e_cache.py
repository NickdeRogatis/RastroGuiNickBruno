"""Testes do funil por menção no diário (--so-mencao-diario) e do cache da rodada."""

import hashlib
from datetime import date, datetime
from pathlib import Path

from openpyxl import load_workbook

import guicredito.dg_mais_de_600_mil.pipeline as pipeline_filtro
from guicredito.aprofundamento.cnj import formatar
from guicredito.dg_mais_de_600_mil.cli import parse_args_filtro
from guicredito.dg_mais_de_600_mil.pipeline import rodar_mais_de_600_mil
from tests.dg_mais_de_600_mil.test_aceite_e_isolamento import (
    ClienteEsajFalso,
    _cliente_djen,
    _pub_elegivel,
    cnj,
    html_capa,
    salvar_capa,
)


def test_funil_so_mencao_diario_consulta_apenas_candidatos_e_cria_aba(tmp_path, item, fazer_zip):
    n_sem_mencao = cnj(101)
    n_mencao_acima = cnj(102)
    n_mencao_abaixo = cnj(103)

    itens = [
        # Score maior, mas sem menção > 600k no diário -> NÃO deve ser consultado no modo --so-mencao-diario
        _pub_elegivel(
            item,
            1,
            n_sem_mencao,
            nomeClasse="CUMPRIMENTO DE SENTENÇA",
            texto="<p>Imóvel penhorado. Pesquisa SISBAJUD infrutífera.</p>",
        ),
        # Menção > 600k no diário -> consultado e confirmado acima na capa
        _pub_elegivel(
            item,
            2,
            n_mencao_acima,
            texto="<p>Débito atualizado em R$ 1.200.000,00.</p>",
        ),
        # Menção > 600k no diário -> consultado e confirmado abaixo na capa (não gera falso positivo!)
        _pub_elegivel(
            item,
            3,
            n_mencao_abaixo,
            texto="<p>Imóvel avaliado em R$ 2 milhões para leilão.</p>",
        ),
    ]
    cliente_djen = _cliente_djen(tmp_path, fazer_zip, {date(2026, 11, 6): itens})
    esaj = ClienteEsajFalso(
        [
            html_capa(n_mencao_acima, "R$ 950.000,00"),
            html_capa(n_mencao_abaixo, "R$ 300.000,00"),
        ]
    )
    pasta_filtro = tmp_path / "filtro"

    planilha, resumo = rodar_mais_de_600_mil(
        date(2026, 11, 6),
        date(2026, 11, 6),
        pasta_dados=tmp_path / "dados",
        pasta_aprofundamento=tmp_path / "aprofundamento",
        pasta_filtro=pasta_filtro,
        cliente_djen=cliente_djen,
        cliente_esaj=esaj,
        so_mencao_diario=True,
        max_consultas=10,
        agora=datetime(2026, 11, 10, 10, 0),
    )

    assert len(esaj.urls) == 2
    assert all(formatar(n_sem_mencao)[:15] not in u for u in esaj.urls)
    assert resumo.elegiveis == 3
    assert resumo.candidatos_mencao_diario == 2
    assert resumo.candidatos_mencao_pendentes == 0
    assert resumo.confirmados_acima_corte == 1
    assert resumo.confirmados_ate_corte == 1
    assert resumo.pendentes == 1
    assert resumo.so_mencao_diario is True

    wb = load_workbook(planilha)
    assert wb.sheetnames == ["Casos", "Publicações", "Candidatos (diário)", "Pendentes", "Como ler"]
    casos = list(wb["Casos"].iter_rows(min_row=2, values_only=True))
    assert len(casos) == 1
    assert casos[0][2] == formatar(n_mencao_acima)

    candidatos = list(wb["Candidatos (diário)"].iter_rows(min_row=2, values_only=True))
    assert len(candidatos) == 2
    situacoes = {row[2]: row[9] for row in candidatos}
    assert situacoes[formatar(n_mencao_acima)] == "Confirmado acima de R$ 600.000,00"
    assert situacoes[formatar(n_mencao_abaixo)] == "Confirmado até R$ 600.000,00"

    assert (
        pasta_filtro / "rodadas" / "TJSP_2026-11-06_a_2026-11-06" / "candidatos_diario.csv"
    ).is_file()


def test_cache_da_rodada_acelera_retomada_e_invalida_se_caderno_mudar(
    tmp_path, item, fazer_zip, monkeypatch
):
    n1 = cnj(201)
    n2 = cnj(202)
    itens = [
        _pub_elegivel(item, 1, n1, texto="<p>Execução no valor de R$ 900.000,00.</p>"),
        _pub_elegivel(item, 2, n2, texto="<p>Avaliação de imóvel em R$ 1,5 milhão.</p>"),
    ]
    cliente_djen = _cliente_djen(tmp_path / "c1", fazer_zip, {date(2026, 11, 6): itens})
    pasta_filtro = tmp_path / "filtro"
    pasta_aprov = tmp_path / "aprofundamento"

    # Rodada 1: lê o zip e grava cache_rodada.json.gz; consulta só n1 (max_consultas=1)
    esaj_1 = ClienteEsajFalso([html_capa(n1, "R$ 800.000,00")])
    _, r1 = rodar_mais_de_600_mil(
        date(2026, 11, 6),
        date(2026, 11, 6),
        pasta_dados=tmp_path / "dados",
        pasta_aprofundamento=pasta_aprov,
        pasta_filtro=pasta_filtro,
        cliente_djen=cliente_djen,
        cliente_esaj=esaj_1,
        so_mencao_diario=True,
        max_consultas=1,
        agora=datetime(2026, 11, 10, 10, 0),
    )
    assert r1.cache_cadernos_reutilizado is False
    assert r1.confirmados_acima_corte == 1
    assert r1.candidatos_mencao_pendentes == 1

    # Incorpora n2 localmente em aprofundamento e bloqueia ler_caderno para provar que o cache evita reler o zip!
    salvar_capa(pasta_aprov / "novo", n2, html_capa(n2, "R$ 750.000,00"))

    def _nao_deve_ler(_caminho):
        raise AssertionError("ler_caderno não deveria ser chamado quando o cache está válido")

    monkeypatch.setattr(pipeline_filtro, "ler_caderno", _nao_deve_ler)

    planilha, r2 = rodar_mais_de_600_mil(
        date(2026, 11, 6),
        date(2026, 11, 6),
        pasta_dados=tmp_path / "dados",
        pasta_aprofundamento=pasta_aprov,
        pasta_filtro=pasta_filtro,
        cliente_djen=cliente_djen,
        so_mencao_diario=True,
        somente_capas_locais=True,
        agora=datetime(2026, 11, 10, 10, 5),
    )
    assert r2.cache_cadernos_reutilizado is True
    assert r2.confirmados_acima_corte == 2
    assert r2.candidatos_mencao_pendentes == 0
    wb = load_workbook(planilha)
    assert wb["Casos"].max_row == 3
    assert wb["Publicações"].max_row == 3


def test_parse_args_so_mencao_diario_e_sem_cache():
    args = parse_args_filtro(
        [
            "--mais-de-600-mil",
            "--inicio",
            "2026-11-17",
            "--fim",
            "2026-11-23",
            "--so-mencao-diario",
            "--sem-cache",
            "--max-consultas",
            "30",
        ]
    )
    assert args.so_mencao_diario is True
    assert args.sem_cache is True
    assert args.max_consultas == 30
