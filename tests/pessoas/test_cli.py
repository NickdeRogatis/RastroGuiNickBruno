from guicredito.pessoas.__main__ import main


def test_verificar_somente_setup_sem_credencial(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    for key in ("PESSOAS_HERMES_KEY","PESSOAS_HERMES_MODELO","PESSOAS_BUSCA"):
        monkeypatch.delenv(key, raising=False)
    assert main(["verificar"]) == 2
    saida = capsys.readouterr()
    assert "modelo" in (saida.out + saida.err).lower()
    assert "provedor" in (saida.out + saida.err).lower()


def test_entrada_invalida_nao_exibe_nome(tmp_path, capsys):
    arquivo = tmp_path / "JOÃO EXEMPLO.json"
    assert main(["pesquisar", "--selecao", str(arquivo), "--planilha", str(arquivo),
                 "--aprofundamento", str(tmp_path), "--saida", str(tmp_path/"externo")]) == 2
    saida = capsys.readouterr()
    assert "JOÃO EXEMPLO" not in saida.err + saida.out


def test_cli_oab_sem_lote_nao_cria_ou_vaza(tmp_path,capsys):
    pasta = tmp_path / "ausente"
    assert main(["importar-oab","--lote",str(pasta),"--arquivo",str(tmp_path/"JOÃO EXEMPLO.json")]) == 2
    assert not pasta.exists()
    assert "JOÃO EXEMPLO" not in "".join(capsys.readouterr())
