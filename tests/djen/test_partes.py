import pytest

from guicredito.djen.modelos import TipoCredor
from guicredito.djen.partes import (
    classe_de_cobranca,
    eh_cumprimento,
    eh_empresa,
    partes_do_cabecalho,
    tipo_credor,
)


@pytest.mark.parametrize(
    "classe,esperado",
    [
        ("EXECUçãO DE TíTULO EXTRAJUDICIAL", True),
        ("CUMPRIMENTO DE SENTENçA", True),
        ("CUMPRIMENTO PROVISÓRIO DE SENTENÇA", True),
        ("CUMPRIMENTO PROVISÓRIO DE DECISÃO", True),
        ("CUMPRIMENTO PROVISÓRIO DE SENTENÇA CONTRA A FAZENDA PÚBLICA", False),
        ("MONITóRIA", True),
        ("CUMPRIMENTO DE SENTENçA CONTRA A FAZENDA PúBLICA", False),
        ("CUMPRIMENTO DE SENTENçA DE OBRIGAçãO DE PRESTAR ALIMENTOS", False),
        ("Cumprimento de Sentença de Ações Coletivas", False),
        ("EXECUçãO FISCAL", False),
        ("EXECUçãO DA PENA", False),
        ("BUSCA E APREENSãO EM ALIENAçãO FIDUCIáRIA", False),
        ("DESPEJO POR FALTA DE PAGAMENTO CUMULADO COM COBRANçA", False),
        ("PROCEDIMENTO COMUM CíVEL", False),
        ("EMBARGOS à EXECUçãO", False),
    ],
)
def test_classe_de_cobranca(classe, esperado):
    assert classe_de_cobranca(classe) is esperado


@pytest.mark.parametrize(
    "nome,tipo",
    [
        ("BANCO SANTANDER (BRASIL) S.A.", TipoCredor.BANCO),
        ("Caixa Econômica Federal", TipoCredor.BANCO),
        ("COOPERATIVA DE CREDITO EXEMPLO - SICOOB", TipoCredor.BANCO),
        ("EXEMPLO CRÉDITO, FINANCIAMENTO E INVESTIMENTO S.A.", TipoCredor.BANCO),
        ("FIDC EXEMPLO NPL I", TipoCredor.FUNDO),
        ("EXEMPLO FUNDO DE INVESTIMENTO EM DIREITOS CREDITÓRIOS", TipoCredor.FUNDO),
        ("EXEMPLO SECURITIZADORA S.A.", TipoCredor.FUNDO),
        ("CONDOMÍNIO EDIFÍCIO EXEMPLO", TipoCredor.EMPRESA),
        ("LOJA EXEMPLO LTDA", TipoCredor.EMPRESA),
        ("JOÃO EXEMPLO DA SILVA", TipoCredor.PESSOA),
    ],
)
def test_tipo_credor(nome, tipo):
    assert tipo_credor(nome) is tipo


def test_eh_empresa():
    assert eh_empresa("LOJA EXEMPLO LTDA") and eh_empresa("MARIA MODELO ME") and eh_empresa("J. EXEMPLO EIRELI")
    assert not eh_empresa("JOÃO EXEMPLO")
    assert eh_empresa("PROMOVE EXEMPLO", "FAZ SABER a PROMOVE EXEMPLO, CNPJ: 00.000.000/0001-00, que")
    assert not eh_empresa("ANA FICTÍCIA", "intimada ANA FICTÍCIA, CPF 000.000.000-00, para")


def test_partes_do_cabecalho():
    t = (
        "EXECUÇÃO DE TÍTULO EXTRAJUDICIAL Nº 1003464-18.2022.8.26.0269/SP RELATOR : FULANO RELATOR "
        "EXEQUENTE : BANCO EXEMPLO S.A. ADVOGADO(A) : CICRANO ADVOGADO (OAB SP000000) "
        "EXECUTADO : JOÃO EXEMPLO ADVOGADO(A) : BELTRANO (OAB SP000001) ATO ORDINATÓRIO Intime-se."
    )
    assert partes_do_cabecalho(t) == (["BANCO EXEMPLO S.A."], ["JOÃO EXEMPLO"])
    assert partes_do_cabecalho("AUTOR : ANA FICTÍCIA RÉU : LOJA EXEMPLO LTDA DESPACHO Vistos.") == (
        ["ANA FICTÍCIA"],
        ["LOJA EXEMPLO LTDA"],
    )
    assert partes_do_cabecalho("Vistos. Intime-se.") == ([], [])


def test_cnpj_de_outro_nao_torna_a_pessoa_empresa():
    texto = "EXECUTADO : JOÃO EXEMPLO EXEQUENTE : BANCO EXEMPLO S.A., CNPJ: 00.000.000/0001-00"
    assert eh_empresa("JOÃO EXEMPLO", texto) is False


def test_cnpj_da_loja_nao_alcanca_a_pessoa_ao_lado():
    texto = "MARIA MODELO e LOJA EXEMPLO LTDA, CNPJ: 00.000.000/0001-00"
    assert eh_empresa("MARIA MODELO", texto) is False
    assert eh_empresa("LOJA EXEMPLO LTDA", texto) is True


def test_prefixo_do_nome_nao_herda_o_cnpj():
    texto = "JOÃO EXEMPLO LTDA, CNPJ: 00.000.000/0001-00"
    assert eh_empresa("JOÃO EXEMPLO", texto) is False
    assert eh_empresa("JOÃO EXEMPLO LTDA", texto) is True


def test_cpf_no_proprio_nome_forca_pessoa():
    assert eh_empresa("LOJA EXEMPLO LTDA", "LOJA EXEMPLO LTDA, CPF 000.000.000-00") is False


@pytest.mark.parametrize(
    "nome",
    [
        "LOJA EXEMPLO LIMITADA",
        "EXEMPLO SOCIEDADE ANÔNIMA",
        "COMPANHIA EXEMPLO",
        "EMPRESA EXEMPLO S.A",
        "LOJA EXEMPLO SA",
    ],
)
def test_nome_empresarial_por_extenso(nome):
    assert eh_empresa(nome) is True
    assert tipo_credor(nome) is TipoCredor.EMPRESA


def test_executados_no_plural_separa_pessoa_e_empresa():
    texto = (
        "EXECUTADOS : JOÃO EXEMPLO LTDA, CNPJ: 00.000.000/0001-00 e JOÃO EXEMPLO "
        "ADVOGADO(A) :"
    )
    _, devedores = partes_do_cabecalho(texto)
    assert devedores == ["JOÃO EXEMPLO LTDA", "JOÃO EXEMPLO"]


@pytest.mark.parametrize(
    "classe,esperado",
    [
        ("CUMPRIMENTO DE SENTENçA", True),
        ("Cumprimento Provisório de Sentença", True),
        ("EXECUÇÃO DE TÍTULO EXTRAJUDICIAL", False),
    ],
)
def test_eh_cumprimento(classe, esperado):
    assert eh_cumprimento(classe) is esperado


@pytest.mark.parametrize(
    "nome",
    [
        "INSTITUTO NACIONAL DO SEGURO SOCIAL - INSS",
        "PREFEITURA MUNICIPAL DE SÃO PAULO",
        "FAZENDA PÚBLICA DO ESTADO DE SÃO PAULO",
        "MUNICÍPIO DE EXEMPLO",
        "UNIÃO FEDERAL",
        "UNIMED EXEMPLO COOPERATIVA DE TRABALHO MÉDICO",
        "CENTRAL NACIONAL UNIMED - COOPERATIVA CENTRAL",
        "EXEMPLO COOP HABITACIONAL",
        "SINDICATO DOS EXEMPLOS DE SÃO PAULO",
        "FUNDAÇÃO EXEMPLO",
        "SÃO PAULO PREVIDÊNCIA - SPPREV",
        "TIM S A",
        "IBERIA LINEAS AEREAS DE ESPAÑA SOCIEDAD ANONIMA OPERADORA",
        "MASTER PREV CLUBE DE BENEFÍCIOS",
        "IGREJA EXEMPLO DO REINO",
        "CEB - CENTRO DE ESTUDOS DOS BENEFÍCIOS DOS APOSENTADOS",
        "DETRAN - DEPARTAMENTO ESTADUAL DE TRÂNSITO",
    ],
)
def test_orgao_publico_e_cooperativa_nao_sao_pessoa(nome):
    assert eh_empresa(nome)
    assert tipo_credor(nome) is not TipoCredor.PESSOA


@pytest.mark.parametrize("nome", ["JOSÉ CARLOS DA COSTA", "MARIA UNIÃO EXEMPLO", "ANA COOPER FICTÍCIA"])
def test_nome_de_pessoa_continua_pessoa(nome):
    assert not eh_empresa(nome)
