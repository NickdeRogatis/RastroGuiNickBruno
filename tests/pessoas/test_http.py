import io
import socket

import pytest

from guicredito.pessoas.config import carregar_config
from guicredito.pessoas.http import (
    ErroGateway, Ritmo, TransporteLocal, TransportePublico, validar_gateway_url,
)


def resolvedor(*ips):
    return lambda host: ips


class Conexao:
    """Socket HTTP em memória. Nenhum byte sai do processo."""
    def __init__(self, peer, resposta):
        self.peer = peer
        self.resposta = resposta
        self.enviados = bytearray()

    def sendall(self, data):
        self.enviados.extend(data)

    def getpeername(self):
        return self.peer, 8642

    def makefile(self, *args):
        return io.BytesIO(self.resposta)

    def settimeout(self, timeout):
        pass

    def close(self):
        pass


def http(corpo=b"", status=200, headers=b""):
    return (f"HTTP/1.1 {status} Test\r\nContent-Length: {len(corpo)}\r\n".encode()
            + headers + b"\r\n" + corpo)


@pytest.mark.parametrize("url,ips", [
    ("http://localhost:8642/v1", ["8.8.8.8", "::1"]),
    ("http://192.168.0.1:8642/v1", []), ("http://modelo.example/v1", ["127.0.0.1"]),
    ("http://127.0.0.1:18434/v1", []), ("http://user:senha@127.0.0.1/v1", []),
    ("http://127.0.0.1/v1?segredo", []), ("http://127.0.0.1/v1#ancora", []),
    ("http://127.0.0.1/v2", []), ("http://127.0.0.1/v1? ", []),
])
def test_gateway_recusa_destinos(url, ips):
    with pytest.raises(ValueError):
        validar_gateway_url(url, resolvedor(*ips))


@pytest.mark.parametrize("host", ["[::1]", "127.0.0.1", "localhost"])
def test_gateway_valido_usa_ip_verificado_e_sem_proxy(tmp_path, monkeypatch, host):
    monkeypatch.setenv("HTTP_PROXY", "http://proxy.example.test")
    ip = "::1" if host == "[::1]" else "127.0.0.1"
    conn = Conexao(ip, http(b'{"data":[]}'))
    chamadas = []
    def conectar(destino, timeout):
        chamadas.append(destino)
        return conn
    base = f"http://{host}:8642/v1"
    cfg = carregar_config(tmp_path / ".env", {"PESSOAS_HERMES_KEY": "sentinela", "PESSOAS_HERMES_URL": base})
    tx = TransporteLocal(cfg, resolver=resolvedor(ip), conectar=conectar)
    assert tx.enviar(base + "/models", None) == {"data": []}
    assert chamadas == [(ip, 8642)]
    assert b"Authorization: Bearer sentinela" in conn.enviados
    assert b"GET /v1/models " in conn.enviados


@pytest.mark.parametrize("url,peer", [
    ("http://127.0.0.1:8642/v1/models", "8.8.8.8"),
    ("http://127.0.0.1:8000/v1/models", "127.0.0.1"),
    ("http://127.0.0.1:8642/v1/other", "127.0.0.1"),
])
def test_gateway_recusa_troca_antes_do_bearer(tmp_path, url, peer):
    cfg = carregar_config(tmp_path / ".env", {"PESSOAS_HERMES_KEY": "sentinela"})
    conn = Conexao(peer, http())
    tx = TransporteLocal(cfg, conectar=lambda *_: conn)
    with pytest.raises(ErroGateway) as err:
        tx.enviar(url, None)
    assert conn.enviados == b"" and "sentinela" not in str(err.value)


@pytest.mark.parametrize("resposta,motivo", [
    (http(status=302, headers=b"Location: http://example.test/next\r\n"), "redirecionamento"),
    (http(status=429), "HTTP 429"), (http(status=403), "HTTP 403"),
    (http(b'<form><input type="password"></form>'), "login ou captcha"),
    (http(b"x" * 20), "tamanho excedido"),
])
def test_pagina_uma_tentativa_sem_cookie_ou_bearer(resposta, motivo):
    conn = Conexao("8.8.8.8", resposta)
    def conectar(*args):
        assert not conn.enviados
        return conn
    tx = TransportePublico(resolver=resolvedor("8.8.8.8"), conectar=conectar,
                           max_bytes=10 if motivo == "tamanho excedido" else 1000)
    url = "http://example.test/perfil"
    pagina = tx.baixar(url)
    assert pagina.estado == "nao_consultado" and pagina.motivo == motivo and not pagina.texto
    assert b"Cookie" not in conn.enviados and b"Authorization" not in conn.enviados
    assert tx.baixar(url) is pagina


@pytest.mark.parametrize("ips", [("8.8.8.8", "127.0.0.1"), ("192.168.1.1",), ("224.0.0.1",)])
def test_pagina_recusa_enderecos_internos(ips):
    tx = TransportePublico(resolver=resolvedor(*ips), conectar=lambda *_: pytest.fail("conexão"))
    assert tx.baixar("http://example.test").estado == "nao_consultado"


def test_pacing_entre_paginas_e_timeout_sem_retry():
    pausas = []
    ritmo = Ritmo(5, relogio=lambda: 0, dormir=pausas.append)
    tentativas = []
    def conectar(destino, timeout):
        tentativas.append(destino)
        if len(tentativas) == 2:
            raise socket.timeout()
        return Conexao(destino[0], http(b"<p>Nome</p><script>segredo</script>"))
    tx = TransportePublico(ritmo=ritmo, resolver=resolvedor("8.8.8.8"), conectar=conectar)
    assert tx.baixar("http://example.test/1").texto == "Nome"
    assert tx.baixar("http://example.test/2").estado == "nao_consultado"
    assert pausas == [5] and len(tentativas) == 2


def test_perfil_social_disponivel_minimiza_html_antes_da_leitura():
    corpo = (b'<head><meta property="og:title" content="JOAO EXEMPLO - LinkedIn"></head>'
             b'<main>Post sobre familia e fotos privadas</main>')
    tx = TransportePublico(resolver=resolvedor("8.8.8.8"),
                           conectar=lambda *_: Conexao("8.8.8.8", http(corpo)))
    pagina = tx.baixar("http://www.linkedin.com/in/joaoexemplo")
    assert pagina.texto == "JOAO EXEMPLO - LinkedIn"
