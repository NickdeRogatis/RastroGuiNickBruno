"""Testes de aceite e isolamento de pastas para o modo ``--mais-de-600-mil``."""

import hashlib
import json
from datetime import date, datetime
from pathlib import Path

from openpyxl import load_workbook

from guicredito.aprofundamento.cliente import FalhaConsulta
from guicredito.aprofundamento.cnj import formatar
from guicredito.dg_mais_de_600_mil.capas import importar_capa_html
from guicredito.dg_mais_de_600_mil.modelos import MotivoPendencia
from guicredito.dg_mais_de_600_mil.pipeline import rodar_mais_de_600_mil
from guicredito.djen.fonte import URL_CADERNO
from guicredito.djen.pipeline import rodar as rodar_normal
from tests.djen.conftest import ClienteFalso


def cnj(i: int, ano: int = 2020) -> str:
    base = f"{i:07d}{ano}8260001"
    dd = 98 - int(base + "00") % 97
    return f"{i:07d}{dd:02d}{ano}8260001"


def html_capa(numero: str, valor: str | None) -> str:
    campo_valor = f'<div id="valorAcaoProcesso">{valor}</div>' if valor is not None else ""
    return (
        f'<html><span id="numeroProcesso">{formatar(numero)}</span>'
        f'<div id="classeProcesso">Execução de título extrajudicial</div>'
        f"{campo_valor}</html>"
    )


def salvar_capa(pasta_raiz: Path, numero: str, html: str, *, numero_json: str | None = None) -> Path:
    pasta = pasta_raiz / numero
    pasta.mkdir(parents=True, exist_ok=True)
    raw = html.encode("utf-8")
    (pasta / "consulta.html.txt").write_bytes(raw)
    dados = {
        "numero_processo": numero_json or numero,
        "status": "coletado",
        "consultado_em": "2026-11-24T12:00:00+00:00",
        "fonte": "TJSP e-SAJ — consulta pública de 1º grau",
        "url_consulta": f"https://esaj.tjsp.jus.br/cpopg/search.do?n={numero}",
        "url_pagina": f"https://esaj.tjsp.jus.br/cpopg/show.do?n={numero}",
        "evidencias": [{"arquivo": "consulta.html.txt", "sha256": hashlib.sha256(raw).hexdigest()}],
    }
    destino = pasta / "resultado.json"
    destino.write_text(json.dumps(dados, ensure_ascii=False), encoding="utf-8")
    return destino


def _cliente_djen(tmp_path: Path, fazer_zip, dias: dict[date, list[dict]]) -> ClienteFalso:
    metadados: dict[str, dict] = {}
    arquivos: dict[str, bytes] = {}
    brutos = tmp_path / "brutos_teste"
    brutos.mkdir(parents=True, exist_ok=True)
    for dia, itens in dias.items():
        zip_path = fazer_zip(brutos, f"fonte-{dia.isoformat()}", [itens])
        conteudo = zip_path.read_bytes()
        url_zip = f"https://s3/{dia.isoformat()}"
        metadados[URL_CADERNO.format(sigla="TJSP", data=dia.isoformat())] = {
            "sigla_tribunal": "TJSP",
            "versao": 1,
            "data": dia.isoformat(),
            "total_comunicacoes": len(itens),
            "numero_paginas": 1,
            "tamanho_bytes": len(conteudo),
            "hash": hashlib.sha256(conteudo).hexdigest(),
            "url": url_zip,
        }
        arquivos[url_zip] = conteudo
    return ClienteFalso(metadados, arquivos)


class ClienteEsajFalso:
    def __init__(self, respostas: list[object]):
        self.respostas = list(respostas)
        self.urls: list[str] = []
        self.inicios = 0

    def iniciar(self) -> str:
        self.inicios += 1
        return "<html>Consulta pública TJSP</html>"

    def get(self, url: str) -> str:
        self.urls.append(url)
        prox = self.respostas.pop(0)
        if isinstance(prox, Exception):
            raise prox
        return str(prox)


def _hashes_arvore(raiz: Path) -> dict[str, str]:
    if not raiz.exists():
        return {}
    resultado: dict[str, str] = {}
    for arquivo in sorted(raiz.rglob("*")):
        if arquivo.is_file():
            rel = arquivo.relative_to(raiz).as_posix()
            resultado[rel] = hashlib.sha256(arquivo.read_bytes()).hexdigest()
    return resultado


def _pub_elegivel(item, idx: int, numero: str, *, texto: str = "<p>Intime-se.</p>", **extra) -> dict:
    base = dict(
        id=idx,
        data_disponibilizacao="2026-11-06",
        numero_processo=numero,
        texto=texto,
        destinatarios=[
            {"nome": "EMPRESA EXEMPLO LTDA", "polo": "A"},
            {"nome": f"JOÃO EXEMPLO PESSOA {idx}", "polo": "P"},
        ],
    )
    base.update(extra)
    return item(**base)


def test_aceite_1_e_2_normal_preservado_e_isolamento_bidirecional(tmp_path, item, fazer_zip):
    projeto = tmp_path / "projeto"
    pasta_dados = projeto / "dados" / "cadernos"
    pasta_saida = projeto / "saida"
    pasta_aprofundamento = pasta_saida / "aprofundamento"
    pasta_pessoas = pasta_saida / "pessoas"
    pasta_filtro = pasta_saida / "DG__mais_de_600_mil"

    n1 = cnj(1)
    n2 = cnj(2)
    dia_06 = [
        _pub_elegivel(item, 1, n1, texto="<p>A pesquisa via SISBAJUD restou infrutífera.</p>"),
    ]
    dia_09 = [
        _pub_elegivel(
            item,
            2,
            n2,
            data_disponibilizacao="2026-11-09",
            texto="<p>Defiro penhora de imóvel.</p>",
        ),
    ]
    cliente_dia06 = _cliente_djen(tmp_path / "c1", fazer_zip, {date(2026, 11, 6): dia_06})
    cliente_dois_dias = _cliente_djen(
        tmp_path / "c2",
        fazer_zip,
        {date(2026, 11, 6): dia_06, date(2026, 11, 9): dia_09},
    )

    # 1) Roda normal em 06/11 e confirma que a pasta do filtro ainda não existe
    planilha_normal, resumo_normal = rodar_normal(
        date(2026, 11, 6),
        date(2026, 11, 6),
        pasta_dados=pasta_dados,
        pasta_saida=pasta_saida,
        cliente=cliente_dia06,
        agora=datetime(2026, 11, 10, 10, 0),
    )
    assert planilha_normal == pasta_saida / "casos_djen_2026-11-06_a_2026-11-06.xlsx"
    assert not pasta_filtro.exists()
    assert resumo_normal.casos_na_planilha == 1

    # Simula edição manual do usuário na planilha normal + arquivos em aprofundamento e pessoas
    wb_norm = load_workbook(planilha_normal)
    wb_norm["Como ler"]["C1"] = "Anotação manual do usuário"
    wb_norm.save(planilha_normal)

    salvar_capa(pasta_aprofundamento / "lote_exemplo", n1, html_capa(n1, "R$ 700.000,00"))
    (pasta_pessoas / "lote_p").mkdir(parents=True, exist_ok=True)
    (pasta_pessoas / "lote_p" / "manifesto.json").write_text('{"ok": true}\n', encoding="utf-8")

    antes_dados = _hashes_arvore(pasta_dados)
    antes_aprov = _hashes_arvore(pasta_aprofundamento)
    antes_pessoas = _hashes_arvore(pasta_pessoas)
    hash_planilha_normal = hashlib.sha256(planilha_normal.read_bytes()).hexdigest()

    # 2) Roda o filtro para 06/11 a 09/11 (06/11 existe em dados/cadernos; 09/11 precisa baixar -> vai para pasta_filtro/cadernos)
    esaj_1 = ClienteEsajFalso([FalhaConsulta("erro_rede", "sem conexão")])
    planilha_filtro, resumo_f1 = rodar_mais_de_600_mil(
        date(2026, 11, 6),
        date(2026, 11, 9),
        pasta_dados=pasta_dados,
        pasta_aprofundamento=pasta_aprofundamento,
        pasta_filtro=pasta_filtro,
        cliente_djen=cliente_dois_dias,
        cliente_esaj=esaj_1,
        agora=datetime(2026, 11, 10, 10, 5),
    )
    assert planilha_filtro == pasta_filtro / "casos_djen_2026-11-06_a_2026-11-09.xlsx"
    assert (pasta_filtro / "cadernos" / "TJSP-D-2026-11-09_v1.zip").is_file()
    assert not (pasta_filtro / "cadernos" / "TJSP-D-2026-11-06_v1.zip").exists()
    assert resumo_f1.confirmados_acima_corte == 1

    # Retoma o filtro com resposta válida para n2
    esaj_2 = ClienteEsajFalso([html_capa(n2, "R$ 800.000,00")])
    _, resumo_f2 = rodar_mais_de_600_mil(
        date(2026, 11, 6),
        date(2026, 11, 9),
        pasta_dados=pasta_dados,
        pasta_aprofundamento=pasta_aprofundamento,
        pasta_filtro=pasta_filtro,
        cliente_djen=cliente_dois_dias,
        cliente_esaj=esaj_2,
        agora=datetime(2026, 11, 10, 10, 10),
    )
    assert resumo_f2.confirmados_acima_corte == 2

    # Confere que NADA fora de saida/DG__mais_de_600_mil/ mudou
    assert _hashes_arvore(pasta_dados) == antes_dados
    assert _hashes_arvore(pasta_aprofundamento) == antes_aprov
    assert _hashes_arvore(pasta_pessoas) == antes_pessoas
    assert hashlib.sha256(planilha_normal.read_bytes()).hexdigest() == hash_planilha_normal
    # Nenhum arquivo novo na raiz de saida/ além da planilha normal e das subpastas conhecidas
    assert sorted(p.name for p in pasta_saida.iterdir()) == [
        "DG__mais_de_600_mil",
        "aprofundamento",
        "casos_djen_2026-11-06_a_2026-11-06.xlsx",
        "pessoas",
    ]

    # 3) Roda o modo normal de novo e confere que TODOS os arquivos do filtro foram preservados
    antes_filtro = _hashes_arvore(pasta_filtro)
    assert antes_filtro  # há arquivos gravados no filtro
    rodar_normal(
        date(2026, 11, 6),
        date(2026, 11, 6),
        pasta_dados=pasta_dados,
        pasta_saida=pasta_saida,
        cliente=cliente_dia06,
        agora=datetime(2026, 11, 10, 10, 15),
    )
    assert _hashes_arvore(pasta_filtro) == antes_filtro


def test_aceite_3_301_elegiveis_so_o_301o_acima_de_600_mil_com_limite_1(tmp_path, item, fazer_zip):
    itens: list[dict] = []
    # 300 primeiros têm sinal forte (imóvel penhorado +15, desgaste +10, cumprimento +10, credor +5 = 40 pts)
    for i in range(1, 301):
        itens.append(
            _pub_elegivel(
                item,
                i,
                cnj(i, ano=2018),
                nomeClasse="CUMPRIMENTO DE SENTENÇA",
                texto="<p>Lavre-se o termo de penhora do imóvel. Pesquisa SISBAJUD infrutífera.</p>",
            )
        )
    # 301º tem pontuação menor (somente credor empresa +5, ano mais recente 2024)
    n301 = cnj(301, ano=2024)
    itens.append(
        _pub_elegivel(
            item,
            301,
            n301,
            nomeClasse="EXECUÇÃO DE TÍTULO EXTRAJUDICIAL",
            texto="<p>Intime-se.</p>",
        )
    )

    pasta_aprov = tmp_path / "aprofundamento"
    salvar_capa(pasta_aprov / "manual", n301, html_capa(n301, "R$ 600.000,01"))
    cliente = _cliente_djen(tmp_path, fazer_zip, {date(2026, 11, 6): itens})

    # Primeiro confere que no modo normal (limite 300) o 301º ficaria de fora
    planilha_norm, resumo_norm = rodar_normal(
        date(2026, 11, 6),
        date(2026, 11, 6),
        pasta_dados=tmp_path / "dados_norm",
        pasta_saida=tmp_path / "saida_norm",
        cliente=cliente,
        agora=datetime(2026, 11, 10, 10, 0),
    )
    assert resumo_norm.casos_na_planilha == 300
    procs_norm = {
        row[2] for row in load_workbook(planilha_norm)["Casos"].iter_rows(min_row=2, values_only=True)
    }
    assert formatar(n301) not in procs_norm

    # Agora no modo filtrado com --limite 1: o 301º entra em Casos com seu score original (5)
    planilha_filtro, resumo = rodar_mais_de_600_mil(
        date(2026, 11, 6),
        date(2026, 11, 6),
        limite=1,
        pasta_dados=tmp_path / "dados_norm",
        pasta_aprofundamento=pasta_aprov,
        pasta_filtro=tmp_path / "saida_filtro",
        cliente_djen=cliente,
        somente_capas_locais=True,
        agora=datetime(2026, 11, 10, 10, 0),
    )
    assert resumo.elegiveis == 301
    assert resumo.confirmados_acima_corte == 1
    assert resumo.confirmados_ate_corte == 0
    assert resumo.pendentes == 300
    assert resumo.exportados == 1
    assert resumo.cobertura_parcial is True

    wb = load_workbook(planilha_filtro)
    linhas = list(wb["Casos"].iter_rows(min_row=2, values_only=True))
    assert len(linhas) == 1
    assert linhas[0][1] == 5
    assert linhas[0][2] == formatar(n301)
    assert linhas[0][15] == 600000.01


def test_aceite_4_fronteira_monetaria_599999_600000_60000001(tmp_path, item, fazer_zip):
    n_baixo = cnj(1)
    n_igual = cnj(2)
    n_acima = cnj(3)
    itens = [
        _pub_elegivel(item, 1, n_baixo),
        _pub_elegivel(item, 2, n_igual),
        _pub_elegivel(item, 3, n_acima),
    ]
    pasta_aprov = tmp_path / "aprofundamento"
    salvar_capa(pasta_aprov / "lote", n_baixo, html_capa(n_baixo, "R$ 599.999,99"))
    salvar_capa(pasta_aprov / "lote", n_igual, html_capa(n_igual, "R$ 600.000,00"))
    salvar_capa(pasta_aprov / "lote", n_acima, html_capa(n_acima, "R$ 600.000,01"))
    cliente = _cliente_djen(tmp_path, fazer_zip, {date(2026, 11, 6): itens})

    planilha, resumo = rodar_mais_de_600_mil(
        date(2026, 11, 6),
        date(2026, 11, 6),
        pasta_dados=tmp_path / "dados",
        pasta_aprofundamento=pasta_aprov,
        pasta_filtro=tmp_path / "filtro",
        cliente_djen=cliente,
        somente_capas_locais=True,
        agora=datetime(2026, 11, 10, 10, 0),
    )
    assert resumo.elegiveis == 3
    assert resumo.confirmados_acima_corte == 1
    assert resumo.confirmados_ate_corte == 2
    assert resumo.pendentes == 0
    assert resumo.exportados == 1
    assert resumo.cobertura_parcial is False

    wb = load_workbook(planilha)
    assert wb.sheetnames == ["Casos", "Publicações", "Pendentes", "Como ler"]
    linhas = list(wb["Casos"].iter_rows(min_row=2, values_only=True))
    assert len(linhas) == 1
    assert linhas[0][2] == formatar(n_acima)
    assert linhas[0][15] == 600000.01
    assert "TJSP e-SAJ" in str(linhas[0][16])
    assert linhas[0][17] == datetime(2026, 11, 24, 0, 0)


def test_aceite_5_publicacao_repetida_leilao_2mi_capa_sem_valor_e_cnj_divergente(
    tmp_path, item, fazer_zip
):
    n_rep = cnj(10)
    n_sem_valor = cnj(11)
    n_divergente = cnj(12)
    n_outro = cnj(99)

    itens = [
        _pub_elegivel(
            item,
            1,
            n_rep,
            texto="<p>Designo leilão do imóvel avaliado em R$ 2 milhões.</p>",
        ),
        _pub_elegivel(
            item,
            2,
            n_rep,
            texto="<p>Reitero a intimação sobre o leilão de R$ 2.000.000,00.</p>",
        ),
        _pub_elegivel(item, 3, n_sem_valor, texto="<p>Intime-se.</p>"),
        _pub_elegivel(item, 4, n_divergente, texto="<p>Intime-se.</p>"),
    ]
    pasta_aprov = tmp_path / "aprofundamento"
    salvar_capa(pasta_aprov / "lote", n_sem_valor, html_capa(n_sem_valor, None))
    salvar_capa(pasta_aprov / "lote", n_divergente, html_capa(n_outro, "R$ 5.000.000,00"))
    cliente = _cliente_djen(tmp_path, fazer_zip, {date(2026, 11, 6): itens})

    planilha, resumo = rodar_mais_de_600_mil(
        date(2026, 11, 6),
        date(2026, 11, 6),
        pasta_dados=tmp_path / "dados",
        pasta_aprofundamento=pasta_aprov,
        pasta_filtro=tmp_path / "filtro",
        cliente_djen=cliente,
        somente_capas_locais=True,
        agora=datetime(2026, 11, 10, 10, 0),
    )
    # 1 processo por CNJ (n_rep consolidado), zero falsos positivos
    assert resumo.elegiveis == 3
    assert resumo.confirmados_acima_corte == 0
    assert resumo.confirmados_ate_corte == 0
    assert resumo.pendentes == 3
    assert resumo.pendencias_por_motivo[MotivoPendencia.NAO_CONSULTADO] == 1
    assert resumo.pendencias_por_motivo[MotivoPendencia.CAPA_SEM_VALOR] == 1
    assert resumo.pendencias_por_motivo[MotivoPendencia.CAPA_CNJ_DIVERGENTE] == 1

    wb = load_workbook(planilha)
    assert wb["Casos"].max_row == 1
    pendentes = list(wb["Pendentes"].iter_rows(min_row=2, values_only=True))
    assert len(pendentes) == 3
    assert len({row[0] for row in pendentes}) == 3


def test_aceite_6_acordo_em_outro_processo_fora_do_filtro_mantem_pontuacao(
    tmp_path, item, fazer_zip
):
    devedor_comum = {"nome": "JOSÉ CARLOS DA SILVA", "polo": "P"}
    n_acordo = cnj(20)
    n_alvo = cnj(21)

    dia_05 = [
        item(
            id=1,
            data_disponibilizacao="2026-11-05",
            numero_processo=n_acordo,
            texto="<p>Homologo o acordo celebrado entre as partes.</p>",
            destinatarios=[{"nome": "EMPRESA EXEMPLO LTDA", "polo": "A"}, devedor_comum],
        )
    ]
    dia_06 = [
        item(
            id=2,
            data_disponibilizacao="2026-11-06",
            numero_processo=n_alvo,
            texto="<p>Intime-se.</p>",
            destinatarios=[{"nome": "LOJA EXEMPLO LTDA", "polo": "A"}, devedor_comum],
        )
    ]
    cliente = _cliente_djen(
        tmp_path, fazer_zip, {date(2026, 11, 5): dia_05, date(2026, 11, 6): dia_06}
    )
    pasta_aprov = tmp_path / "aprofundamento"
    salvar_capa(pasta_aprov / "lote", n_acordo, html_capa(n_acordo, "R$ 50.000,00"))
    salvar_capa(pasta_aprov / "lote", n_alvo, html_capa(n_alvo, "R$ 750.000,00"))

    planilha_norm, _ = rodar_normal(
        date(2026, 11, 6),
        date(2026, 11, 6),
        historico=1,
        pasta_dados=tmp_path / "dados",
        pasta_saida=tmp_path / "saida_norm",
        cliente=cliente,
        agora=datetime(2026, 11, 10, 10, 0),
    )
    linha_norm = list(load_workbook(planilha_norm)["Casos"].iter_rows(min_row=2, values_only=True))[0]

    planilha_filtro, resumo = rodar_mais_de_600_mil(
        date(2026, 11, 6),
        date(2026, 11, 6),
        historico=1,
        pasta_dados=tmp_path / "dados",
        pasta_aprofundamento=pasta_aprov,
        pasta_filtro=tmp_path / "saida_filtro",
        cliente_djen=cliente,
        somente_capas_locais=True,
        agora=datetime(2026, 11, 10, 10, 0),
    )
    assert resumo.confirmados_acima_corte == 1
    linha_filtro = list(
        load_workbook(planilha_filtro)["Casos"].iter_rows(min_row=2, values_only=True)
    )[0]
    # Mesmo score (+30 de acordo em outro processo + 5 credor = 35) e mesmos sinais
    assert linha_filtro[1] == linha_norm[1] == 35
    assert "acordo em outro processo" in str(linha_filtro[10])


def test_aceite_7_interrupcao_e_retomada_sem_duplicar_nem_repetir_consultas(
    tmp_path, item, fazer_zip
):
    n1 = cnj(30)
    n2 = cnj(31)
    n3 = cnj(32)
    n4 = cnj(33)
    itens = [
        _pub_elegivel(item, 1, n1, texto="<p>Leilão de imóvel em R$ 2 milhões.</p>"),
        _pub_elegivel(item, 2, n2, texto="<p>Pesquisa SISBAJUD infrutífera.</p>"),
        _pub_elegivel(item, 3, n3, texto="<p>Intime-se.</p>"),
        _pub_elegivel(item, 4, n4, texto="<p>Intime-se.</p>"),
    ]
    cliente_djen = _cliente_djen(tmp_path, fazer_zip, {date(2026, 11, 6): itens})
    pasta_filtro = tmp_path / "filtro"

    # Rodada 1: consulta n1 (priorizado pela menção no diário -> acima), n2 (abaixo), n3 (bloqueado -> para!)
    esaj_1 = ClienteEsajFalso(
        [
            html_capa(n1, "R$ 900.000,00"),
            html_capa(n2, "R$ 150.000,00"),
            FalhaConsulta("bloqueado", "HTTP 403"),
        ]
    )
    planilha, r1 = rodar_mais_de_600_mil(
        date(2026, 11, 6),
        date(2026, 11, 6),
        pasta_dados=tmp_path / "dados",
        pasta_aprofundamento=tmp_path / "aprofundamento",
        pasta_filtro=pasta_filtro,
        cliente_djen=cliente_djen,
        cliente_esaj=esaj_1,
        max_consultas=10,
        agora=datetime(2026, 11, 10, 10, 0),
    )
    assert r1.elegiveis == 4
    assert r1.confirmados_acima_corte == 1
    assert r1.confirmados_ate_corte == 1
    assert r1.pendentes == 2
    assert r1.interrompido_por == "bloqueado"
    assert r1.consultas_nesta_rodada == 3
    assert r1.pendencias_por_motivo[MotivoPendencia.CONSULTA_INTERROMPIDA] == 1
    assert r1.pendencias_por_motivo[MotivoPendencia.NAO_CONSULTADO] == 1

    # Incorpora n4 manualmente antes de retomar
    html_n4 = tmp_path / "n4.html"
    html_n4.write_text(html_capa(n4, "R$ 610.000,00"), encoding="utf-8")
    importar_capa_html(n4, html_n4, pasta_filtro / "capas")

    # Rodada 2 (retomada): só n3 deve ser consultado online! n1, n2 e n4 já resolvidos localmente
    esaj_2 = ClienteEsajFalso([html_capa(n3, "R$ 700.000,00")])
    planilha2, r2 = rodar_mais_de_600_mil(
        date(2026, 11, 6),
        date(2026, 11, 6),
        pasta_dados=tmp_path / "dados",
        pasta_aprofundamento=tmp_path / "aprofundamento",
        pasta_filtro=pasta_filtro,
        cliente_djen=cliente_djen,
        cliente_esaj=esaj_2,
        max_consultas=10,
        agora=datetime(2026, 11, 10, 10, 5),
    )
    assert planilha2 == planilha
    assert len(esaj_2.urls) == 1
    assert formatar(n3)[:15] in esaj_2.urls[0]
    assert r2.consultas_nesta_rodada == 1
    assert r2.confirmados_acima_corte == 3
    assert r2.confirmados_ate_corte == 1
    assert r2.pendentes == 0
    assert r2.cobertura_parcial is False

    wb = load_workbook(planilha2)
    procs_casos = [row[2] for row in wb["Casos"].iter_rows(min_row=2, values_only=True)]
    assert len(procs_casos) == 3
    assert len(set(procs_casos)) == 3
    assert wb["Pendentes"].max_row == 1


def test_aceite_8_nenhum_confirmado_com_pendentes_e_cobertura_parcial(tmp_path, item, fazer_zip):
    n1 = cnj(40)
    n2 = cnj(41)
    itens = [_pub_elegivel(item, 1, n1), _pub_elegivel(item, 2, n2)]
    cliente = _cliente_djen(tmp_path, fazer_zip, {date(2026, 11, 6): itens})

    planilha, resumo = rodar_mais_de_600_mil(
        date(2026, 11, 6),
        date(2026, 11, 6),
        pasta_dados=tmp_path / "dados",
        pasta_aprofundamento=tmp_path / "aprofundamento",
        pasta_filtro=tmp_path / "filtro",
        cliente_djen=cliente,
        somente_capas_locais=True,
        agora=datetime(2026, 11, 10, 10, 0),
    )
    assert resumo.elegiveis == 2
    assert resumo.confirmados_acima_corte == 0
    assert resumo.confirmados_ate_corte == 0
    assert resumo.pendentes == 2
    assert resumo.exportados == 0
    assert resumo.cobertura_parcial is True

    wb = load_workbook(planilha)
    assert wb.sheetnames == ["Casos", "Publicações", "Pendentes", "Como ler"]
    assert wb["Casos"].max_row == 1
    assert wb["Publicações"].max_row == 1
    assert wb["Pendentes"].max_row == 3
    como_ler = {
        row[0]: row[1] for row in wb["Como ler"].iter_rows(values_only=True) if row and row[0]
    }
    assert como_ler["Cobertura"] == "Cobertura parcial"
    assert como_ler["Elegíveis antes do corte financeiro"] == 2
    assert como_ler["Pendentes de confirmação"] == 2
    assert como_ler["Exportados na aba Casos"] == 0
