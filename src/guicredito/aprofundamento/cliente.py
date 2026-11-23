"""Consultas sequenciais, sem login e sem resolver/burlar desafios."""
import http.cookiejar
import ssl
import time
import urllib.error
import urllib.request
from urllib.parse import urlsplit

from .cnj import BASE


class FalhaConsulta(Exception):
    def __init__(self, status, mensagem):
        self.status = status
        super().__init__(mensagem)


def destino_permitido(url):
    p = urlsplit(url)
    return p.scheme == "https" and p.netloc == "esaj.tjsp.jus.br" and p.path.startswith("/cpopg/")


class Redirecionamento(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if not destino_permitido(newurl):
            raise FalhaConsulta("redirecionamento_manual", "O site redirecionou para outro serviço; confira no navegador.")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


class Cliente:
    def __init__(self, intervalo=5):
        if intervalo < 3:
            raise ValueError("O intervalo deve ser de pelo menos 3 segundos.")
        self.intervalo = intervalo
        self.ultima = None
        try:
            import certifi
            contexto = ssl.create_default_context(cafile=certifi.where())
        except ImportError:
            contexto = ssl.create_default_context()
        self.opener = urllib.request.build_opener(
            urllib.request.HTTPSHandler(context=contexto),
            urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()),
            Redirecionamento(),
        )

    def get(self, url):
        if not destino_permitido(url):
            raise FalhaConsulta("destino_invalido", "URL fora da consulta pública do e-SAJ.")
        if self.ultima is not None:
            time.sleep(max(0, self.intervalo - (time.monotonic() - self.ultima)))
        self.ultima = time.monotonic()
        req = urllib.request.Request(url, headers={"User-Agent": "GUICredito/0.1 (consulta avulsa)", "Accept": "text/html"})
        try:
            with self.opener.open(req, timeout=25) as r:
                if r.headers.get_content_type() != "text/html":
                    raise FalhaConsulta("formato_inesperado", "Resposta não é HTML.")
                raw = r.read(5_000_001)
                if len(raw) > 5_000_000:
                    raise FalhaConsulta("pagina_grande", "Página excedeu o limite de 5 MB.")
                return raw.decode(r.headers.get_content_charset() or "utf-8", errors="replace")
        except urllib.error.HTTPError as e:
            status = "bloqueado" if e.code in (401, 403, 429) else "erro_http"
            raise FalhaConsulta(status, f"HTTP {e.code}; sem repetição automática.") from e
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            raise FalhaConsulta("erro_rede", "Não foi possível acessar o TJSP. Confira a conexão ou tente pelo navegador.") from e

    def iniciar(self):
        return self.get(BASE + "open.do")
