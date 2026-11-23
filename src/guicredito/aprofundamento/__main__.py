import argparse
from datetime import datetime
from pathlib import Path

from .cliente import Cliente
from .fluxo import gravar_json, importar, ler_selecao, posicoes, reprocessar, rodar, selecionar


def main(argv=None):
    p = argparse.ArgumentParser(description="Aprofundar até 10 casos no TJSP, preservando o score do DJEN.")
    sub = p.add_subparsers(dest="acao", required=True)
    s = sub.add_parser("selecionar", help="Salvar posições escolhidas da aba Casos.")
    s.add_argument("--planilha", type=Path, required=True)
    s.add_argument("--posicoes", default="1-10", help="Posições na coluna #. Ex.: 1-10 ou 1,3,5.")
    s.add_argument("--destino", type=Path, default=Path("dados/aprofundamento/selecionados.json"))
    c = sub.add_parser("consultar", help="Consultar os casos selecionados, um por vez.")
    c.add_argument("--selecao", type=Path, default=Path("dados/aprofundamento/selecionados.json"))
    c.add_argument("--saida", type=Path, default=Path("saida/aprofundamento") / datetime.now().strftime("%Y%m%d_%H%M%S_%f"))
    c.add_argument("--intervalo", type=float, default=5)
    i = sub.add_parser("importar", help="Ler um HTML e-SAJ salvo manualmente.")
    i.add_argument("--selecao", type=Path, default=Path("dados/aprofundamento/selecionados.json"))
    i.add_argument("--processo", required=True)
    i.add_argument("--html", type=Path, required=True)
    i.add_argument("--saida", type=Path, required=True)
    r = sub.add_parser("reprocessar", help="Atualizar a extração das respostas salvas, sem consultar o site.")
    r.add_argument("--saida", type=Path, required=True)
    a = p.parse_args(argv)
    try:
        if a.acao == "selecionar":
            if a.destino.exists():
                raise ValueError("A seleção já existe. Use --destino com outro nome para preservar a anterior.")
            selecao = selecionar(a.planilha, posicoes(a.posicoes))
            gravar_json(a.destino, selecao)
            print(f"Selecionados {len(selecao['casos'])} casos. Arquivo: {a.destino}")
            return 0
        if a.acao == "reprocessar":
            resultados = reprocessar(a.saida)
        elif a.acao == "consultar":
            selecao = ler_selecao(a.selecao)
            resultados = rodar(selecao, Cliente(a.intervalo), a.saida)
        else:
            selecao = ler_selecao(a.selecao)
            resultados = [importar(selecao, a.processo, a.html, a.saida)]
        coletados = sum(r["status"] == "coletado" for r in resultados)
        parciais = sum(r["status"] == "coletado_parcial" for r in resultados)
        print(f"Coletados: {coletados}/{len(resultados)}; parciais: {parciais}. Relatório: {a.saida / 'relatorio.html'}")
        return 0 if coletados == len(resultados) else 2
    except (ValueError, KeyError, TypeError, OSError) as e:
        p.error(str(e))


if __name__ == "__main__":
    raise SystemExit(main())
