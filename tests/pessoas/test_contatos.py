import pytest

from guicredito.pessoas.contatos import ProvedorIncompativel, processar, validar_cpf, validar_cnpj


class Provedor:
    nome = "teste"
    identificadores = {"nome", "cpf", "cnpj"}

    def __init__(self):
        self.chamadas = []
        self.multiplos = True

    def identificar(self, identidade):
        self.chamadas.append(identidade)
        itens = [{"id": "x", "nome": "JOÃO EXEMPLO", "cidade": "Cidade A",
                  "telefone": "CONTATO_SENTINELA"}]
        return itens + [{"id": "y", "nome": "JOÃO EXEMPLO"}] if self.multiplos else itens

    def obter_contatos(self, id_confirmado):
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
    def falhou(_):
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
