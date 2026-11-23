"""HTTP de uma tentativa, com conexão ao IP validado e autenticação só no gateway."""
import http.client
import ipaddress
import json
import re
import socket
import ssl
import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from html.parser import HTMLParser
from urllib.parse import urlsplit

import certifi


class ErroGateway(RuntimeError):
    """Diagnóstico que pode ser exibido sem o corpo ou a URL da fonte."""


class PoliticaIndisponivel(ErroGateway):
    pass


MOTIVO_POLITICA = (
    "Hermes sem política prévia demonstrada para uma única web_search gratuita "
    "com argumentos exatos e leitura sem ferramentas"
)


def _resolver(host):
    return tuple(item[4][0] for item in socket.getaddrinfo(host, None, type=socket.SOCK_STREAM))


def _destino(url, resolver, local):
    if not isinstance(url, str) or re.search(r"[\s\\\x00-\x1f\x7f]", url) or "#" in url:
        raise ValueError("URL inválida")
    partes = urlsplit(url)
    host = partes.hostname
    if partes.scheme not in ("http", "https") or not host or "%" in host or partes.username is not None:
        raise ValueError("URL inválida")
    porta = partes.port if partes.port is not None else (443 if partes.scheme == "https" else 80)
    if not 1 <= porta <= 65535:
        raise ValueError("Porta inválida")
    try:
        ips = (ipaddress.ip_address(host),)
    except ValueError:
        if local and host != "localhost":
            raise ValueError("Gateway fora do loopback") from None
        ips = tuple(ipaddress.ip_address(ip) for ip in resolver(host))
    if local:
        permitido = porta != 18434 and "?" not in url and all(ip.is_loopback for ip in ips)
    else:
        permitido = all(ip.is_global and not ip.is_multicast and not ip.is_reserved
                        and not ip.is_loopback for ip in ips)
    if not ips or not permitido:
        raise ValueError("Destino não permitido")
    return partes, porta, ips[0]


def validar_gateway_url(url: str, resolver=_resolver) -> str:
    try:
        partes, _, _ = _destino(url, resolver, True)
        if partes.path.rstrip("/") == "/v1":
            return url.rstrip("/")
    except (ValueError, OSError, UnicodeError):
        pass
    raise ValueError("PESSOAS_HERMES_URL inválida")


class Ritmo:
    def __init__(self, intervalo=5, relogio=time.monotonic, dormir=time.sleep):
        if intervalo < 3:
            raise ValueError("Intervalo inferior a 3 segundos")
        self.intervalo = intervalo
        self._relogio = relogio
        self._dormir = dormir
        self._ultimo = None
        self._lock = threading.Lock()

    @contextmanager
    def requisicao(self):
        with self._lock:
            if self._ultimo is not None:
                restante = self.intervalo - (self._relogio() - self._ultimo)
                if restante > 0:
                    self._dormir(restante)
            try:
                yield
            finally:
                self._ultimo = self._relogio()


class _FalhaHTTP(Exception):
    pass


def _obter(destino, conectar, timeout, max_bytes, headers):
    partes, porta, ip = destino
    host = partes.hostname.encode("idna").decode("ascii")
    # HTTPConnection não recebe a URL nem credenciais de proxy. Fixar o socket
    # antes de request elimina uma segunda resolução entre validação e envio.
    conexao = http.client.HTTPConnection(host, porta, timeout=timeout)
    sock = conectar((str(ip), porta), timeout)
    try:
        if ipaddress.ip_address(sock.getpeername()[0]) != ip:
            raise _FalhaHTTP("destino efetivo inválido")
        if partes.scheme == "https":
            contexto = ssl.create_default_context(cafile=certifi.where())
            sock = contexto.wrap_socket(sock, server_hostname=host)
        conexao.sock = sock
        alvo = partes.path or "/"
        if partes.query:
            alvo += "?" + partes.query
        conexao.request("GET", alvo, headers=headers)
        resposta = conexao.getresponse()
        if 300 <= resposta.status < 400:
            raise _FalhaHTTP("redirecionamento")
        if not 200 <= resposta.status < 300:
            raise _FalhaHTTP(f"HTTP {resposta.status}")
        tamanho = resposta.getheader("Content-Length")
        if tamanho is not None and int(tamanho) > max_bytes:
            raise _FalhaHTTP("tamanho excedido")
        if resposta.getheader("Content-Encoding", "identity").lower() != "identity":
            raise _FalhaHTTP("codificação não suportada")
        corpo = resposta.read(max_bytes + 1)
        if len(corpo) > max_bytes:
            raise _FalhaHTTP("tamanho excedido")
        if tamanho is not None and len(corpo) != int(tamanho):
            raise _FalhaHTTP("conteúdo incompleto")
        return corpo, resposta.headers
    finally:
        conexao.close()
        sock.close()


class TransporteLocal:
    def __init__(self, config, *, resolver=_resolver, conectar=socket.create_connection, ritmo=None):
        self._config = config
        self._resolver = resolver
        self._conectar = conectar
        self._ritmo = ritmo or Ritmo(config.intervalo)

    def exigir_politica(self):
        # /v1/responses herda as ferramentas da plataforma. O servidor instalado
        # não oferece contrato por pedido vinculando argumentos, contagem e custo.
        raise PoliticaIndisponivel(MOTIVO_POLITICA)

    def enviar_restrito(self, url, payload, *, modo, argumentos):
        raise PoliticaIndisponivel(MOTIVO_POLITICA)

    def enviar(self, url, payload=None) -> dict:
        if payload is not None:
            raise PoliticaIndisponivel(MOTIVO_POLITICA)
        try:
            base = validar_gateway_url(self._config.hermes_url, self._resolver)
            if url != base + "/models" or not self._config.hermes_key:
                raise ErroGateway("Requisição autenticada inválida")
            destino = _destino(url, self._resolver, True)
            headers = {"Authorization": "Bearer " + self._config.hermes_key, "Accept": "application/json"}
            with self._ritmo.requisicao():
                corpo, _ = _obter(destino, self._conectar, self._config.hermes_timeout, 5_000_000, headers)
            resposta = json.loads(corpo)
            if isinstance(resposta, dict):
                return resposta
        except _FalhaHTTP as exc:
            raise ErroGateway(str(exc)) from None
        except (ValueError, OSError, http.client.HTTPException):
            raise ErroGateway("Gateway inacessível ou resposta inválida") from None
        raise ErroGateway("Resposta do gateway inválida")


@dataclass(frozen=True)
class Pagina:
    url: str
    texto: str
    estado: str
    motivo: str = ""
    data: str = ""


def rede_social(host):
    host = (host or "").lower().rstrip(".")
    for rede in ("instagram.com", "facebook.com", "linkedin.com"):
        if host == rede or host.endswith("." + rede):
            return rede
    return None


class _TextoHTML(HTMLParser):
    def __init__(self):
        super().__init__()
        self.partes = []
        self.titulos = []
        self.em_titulo = False
        self.ignorar = 0
        self.barreira = False

    def handle_starttag(self, tag, attrs):
        if tag in ("style", "script", "noscript", "svg", "head"):
            self.ignorar += 1
        atributos = dict(attrs)
        if tag == "title":
            self.em_titulo = True
        if tag == "meta" and atributos.get("property") == "og:title" and atributos.get("content"):
            self.titulos.append(atributos["content"])
        if tag == "input" and (atributos.get("type") or "").lower() == "password":
            self.barreira = True
        if any("captcha" in (atributos.get(k) or "").lower() for k in ("class", "id", "src")):
            self.barreira = True

    def handle_endtag(self, tag):
        if tag == "title":
            self.em_titulo = False
        if tag in ("style", "script", "noscript", "svg", "head") and self.ignorar:
            self.ignorar -= 1

    def handle_data(self, data):
        if self.em_titulo:
            self.titulos.append(data)
        if not self.ignorar:
            self.partes.append(data)


class TransportePublico:
    def __init__(self, *, resolver=_resolver, conectar=socket.create_connection, ritmo=None,
                 max_bytes=5_000_000, timeout=25, agora=lambda: datetime.now(UTC)):
        self._resolver = resolver
        self._conectar = conectar
        self._ritmo = ritmo or Ritmo()
        self._max_bytes = min(5_000_000, max_bytes)
        self._timeout = timeout
        self._agora = agora
        self._cache = {}

    def baixar(self, url) -> Pagina:
        if url in self._cache:
            return self._cache[url]
        data = self._agora().isoformat()
        try:
            destino = _destino(url, self._resolver, False)
            with self._ritmo.requisicao():
                corpo, headers = _obter(destino, self._conectar, self._timeout, self._max_bytes,
                                        {"Accept": "text/html,text/plain", "Accept-Encoding": "identity"})
            mime = headers.get_content_type()
            if mime not in ("text/html", "text/plain", "application/xhtml+xml"):
                raise _FalhaHTTP("tipo de conteúdo não suportado")
            texto = corpo.decode(headers.get_content_charset() or "utf-8", errors="replace")
            parser = _TextoHTML()
            parser.feed(texto)
            parser.close()
            texto = " ".join(" ".join(parser.partes).split())
            if parser.barreira or re.search(r"\b(log in to (see|continue)|entrar para (ver|continuar)|"
                                           r"verify you are human|confirme que você é humano)\b", texto, re.I):
                raise _FalhaHTTP("login ou captcha")
            if rede_social(destino[0].hostname):
                # A página de perfil pode embutir posts e conexões no corpo.
                # Somente títulos de perfil seguem para leitura ou cache.
                texto = " ".join(dict.fromkeys(parser.titulos)).strip()
            if not texto:
                raise _FalhaHTTP("página sem texto")
            pagina = Pagina(url, texto, "consultado", data=data)
        except _FalhaHTTP as exc:
            pagina = Pagina(url, "", "nao_consultado", str(exc), data)
        except (OSError, ValueError, LookupError, http.client.HTTPException):
            pagina = Pagina(url, "", "nao_consultado", "endereço inválido ou página inacessível", data)
        self._cache[url] = pagina
        return pagina
