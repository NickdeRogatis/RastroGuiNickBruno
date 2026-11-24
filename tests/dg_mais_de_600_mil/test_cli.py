import hashlib
import json
import subprocess
import sys
from datetime import date
from pathlib import Path

import pytest

from guicredito.aprofundamento.cnj import formatar
from guicredito.dg_mais_de_600_mil.cli import parse_args_filtro
from guicredito.djen.pipeline import main as djen_main
from tests.djen.conftest import _fazer_zip, _item


def _cnj(i: int, ano: int = 2020) -> str:
    base = f"{i:07d}{ano}8260001"
    dd = 98 - int(base + "00") % 97
    return f"{i:07d}{dd:02d}{ano}8260001"


def test_help_djen_exibe_opcao_e_encaminha_help_do_filtro():
    res_normal = subprocess.run(
        [sys.executable, "-m", "guicredito.djen", "--help"],
        capture_output=True,
        text=True,
        check=True,
    )
    assert "--mais-de-600-mil" in res_normal.stdout

    res_filtro = subprocess.run(
        [sys.executable, "-m", "guicredito.djen", "--mais-de-600-mil", "--help"],
        capture_output=True,
        text=True,
        check=True,
    )
    assert "--somente-capas-locais" in res_filtro.stdout
    assert "--max-consultas" in res_filtro.stdout
    assert "--limite" in res_filtro.stdout


def test_parse_args_filtro_validacoes():
    args = parse_args_filtro(["--mais-de-600-mil", "--inicio", "2026-11-12", "--fim", "2026-11-23"])
    assert args.inicio == date(2026, 11, 12)
    assert args.fim == date(2026, 11, 23)
    assert args.limite is None
    assert args.max_consultas == 10
    assert args.somente_capas_locais is False

    with pytest.raises(SystemExit):
        parse_args_filtro(["--mais-de-600-mil", "--inicio", "2026-11-12"])
    with pytest.raises(SystemExit):
        parse_args_filtro(["--mais-de-600-mil", "--intervalo", "2"])
    with pytest.raises(SystemExit):
        parse_args_filtro(["--mais-de-600-mil", "--limite", "-1"])


def test_cli_entrada_djen_encaminha_modo_filtrado_com_capas_locais(tmp_path, capsys):
    dados = tmp_path / "dados" / "cadernos"
    dados.mkdir(parents=True)
    aprov = tmp_path / "saida" / "aprofundamento"
    filtro = tmp_path / "saida" / "DG__mais_de_600_mil"

    n1 = _cnj(1)
    n2 = _cnj(2)
    itens = [
        _item(
            id=1,
            data_disponibilizacao="2026-11-06",
            numero_processo=n1,
            destinatarios=[
                {"nome": "EMPRESA EXEMPLO LTDA", "polo": "A"},
                {"nome": "JOÃO EXEMPLO", "polo": "P"},
            ],
        ),
        _item(
            id=2,
            data_disponibilizacao="2026-11-06",
            numero_processo=n2,
            destinatarios=[
                {"nome": "EMPRESA EXEMPLO LTDA", "polo": "A"},
                {"nome": "MARIA FICTÍCIA", "polo": "P"},
            ],
        ),
    ]
    _fazer_zip(dados, "TJSP-D-2026-11-06_v1", [itens])

    pasta_n1 = aprov / "piloto" / n1
    pasta_n1.mkdir(parents=True)
    html = (
        f'<html><span id="numeroProcesso">{formatar(n1)}</span>'
        '<div id="valorAcaoProcesso">R$ 850.000,00</div></html>'
    )
    raw = html.encode("utf-8")
    (pasta_n1 / "consulta.html.txt").write_bytes(raw)
    (pasta_n1 / "resultado.json").write_text(
        json.dumps(
            {
                "numero_processo": n1,
                "status": "coletado",
                "consultado_em": "2026-11-24T10:00:00+00:00",
                "fonte": "TJSP e-SAJ — consulta pública de 1º grau",
                "url_pagina": "https://esaj.tjsp.jus.br/cpopg/show.do?x=1",
                "evidencias": [
                    {"arquivo": "consulta.html.txt", "sha256": hashlib.sha256(raw).hexdigest()}
                ],
            }
        ),
        encoding="utf-8",
    )

    rc = djen_main(
        [
            "--mais-de-600-mil",
            "--inicio",
            "2026-11-06",
            "--fim",
            "2026-11-06",
            "--somente-capas-locais",
            "--pasta-dados",
            str(dados),
            "--pasta-aprofundamento",
            str(aprov),
            "--pasta-filtro",
            str(filtro),
        ]
    )
    assert rc == 0
    saida = capsys.readouterr().out
    assert "Elegíveis (antes do corte de 300): 2" in saida
    assert "Confirmados acima de R$ 600.000,00 (antes do limite): 1" in saida
    assert "Pendentes: 1" in saida
    assert "cobertura parcial" in saida
    assert (filtro / "casos_djen_2026-11-06_a_2026-11-06.xlsx").is_file()
