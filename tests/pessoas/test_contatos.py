import pytest

from guicredito.pessoas.contatos import ProvedorIncompativel, processar, validar_cpf, validar_cnpj


class Provedor:
    nome = "teste"
    descoberta_separada = True
    identificadores = {"nome", "cpf", "cnpj"}

    def __init__(self):
        self.chamadas = []
        self.multiplos = True
        self.requisicoes = []

    def identificar(self, identidade, *, requisicao):
        self.requisicoes.append(requisicao)
        self.chamadas.append(identidade)
        itens = [{"id": "x", "nome": "JOÃO EXEMPLO", "cidade": "Cidade A",
                  "telefone": "CONTATO_SENTINELA"}]
        return itens + [{"id": "y", "nome": "JOÃO EXEMPLO"}] if self.multiplos else itens

    def obter_contatos(self, id_confirmado, *, requisicao):
        self.requisicoes.append(requisicao)
        self.chamadas.append(id_confirmado)
        return [{"tipo": "telefone", "valor": "FICTÍCIO"}]


def caso():
    return {"processo": "caso", "alvos": [{"id": "a", "nome": "JOÃO EXEMPLO", "tipo": "PF"}],
            "candidatos": [{"id": "c", "alvo_id": "a", "nome": "JOÃO EXEMPLO", "cidade": "Cidade A"}],
            "provedor": [], "contatos": []}


def decisoes(confirmado="sim", autorizar="sim"):
    return {"candidatos": {"c": {"Confirmado": confirmado, "Autorizar consulta paga": autorizar, "CPF": ""}},
            "provedor": {}}


@pytest.mark.parametrize("valor", ["11111111111", "abc", "01234567899", "exemplo01234567890"])
def test_cpf_invalido(valor):
    with pytest.raises(ValueError):
        validar_cpf(valor)


def test_documentos():
    assert validar_cpf("012.345.678-90") == "01234567890"
    assert validar_cnpj("12.345.678/0001-95") == "12345678000195"


@pytest.mark.parametrize("conf,gasto", [("", "sim"), ("não", "sim"), ("sim", ""), ("sim", "não")])
def test_sem_duas_marcas(conf, gasto):
    fonte = Provedor()
    processar(caso(), decisoes(conf, gasto), fonte, lambda: None)
    assert fonte.chamadas == []


def test_desambiguar_com_nova_leitura():
    c, d, fonte = caso(), decisoes(), Provedor()
    estados = []
    gravar = lambda: estados.append(str(c.get("pedidos")))
    processar(c, d, fonte, gravar)
    assert len(fonte.chamadas) == 1 and c["contatos"] == []
    assert "CONTATO_SENTINELA" not in str(c)
    d["provedor"][c["provedor"][1]["id"]] = {"Confirmado": "sim"}
    d["candidatos"]["c"]["Autorizar consulta paga"] = ""
    processar(c, d, fonte, gravar)
    assert len(fonte.chamadas) == 1
    d["candidatos"]["c"]["Autorizar consulta paga"] = "sim"
    processar(c, d, fonte, gravar)
    processar(c, d, fonte, gravar)
    assert fonte.chamadas[1:] == ["y"]
    assert c["contatos"][0]["candidato_id"] == "c"
    assert any("incerto" in e for e in estados)


def test_pedido_incerto_sem_replay():
    c, fonte = caso(), Provedor()
    def falhou(_, *, requisicao):
        fonte.chamadas.append(True)
        raise TimeoutError("não mostrar dados")
    fonte.identificar = falhou
    with pytest.raises(ValueError, match="incerto"):
        processar(c, decisoes(), fonte, lambda: None)
    with pytest.raises(ValueError, match="incerto"):
        processar(c, decisoes(), fonte, lambda: None)
    assert fonte.chamadas == [True]


def test_sem_provedor_ou_identificador():
    c, fonte = caso(), Provedor()
    processar(c, decisoes(), None, lambda: None)
    fonte.identificadores = {"cpf"}
    processar(c, decisoes(), fonte, lambda: None)
    assert not fonte.chamadas
    assert c["pedidos"]["c"]["estado"] == "identificador_necessario"


def test_opcao_consultada_nao_pode_ser_trocada():
    c, d, fonte = caso(), decisoes(), Provedor()
    processar(c, d, fonte, lambda: None)
    op1, op2 = c["provedor"]
    d["provedor"][op1["id"]] = {"Confirmado": "sim"}
    processar(c, d, fonte, lambda: None)
    contato = c["contatos"][0]
    assert (contato["opcao_id"], contato["id_externo"]) == (op1["id"], "x")
    assert contato["id"] and contato["requisicao"] == fonte.requisicoes[1]
    assert fonte.requisicoes[0] != fonte.requisicoes[1]
    d["provedor"] = {op2["id"]: {"Confirmado": "sim"}}
    with pytest.raises(ValueError, match="opção"):
        processar(c, d, fonte, lambda: None)
    assert len(fonte.chamadas) == 2


@pytest.mark.parametrize("campo,valor", [
    ("nome", {"telefone": "SENTINELA"}), ("nome", "João telefone (11) 98765-1234"),
    ("id", "01234567890"), ("id", "11-98123-1234"), ("id", "cpf-01234567890"), ("cidade", "abc@example.com"),
    ("faixa_etaria", {"telefone": "SENTINELA"}),
])
def test_ambiguidade_nao_persiste_dados_de_contato(campo, valor):
    c, d, fonte = caso(), decisoes(), Provedor()
    fonte.identificar = lambda identidade, *, requisicao: [
        {"id": "x", "nome": "JOÃO EXEMPLO"},
        {"id": "y", "nome": "JOÃO EXEMPLO", campo: valor}]
    with pytest.raises(ValueError, match="incerto"):
        processar(c, d, fonte, lambda: None)
    assert not c["provedor"] and not c["contatos"]


def test_exige_descoberta_separada_antes_da_cobranca():
    c, d, fonte = caso(), decisoes(), Provedor()
    fonte.descoberta_separada = False
    with pytest.raises(ProvedorIncompativel):
        processar(c, d, fonte, lambda: None)
    assert not fonte.chamadas


def test_conciliacao_registrada_sem_replay_automatico():
    from guicredito.pessoas.contatos import conciliar_pedido
    c, d, fonte = caso(), decisoes(), Provedor()
    original = fonte.identificar

    def timeout(identidade, *, requisicao):
        fonte.requisicoes.append(requisicao)
        raise TimeoutError

    fonte.identificar = timeout
    with pytest.raises(ValueError, match="incerto"):
        processar(c, d, fonte, lambda: None)
    req = fonte.requisicoes[0]
    assert c["pedidos"]["c"]["requisicao"] == req
    with pytest.raises(ValueError):
        conciliar_pedido(c, d, "ausente", "nao_executado")
    conciliar_pedido(c, d, req, "nao_executado")
    assert len(fonte.requisicoes) == 1
    fonte.identificar = original
    processar(c, d, fonte, lambda: None)
    assert fonte.requisicoes == [req, req]
    assert c["pedidos"]["c"]["conciliacoes"][0]["resultado"] == "nao_executado"


def test_recupera_contato_ja_executado_com_opcao_e_requisicao():
    from guicredito.pessoas.contatos import conciliar_pedido
    c, d, fonte = caso(), decisoes(), Provedor()
    processar(c, d, fonte, lambda: None)
    opcao = c["provedor"][1]
    d["provedor"][opcao["id"]] = {"Confirmado": "sim"}

    def timeout(opcao, *, requisicao):
        raise TimeoutError

    fonte.obter_contatos = timeout
    with pytest.raises(ValueError, match="incerto"):
        processar(c, d, fonte, lambda: None)
    req = c["pedidos"]["c"]["requisicao"]
    resposta = [{"tipo": "telefone", "valor": "FICTÍCIO"}]
    d["candidatos"]["c"]["Autorizar consulta paga"] = ""
    with pytest.raises(ValueError):
        conciliar_pedido(c, d, req, "executado", resposta)
    d["candidatos"]["c"]["Autorizar consulta paga"] = "sim"
    conciliar_pedido(c, d, req, "executado", resposta)
    processar(c, d, fonte, lambda: None)
    assert len(c["contatos"]) == 1
    assert c["contatos"][0]["id_externo"] == "y"
    assert c["contatos"][0]["requisicao"] == req


def test_cli_concilia_lote_sem_novo_despacho(tmp_path, capsys):
    import json
    from types import SimpleNamespace

    from openpyxl import load_workbook

    from guicredito.pessoas import fluxo
    from guicredito.pessoas.__main__ import main
    from guicredito.pessoas.config import carregar_config

    c = caso()
    c.update(processo="00000013020258260100", posicao_original=1)
    c["alvos"][0].update(papel="devedor", processo=c["processo"])
    entrada = SimpleNamespace(casos=[c], hashes={"planilha": "fictício"})
    lote = tmp_path / "lote"
    fluxo.pesquisar(entrada, carregar_config(tmp_path / "config-ausente", {}), {}, lote)
    wb = load_workbook(lote / "pessoas.xlsx")
    for coluna in ("Confirmado", "Autorizar consulta paga"):
        idx = [c.value for c in wb["Candidatos"][1]].index(coluna)
        wb["Candidatos"][2][idx].value = "sim"
    wb.save(lote / "pessoas.xlsx")
    wb.close()
    fonte = Provedor()

    def timeout(identidade, *, requisicao):
        fonte.requisicoes.append(requisicao)
        raise TimeoutError

    fonte.identificar = timeout
    with pytest.raises(ValueError, match="incerto"):
        fluxo.contatos(lote, fonte)
    req = fonte.requisicoes[0]
    resposta = tmp_path / "reconciliado.json"
    resposta.write_text(json.dumps([{"id": "opcao", "nome": "JOÃO EXEMPLO"}]))
    args = ["conciliar", "--lote", str(lote), "--requisicao", req, "--resultado", "executado"]
    assert main(args) == 2
    assert main([*args, "--arquivo", str(resposta)]) == 0
    assert main([*args, "--arquivo", str(resposta)]) == 2
    saida = capsys.readouterr()
    assert "JOÃO EXEMPLO" not in saida.out + saida.err
    assert fonte.requisicoes == [req]
    dados = json.loads((lote / c["processo"] / "pessoas.json").read_text())
    assert dados["pedidos"]["c"]["estado"] == "identificado"
    assert dados["provedor"][0]["id_externo"] == "opcao"


def test_prevenir_troca_de_cpf_apos_cobranca_com_provedor_desativado():
    c, d, fonte = caso(), decisoes(), Provedor()
    fonte.multiplos = False
    d["candidatos"]["c"]["CPF"] = "012.345.678-90"
    processar(c, d, fonte, lambda: None)
    d["candidatos"]["c"]["CPF"] = "52998224725"
    with pytest.raises(ValueError, match="Identidade"):
        processar(c, d, None, lambda: None)
    assert len(fonte.chamadas) == 2


def test_conciliar_encerrando_pedido_legado_sem_chamar_fornecedor():
    from guicredito.pessoas.contatos import conciliar_pedido

    c, d, fonte = caso(), decisoes(), Provedor()
    c["pedidos"] = {"c": {"estado": "incerto", "requisicao": "chave-antiga"}}
    with pytest.raises(ValueError, match="sem identificação"):
        conciliar_pedido(c, d, "chave-antiga", "nao_executado")
    conciliar_pedido(c, d, "chave-antiga", "encerrar")
    processar(c, d, fonte, lambda: None)
    assert c["pedidos"]["c"]["estado"] == "encerrado"
    assert fonte.chamadas == []
