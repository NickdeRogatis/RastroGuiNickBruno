import re
from urllib.parse import urlencode

BASE = "https://esaj.tjsp.jus.br/cpopg/"


def normalizar(valor: str) -> str:
    valor = valor.strip()
    if not re.fullmatch(r"(?:\d{20}|\d{7}-\d{2}\.\d{4}\.8\.26\.\d{4})", valor):
        raise ValueError("Informe um número CNJ completo de 20 dígitos.")
    n = re.sub(r"\D", "", valor)
    if n[13:16] != "826":
        raise ValueError("Esta etapa atende processos do TJSP (8.26).")
    if int(n[:7] + n[9:] + n[7:9]) % 97 != 1:
        raise ValueError("Dígito verificador do número CNJ inválido.")
    return n


def formatar(n: str) -> str:
    n = normalizar(n)
    return f"{n[:7]}-{n[7:9]}.{n[9:13]}.{n[13]}.{n[14:16]}.{n[16:]}"


def url_consulta(n: str) -> str:
    n = formatar(n)
    return BASE + "search.do?" + urlencode({
        "cbPesquisa": "NUMPROC",
        "dadosConsulta.tipoNuProcesso": "UNIFICADO",
        "numeroDigitoAnoUnificado": n[:15],
        "foroNumeroUnificado": n[-4:],
        "dadosConsulta.valorConsultaNuUnificado": n,
        "dadosConsulta.valorConsulta": n,
    })
