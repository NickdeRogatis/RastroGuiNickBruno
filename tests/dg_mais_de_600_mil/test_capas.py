import hashlib
import json
from pathlib import Path

from guicredito.aprofundamento.cliente import FalhaConsulta
from guicredito.aprofundamento.cnj import formatar
from guicredito.dg_mais_de_600_mil.capas import (
    consultar_capa_esaj,
    importar_capa_html,
    indexar_capas_locais,
    verificar_capa_salva,
)
from guicredito.dg_mais_de_600_mil.modelos import MotivoPendencia, StatusValor


def cnj(i: int = 1, ano: int = 2020) -> str:
    base = f"{i:07d}{ano}8260001"
    dd = 98 - int(base + "00") % 97
    return f"{i:07d}{dd:02d}{ano}8260001"


def html_capa(numero: str, valor: str | None = "R$ 750.000,00") -> str:
    bloco_valor = f'<div id="valorAcaoProcesso">{valor}</div>' if valor is not None else ""
    return (
        f'<html><span id="numeroProcesso">{formatar(numero)}</span>'
        f'<div id="classeProcesso">Execução de título extrajudicial</div>'
        f"{bloco_valor}</html>"
    )


def salvar_capa_local(
    raiz: Path,
    numero: str,
    html: str,
    *,
    numero_json: str | None = None,
    status: str = "coletado",
    consultado_em: str = "2026-11-24T12:00:00+00:00",
    hash_override: str | None = None,
) -> Path:
    pasta = raiz / numero
    pasta.mkdir(parents=True, exist_ok=True)
    conteudo = html.encode("utf-8")
    (pasta / "consulta.html.txt").write_bytes(conteudo)
    digest = hash_override or hashlib.sha256(conteudo).hexdigest()
    dados = {
        "numero_processo": numero_json or numero,
        "status": status,
        "consultado_em": consultado_em,
        "fonte": "TJSP e-SAJ — consulta pública de 1º grau",
        "url_consulta": f"https://esaj.tjsp.jus.br/cpopg/search.do?n={numero}",
        "url_pagina": f"https://esaj.tjsp.jus.br/cpopg/show.do?n={numero}",
        "evidencias": [{"arquivo": "consulta.html.txt", "sha256": digest}],
    }
    destino = pasta / "resultado.json"
    destino.write_text(json.dumps(dados, ensure_ascii=False), encoding="utf-8")
    return destino


class ClienteEsajFalso:
    def __init__(self, respostas: list[object]):
        self.respostas = list(respostas)
        self.urls: list[str] = []

    def iniciar(self) -> str:
        return "<html>Consulta pública</html>"

    def get(self, url: str) -> str:
        self.urls.append(url)
        prox = self.respostas.pop(0)
        if isinstance(prox, Exception):
            raise prox
        return str(prox)


def test_verificar_capa_salva_valida_e_evidencia_adulterada(tmp_path):
    n = cnj(1)
    arq = salvar_capa_local(tmp_path, n, html_capa(n, "R$ 600.000,01"))
    chave, ver = verificar_capa_salva(arq)
    assert chave == n
    assert ver is not None
    assert ver.status is StatusValor.CONFIRMADO_ACIMA
    assert ver.valor_centavos == 60_000_001
    assert ver.resolvido_localmente is True

    # Adultera o HTML salvo: hash não confere -> pendente, nunca confirma
    (tmp_path / n / "consulta.html.txt").write_text(html_capa(n, "R$ 9.000.000,00"), encoding="utf-8")
    _chave, ver_inv = verificar_capa_salva(arq)
    assert ver_inv is not None
    assert ver_inv.status is StatusValor.PENDENTE
    assert ver_inv.motivo == MotivoPendencia.EVIDENCIA_INVALIDA


def test_verificar_capa_com_cnj_divergente_no_html_e_no_json(tmp_path):
    n1 = cnj(1)
    n2 = cnj(2)
    # HTML mostra n2 dentro da pasta de n1
    arq_html_div = salvar_capa_local(tmp_path / "lote1", n1, html_capa(n2, "R$ 1.000.000,00"))
    chave, ver = verificar_capa_salva(arq_html_div)
    assert chave == n1
    assert ver is not None
    assert ver.status is StatusValor.PENDENTE
    assert ver.motivo == MotivoPendencia.CAPA_CNJ_DIVERGENTE

    # JSON mostra n2 dentro da pasta de n1
    arq_json_div = salvar_capa_local(
        tmp_path / "lote2", n1, html_capa(n1, "R$ 1.000.000,00"), numero_json=n2
    )
    chave2, ver2 = verificar_capa_salva(arq_json_div)
    assert chave2 == n1
    assert ver2 is not None
    assert ver2.status is StatusValor.PENDENTE
    assert ver2.motivo == MotivoPendencia.CAPA_CNJ_DIVERGENTE


def test_indexar_capas_locais_reaproveita_fora_do_piloto(tmp_path):
    aprov = tmp_path / "aprofundamento"
    capas = tmp_path / "capas"
    n_piloto = cnj(1)
    n_extra = cnj(2)
    salvar_capa_local(aprov / "2026-11-23_top10", n_piloto, html_capa(n_piloto, "R$ 100.000,00"))
    salvar_capa_local(aprov / "lote_avulso_extra", n_extra, html_capa(n_extra, "R$ 850.000,00"))

    indice = indexar_capas_locais([aprov], capas)
    assert indice[n_piloto].status is StatusValor.CONFIRMADO_ATE
    assert indice[n_extra].status is StatusValor.CONFIRMADO_ACIMA


def test_consultar_capa_esaj_sucesso_e_interrupcao(tmp_path):
    n1 = cnj(10)
    n2 = cnj(11)
    cliente = ClienteEsajFalso(
        [
            html_capa(n1, "R$ 650.000,00"),
            FalhaConsulta("bloqueado", "HTTP 403"),
        ]
    )
    ver1, parada1 = consultar_capa_esaj(n1, cliente, tmp_path / "capas")
    assert parada1 is None
    assert ver1.status is StatusValor.CONFIRMADO_ACIMA
    assert (tmp_path / "capas" / n1 / "consulta.html.txt").is_file()
    assert (tmp_path / "capas" / n1 / "resultado.json").is_file()

    ver2, parada2 = consultar_capa_esaj(n2, cliente, tmp_path / "capas")
    assert parada2 == "bloqueado"
    assert ver2.status is StatusValor.PENDENTE
    assert ver2.motivo == MotivoPendencia.CONSULTA_INTERROMPIDA


def test_importar_capa_html(tmp_path):
    n = cnj(25)
    html_orig = tmp_path / "pagina_salva.html"
    html_orig.write_text(html_capa(n, "R$ 900.000,00"), encoding="utf-8")
    ver = importar_capa_html(n, html_orig, tmp_path / "capas")
    assert ver.status is StatusValor.CONFIRMADO_ACIMA
    assert ver.valor_centavos == 90_000_000
    assert "HTML fornecido pelo usuário" in (ver.fonte or "")
