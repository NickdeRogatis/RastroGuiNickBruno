"""Configuração local. O arquivo privado do gateway nunca é usado como origem."""
import os
from collections.abc import Mapping
from pathlib import Path


class Config:
    __slots__ = (
        "busca", "hermes_url", "hermes_modelo", "hermes_key", "hermes_timeout",
        "hermes_contexto", "intervalo", "indice_cnpj", "diagnosticos",
    )
    max_bytes = 5_000_000
    web_timeout = 25
    provedor = None  # Depende do contrato de um fornecedor licenciado.

    def __reduce_ex__(self, protocol):
        raise TypeError("Configuração privada não serializável")


def carregar_config(env_file: Path | None = None, ambiente: Mapping[str, str] | None = None) -> Config:
    valores = {}
    diagnosticos = []
    arquivo = Path(".env") if env_file is None else Path(env_file)
    try:
        linhas = arquivo.read_text(encoding="utf-8").splitlines()
    except FileNotFoundError:
        linhas = []
    except (OSError, UnicodeError):
        linhas = []
        diagnosticos.append("Arquivo de configuração ilegível")
    for linha in linhas:
        if not linha.strip() or linha.lstrip().startswith("#"):
            continue
        chave, separador, valor = linha.partition("=")
        if not separador or not chave.strip().isidentifier():
            diagnosticos.append("Par KEY=VALUE inválido no arquivo de configuração")
            continue
        valor = valor.strip()
        if len(valor) >= 2 and valor[0] in ("'", '"') and valor[0] == valor[-1]:
            valor = valor[1:-1]
        valores[chave.strip()] = valor
    valores.update(os.environ if ambiente is None else ambiente)

    def inteiro(chave, padrao, minimo):
        try:
            valor = int(valores.get(chave, padrao))
            if valor >= minimo:
                return valor
        except (ValueError, TypeError):
            pass
        diagnosticos.append(f"{chave} inválido")
        return padrao

    cfg = Config()
    cfg.busca = valores.get("PESSOAS_BUSCA", "").strip() or None
    cfg.hermes_modelo = valores.get("PESSOAS_HERMES_MODELO", "").strip()
    cfg.hermes_url = valores.get("PESSOAS_HERMES_URL", "http://127.0.0.1:8642/v1").strip()
    cfg.hermes_key = valores.get("PESSOAS_HERMES_KEY", "").strip()
    cfg.hermes_timeout = inteiro("PESSOAS_HERMES_TIMEOUT", 180, 1)
    cfg.hermes_contexto = inteiro("PESSOAS_HERMES_CONTEXTO", 262144, 1)
    cfg.intervalo = inteiro("PESSOAS_INTERVALO", 5, 3)
    indice = valores.get("PESSOAS_INDICE_CNPJ", "").strip()
    cfg.indice_cnpj = Path(indice).expanduser() if indice else None
    if cfg.busca not in (None, "hermes"):
        diagnosticos.append("PESSOAS_BUSCA inválido")
    if cfg.busca == "hermes":
        if not cfg.hermes_key:
            diagnosticos.append("PESSOAS_HERMES_KEY ausente")
        if not cfg.hermes_modelo:
            diagnosticos.append("PESSOAS_HERMES_MODELO ausente")
    cfg.diagnosticos = tuple(diagnosticos)
    return cfg
