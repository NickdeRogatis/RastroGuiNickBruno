"""Comandos de guicredito.pessoas. Veja READING_PESSOAS.md."""
import argparse
import sqlite3
import sys
from pathlib import Path
from zipfile import BadZipFile

from .config import carregar_config
from .hermes import ClienteHermes
from .http import ErroGateway, MOTIVO_POLITICA, PoliticaIndisponivel, validar_gateway_url


def _parser():
    parser = argparse.ArgumentParser(description="Pesquisa dos casos selecionados pelo GUICredito.")
    subs = parser.add_subparsers(dest="comando", required=True)
    subs.add_parser("verificar", help="Conferir configuração e ID anunciado pelo gateway.")
    pesquisa = subs.add_parser("pesquisar", help="Executar a etapa gratuita.")
    pesquisa.add_argument("--alvos", choices=("todos", "credor", "advogados-do-credor", "polo-credor"), default="todos")
    pesquisa.add_argument("--retomar-leituras", action="store_true", help="Ler as URLs salvas sem repetir a busca.")
    for campo in ("selecao", "aprofundamento", "planilha", "saida"):
        pesquisa.add_argument("--" + campo, type=Path, required=True)
    subs.add_parser("contatos", help="Consultar apenas os pedidos autorizados.").add_argument("--lote", type=Path, required=True)
    conciliar = subs.add_parser("conciliar", help="Registrar a conferência de um pedido incerto com o fornecedor.")
    conciliar.add_argument("--lote", type=Path, required=True)
    conciliar.add_argument("--requisicao", required=True, help="ID da requisição no JSON privado do caso.")
    conciliar.add_argument("--resultado", choices=("nao_executado", "executado", "encerrar"), required=True)
    conciliar.add_argument("--arquivo", type=Path, help="Resposta recuperada do fornecedor para um pedido executado.")
    desc = subs.add_parser("descartar", help="Revisar os casos marcados para exclusão.")
    desc.add_argument("--lote", type=Path, required=True)
    desc.add_argument("--confirmar", metavar="CODIGO")
    oab = subs.add_parser("importar-oab", help="Incorporar uma conferência profissional feita manualmente.")
    oab.add_argument("--lote", type=Path, required=True)
    oab.add_argument("--arquivo", type=Path, required=True)
    cnpj = subs.add_parser("preparar-cnpj", help="Prever espaço ou preparar índice a partir de arquivos locais.")
    modo = cnpj.add_mutually_exclusive_group(required=True)
    modo.add_argument("--snapshot", type=Path)
    modo.add_argument("--prever-espaco", type=Path)
    cnpj.add_argument("--indice", type=Path, required=True)
    cnpj.add_argument("--layout", type=Path)
    cnpj.add_argument("--competencia")
    return parser


def _comando(a, cfg, servicos):
    from . import fluxo
    if a.comando == "verificar":
        print("Busca:", "Hermes configurado" if cfg.busca == "hermes" else "não configurada")
        print("Provedor de contatos:", "configurado" if servicos.get("provedor") is not None else "não configurado")
        cliente = servicos.get("hermes") or ClienteHermes(cfg)
        falhas = list(cfg.diagnosticos) + cliente.verificar()
        for detalhe in dict.fromkeys(falhas):
            print(detalhe, file=sys.stderr)
        if not falhas:
            if cfg.hermes_modelo == "hermes-agent":
                print("Modelo hermes-agent listado pelo gateway.")
            else:
                print("Modelo configurado listado pelo gateway.")
        return 2 if falhas else 0
    if a.comando == "preparar-cnpj":
        from .cnpj import preparar_cnpj, prever_espaco
        if a.prever_espaco:
            v = prever_espaco(a.prever_espaco, a.indice)
            print(f"Espaço {v['estado']}. Necessário: {v['necessario']} bytes. Disponível: {v['disponivel']} bytes.")
            return 0 if v["estado"] == "suficiente" else 2
        if not a.layout or not a.competencia:
            print("Informe --layout e --competencia para preparar o índice.", file=sys.stderr)
            return 2
        preparar_cnpj(a.snapshot, a.layout, a.competencia, a.indice)
        print("Índice CNPJ preparado.")
        return 0
    if a.comando == "importar-oab":
        total = fluxo.importar_oab(a.lote, a.arquivo)
        print(f"Registros profissionais incorporados: {total}.")
        return 0
    if a.comando == "conciliar":
        fluxo.conciliar_contatos(a.lote, a.requisicao, a.resultado, a.arquivo)
        print("Conciliação de uma requisição registrada.")
        return 0
    if a.comando == "descartar":
        if a.confirmar:
            total = fluxo.confirmar_descarte(a.lote, a.confirmar)
            print(f"Casos excluídos: {total}.")
        else:
            previa = fluxo.prever_descarte(a.lote)
            print("Casos marcados:", ", ".join(previa["rotulos"]) or "nenhum")
            if previa["rotulos"]:
                print("Para aplicar esta seleção, repita o comando com --confirmar", previa["codigo"])
        return 0
    if a.comando == "contatos":
        resultado = fluxo.contatos(a.lote, servicos.get("provedor"))
        if resultado["estado"] == "nao_configurado":
            print("Provedor não configurado. Marcações preservadas.")
            return 2
        print(f"Casos no lote: {resultado['casos']}.")
        return 0

    from .entrada import ler_entrada
    entrada = ler_entrada(a.selecao, a.aprofundamento, a.planilha, escopo=a.alvos)
    dados = fluxo.pesquisar(entrada, cfg, servicos, a.saida, retomar_leituras=a.retomar_leituras)
    casos = dados["casos"]
    print(f"Casos: {len(casos)}. Candidatos: {sum(len(c['candidatos']) for c in casos)}.")
    if not cfg.busca:
        print("Busca web não configurada.")
    if not cfg.indice_cnpj and not servicos.get("cnpj"):
        print("Índice CNPJ não configurado.")
    print("Relatório do lote: relatorio.html")
    return 0


def main(argv=None, servicos=None):
    args = _parser().parse_args(argv)
    cfg = carregar_config()
    try:
        return _comando(args, cfg, servicos or {})
    except PoliticaIndisponivel:
        print(MOTIVO_POLITICA, file=sys.stderr)
    except ErroGateway:
        try:
            base = validar_gateway_url(cfg.hermes_url)
        except ValueError:
            base = "endereço inválido"
        print(f"Gateway indisponível ou resposta incompatível ({base}).", file=sys.stderr)
    except (ValueError, OSError, KeyError, TypeError, BadZipFile, sqlite3.Error) as erro:
        # Mensagens de planilhas, filesystem e respostas de terceiros podem conter dados pessoais.
        # Somente diagnósticos conhecidos cruzam a fronteira do terminal.
        conhecidos = {
            "A entrada mudou. Escolha outro lote.", "CPF inválido.", "CNPJ inválido.",
            "O lote está em uso.", "Feche a planilha antes de atualizar o lote.",
            "A planilha mudou durante a operação. Reabra o lote.",
            "A planilha mudou durante uma atualização interrompida. Preserve a edição antes de recuperar.",
            "A pasta do lote não pode ser um link.", "Lote inexistente.",
            "Prévia vencida ou incompatível. Confira novamente as marcações.",
            "Resultado pago incerto. Conciliar com o fornecedor antes de repetir.",
            "Requisição incerta não encontrada.", "A opção confirmada diverge do contato solicitado.",
            "Identidade ou fornecedor mudou. Revise o pedido anterior.",
            "Informe o arquivo da resposta apenas para a operação executada.",
            "Resposta do fornecedor inválida para a conciliação.", "Resultado de conciliação ou autorização incompatível.",
            "Pedido incerto. Conciliação manual necessária.", "Índice CNPJ indisponível.",
            "Pesquisa interrompida após possível envio. Confira o lote antes de nova consulta.",
            "Busca salva. Use --retomar-leituras para continuar sem repetir a busca.",
            "Falha na pesquisa Hermes. Resultado incerto. Lote parcial preservado.",
            "Linha desconhecida, repetida ou alterada na planilha.", "Marcação inválida.",
            "Espaço insuficiente ou indeterminado para o índice CNPJ.",
        }
        msg = str(erro)
        if msg in conhecidos:
            print(msg, file=sys.stderr)
        else:
            print("Operação interrompida. Confira os arquivos, as marcações e a configuração.", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
