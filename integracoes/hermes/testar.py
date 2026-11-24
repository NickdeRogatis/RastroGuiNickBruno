"""Ensaio impessoal da busca e da leitura pelo gateway Hermes do Studio."""
import argparse
from pathlib import Path

from guicredito.pessoas.config import carregar_config
from guicredito.pessoas.hermes import criar_servicos_web
from guicredito.pessoas.http import ErroGateway


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-hermes", type=Path, required=True, help="Arquivo local com API_SERVER_KEY.")
    args = parser.parse_args()
    # As variáveis da aplicação e as do gateway têm nomes distintos.
    chave = ""
    for linha in args.env_hermes.read_text(encoding="utf-8").splitlines():
        nome, separador, valor = linha.partition("=")
        if separador and nome.strip() == "API_SERVER_KEY":
            chave = valor.strip().strip("\"'")
    config = carregar_config(env_file=Path("/dev/null"), ambiente={
        "PESSOAS_BUSCA": "hermes", "PESSOAS_HERMES_KEY": chave,
        "PESSOAS_HERMES_MODELO": "hermes-agent", "PESSOAS_HERMES_URL": "http://127.0.0.1:8642/v1",
    })
    if config.diagnosticos:
        raise SystemExit("\n".join(config.diagnosticos))
    agente, paginas = criar_servicos_web(config)
    falhas = agente.verificar()
    if falhas:
        raise SystemExit("\n".join(falhas))
    print("Gateway autenticado. Modelo hermes-agent disponível.", flush=True)
    busca = agente.buscar('"Example Domain" IANA example domains documentation')
    print(f"web_search | backend {busca.backend} | {len(busca.itens)} resultados")
    print(f"Resposta {busca.id_resposta} | chamada {busca.id_chamada}")
    for item in busca.itens:
        print(item.url)
    fonte = paginas.baixar("https://example.org/")
    if fonte.estado != "consultado":
        raise SystemExit(f"Busca concluída. Leitura pendente: {fonte.motivo}")
    achados = agente.propor(fonte.texto, {"nome": "Example Domain", "papel": "credor", "url": fonte.url})
    print(f"Leitura de {fonte.url} concluída sem ferramentas. Propostas: {len(achados)}.")


if __name__ == "__main__":
    try:
        main()
    except (OSError, ErroGateway):
        raise SystemExit("Falha ao acessar a configuração ou concluir o turno pelo gateway.") from None
