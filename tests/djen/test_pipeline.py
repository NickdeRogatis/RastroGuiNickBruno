import hashlib
from datetime import date, datetime

import pytest
from openpyxl import load_workbook

from guicredito.djen.fonte import URL_CADERNO
from guicredito.djen.pipeline import parse_args, rodar
from tests.djen.conftest import ClienteFalso

PROC_A = "10000011820228260001"
PROC_B = "10000021820228260002"
PROC_C = "10000031820228260003"
PROC_D = "10000041820228260004"
PROC_E = "10000051820228260005"
PROC_F = "10000061820228260006"
CNJ_A = "1000001-18.2022.8.26.0001"
CNJ_E = "1000005-18.2022.8.26.0005"


def _cliente(tmp_path, fazer_zip, dias: dict[date, list[dict]]) -> ClienteFalso:
    metadados: dict[str, dict] = {}
    arquivos: dict[str, bytes] = {}
    brutos = tmp_path / "brutos"
    brutos.mkdir()
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


def _rodar(tmp_path, cliente, inicio, fim, **kw):
    return rodar(
        inicio,
        fim,
        pasta_dados=tmp_path / "dados",
        pasta_saida=tmp_path / "saida",
        cliente=cliente,
        agora=datetime(2026, 11, 9, 12, 0),
        **kw,
    )


def test_rodar_ponta_a_ponta(tmp_path, item, fazer_zip):
    dia_06 = [
        item(
            id=1,
            numero_processo=PROC_A,
            texto="<p>A pesquisa via SISBAJUD restou infrutífera.</p>",
            destinatarios=[
                {"nome": "EMPRESA EXEMPLO LTDA", "polo": "A"},
                {"nome": "JOÃO EXEMPLO", "polo": "P"},
            ],
        ),
        item(
            id=2,
            numero_processo=PROC_B,
            destinatarios=[{"nome": "LOJA EXEMPLO LTDA", "polo": "P"}],
        ),
        item(
            id=3,
            numero_processo=PROC_C,
            nomeClasse="BUSCA E APREENSãO EM ALIENAçãO FIDUCIáRIA",
        ),
        item(
            id=4,
            numero_processo=PROC_D,
            nomeClasse="EXECUçãO FISCAL",
        ),
        item(
            id=5,
            numero_processo=PROC_E,
            nomeClasse="CUMPRIMENTO DE SENTENçA",
            texto="<p>Texto.</p>",
            destinatarios=[{"nome": "EMPRESA EXEMPLO LTDA", "polo": "A"}],
        ),
        item(
            id=7,
            numero_processo=PROC_F,
            destinatarios=[
                {"nome": "BANCO EXEMPLO S.A.", "polo": "A"},
                {"nome": "ANA FICTÍCIA", "polo": "P"},
            ],
        ),
    ]
    dia_09 = [
        item(
            id=6,
            data_disponibilizacao="2026-11-09",
            numero_processo=PROC_A,
            texto="<p>Intime-se.</p>",
            destinatarios=[
                {"nome": "EMPRESA EXEMPLO LTDA", "polo": "A"},
                {"nome": "JOÃO EXEMPLO", "polo": "P"},
            ],
        )
    ]
    cliente = _cliente(
        tmp_path,
        fazer_zip,
        {date(2026, 11, 6): dia_06, date(2026, 11, 9): dia_09},
    )
    caminho, resumo = _rodar(tmp_path, cliente, date(2026, 11, 6), date(2026, 11, 9))
    assert caminho.is_file()
    assert resumo.publicacoes_lidas == 7
    assert resumo.publicacoes_cobranca == 5
    assert resumo.processos == 4
    assert resumo.processos_so_empresa == 1
    assert resumo.processos_banco == 1
    assert resumo.processos_recentes == 0
    assert resumo.casos_na_planilha == 2

    wb = load_workbook(caminho)
    casos = wb["Casos"]
    cabecalho = [c.value for c in casos[1]]
    col_proc = cabecalho.index("Processo")
    col_pubs = cabecalho.index("Publicações no período")
    linhas = {
        row[col_proc]: (indice, row[col_pubs])
        for indice, row in enumerate(
            list(casos.iter_rows(min_row=2, values_only=True)), start=2
        )
    }
    assert linhas[CNJ_A][1] == 2
    assert linhas[CNJ_A][0] < linhas[CNJ_E][0]
    assert wb["Publicações"].max_row == 4


def test_rodar_pula_dia_sem_caderno(tmp_path, item, fazer_zip):
    cliente = _cliente(tmp_path, fazer_zip, {date(2026, 11, 6): [item(id=1)]})
    caminho, resumo = _rodar(tmp_path, cliente, date(2026, 11, 5), date(2026, 11, 6))
    assert resumo.dias_sem_caderno == [date(2026, 11, 5)]
    assert caminho.is_file()


def test_rodar_respeita_limite(tmp_path, item, fazer_zip):
    itens = [
        item(
            id=i,
            numero_processo=numero,
            destinatarios=[
                {"nome": "EMPRESA EXEMPLO LTDA", "polo": "A"},
                {"nome": nome, "polo": "P"},
            ],
        )
        for i, numero, nome in (
            (1, "10000061820228260006", "JOÃO EXEMPLO"),
            (2, "10000071820228260007", "ANA FICTÍCIA"),
            (3, "10000081820228260008", "CARLOS MODELO"),
        )
    ]
    cliente = _cliente(tmp_path, fazer_zip, {date(2026, 11, 6): itens})
    caminho, _resumo = _rodar(
        tmp_path, cliente, date(2026, 11, 6), date(2026, 11, 6), limite=1
    )
    assert load_workbook(caminho)["Casos"].max_row == 2


def test_parse_args():
    args = parse_args(["--inicio", "2026-11-03", "--fim", "2026-11-07"])
    assert args.inicio == date(2026, 11, 3)
    assert args.limite == 300
    assert args.tribunal == "TJSP"
    assert args.historico == 0
    assert parse_args(["--historico", "20"]).historico == 20
    with pytest.raises(SystemExit):
        parse_args(["--inicio", "2026-11-03"])


def _linhas_casos(caminho) -> dict[str, dict[str, object]]:
    aba = load_workbook(caminho)["Casos"]
    cabecalho = [c.value for c in aba[1]]
    return {
        row[cabecalho.index("Processo")]: dict(zip(cabecalho, row, strict=True))
        for row in aba.iter_rows(min_row=2, values_only=True)
    }


def test_caso_do_ano_corrente_fica_fora(tmp_path, item, fazer_zip):
    novo = item(
        id=1,
        numero_processo="10000091820268260009",
        destinatarios=[
            {"nome": "EMPRESA EXEMPLO LTDA", "polo": "A"},
            {"nome": "JOÃO EXEMPLO", "polo": "P"},
        ],
    )
    cliente = _cliente(tmp_path, fazer_zip, {date(2026, 11, 6): [novo]})
    caminho, resumo = _rodar(tmp_path, cliente, date(2026, 11, 6), date(2026, 11, 6))
    assert resumo.processos_recentes == 1
    assert resumo.casos_na_planilha == 0
    assert _linhas_casos(caminho) == {}


def test_historico_acha_acordo(tmp_path, item, fazer_zip):
    devedor = {"nome": "JOSÉ CARLOS DA SILVA", "polo": "P"}
    acordo = item(
        id=1,
        data_disponibilizacao="2026-11-06",
        numero_processo=PROC_A,
        texto="<p>Homologo o acordo celebrado entre as partes.</p>",
        destinatarios=[{"nome": "EMPRESA EXEMPLO LTDA", "polo": "A"}, devedor],
    )
    outro = item(
        id=2,
        data_disponibilizacao="2026-11-09",
        numero_processo=PROC_B,
        texto="<p>Intime-se.</p>",
        destinatarios=[{"nome": "LOJA EXEMPLO LTDA", "polo": "A"}, devedor],
    )
    cliente = _cliente(
        tmp_path,
        fazer_zip,
        {date(2026, 11, 6): [acordo], date(2026, 11, 9): [outro]},
    )
    caminho, resumo = _rodar(
        tmp_path, cliente, date(2026, 11, 9), date(2026, 11, 9), historico=1
    )
    assert resumo.dias_historico == 1
    assert resumo.publicacoes_lidas == 1
    linhas = _linhas_casos(caminho)
    assert "1000001-18.2022.8.26.0001" not in linhas
    linha = linhas["1000002-18.2022.8.26.0002"]
    assert "acordo em outro processo" in linha["Sinais de patrimônio"]


def test_historico_sem_caderno_segue(tmp_path, item, fazer_zip):
    cliente = _cliente(tmp_path, fazer_zip, {date(2026, 11, 9): [item(id=1)]})
    caminho, resumo = _rodar(
        tmp_path, cliente, date(2026, 11, 9), date(2026, 11, 9), historico=1
    )
    assert caminho.is_file()
    assert resumo.dias_historico == 0
    assert resumo.dias_sem_caderno == []


def test_processo_com_acordo_homologado_fica_fora(tmp_path, item, fazer_zip):
    devedor = {"nome": "JOSÉ CARLOS DA SILVA", "polo": "P"}
    credor = {"nome": "EMPRESA EXEMPLO LTDA", "polo": "A"}
    acordo = item(
        id=1,
        numero_processo=PROC_A,
        texto="<p>Homologo o acordo. Fica levantada a penhora sobre o imóvel.</p>",
        destinatarios=[credor, devedor],
    )
    descumprido = item(
        id=2,
        numero_processo=PROC_B,
        texto="<p>Diante da notícia de descumprimento do acordo homologado, defiro a penhora.</p>",
        destinatarios=[credor, {"nome": "MARIA EXEMPLO FICTÍCIA", "polo": "P"}],
    )
    cliente = _cliente(tmp_path, fazer_zip, {date(2026, 11, 6): [acordo, descumprido]})
    caminho, resumo = _rodar(tmp_path, cliente, date(2026, 11, 6), date(2026, 11, 6))
    assert resumo.processos_acordo == 1
    linhas = _linhas_casos(caminho)
    assert "1000001-18.2022.8.26.0001" not in linhas
    assert "acordo descumprido" in linhas["1000002-18.2022.8.26.0002"]["Sinais de desgaste"]
    como_ler = {row[0]: row[1] for row in load_workbook(caminho)["Como ler"].iter_rows(values_only=True)}
    assert como_ler["Fora por acordo homologado no próprio processo"] == 1
