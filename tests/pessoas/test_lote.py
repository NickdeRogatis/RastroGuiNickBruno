import json
from pathlib import Path

import pytest

from guicredito.pessoas.lote import Lote


def outputs(base, numero, conteudo):
    (base / numero).mkdir()
    (base / numero / "pessoas.json").write_text(conteudo)
    (base / "pessoas.xlsx").write_text(conteudo)
    (base / "manifesto.json").write_text(json.dumps({"formato":"guicredito-pessoas/1", "numeros":[numero]}))


NUMERO = "00000013020258260100"


def test_recusa_diretorio_alheio_e_link(tmp_path):
    (tmp_path / "intacto").write_text("sentinela")
    with pytest.raises(ValueError):
        with Lote(tmp_path, criar=True):
            pass
    assert sorted(p.name for p in tmp_path.iterdir()) == ["intacto"]
    link = tmp_path / "link"
    link.symlink_to(tmp_path, target_is_directory=True)
    with pytest.raises(ValueError):
        with Lote(link, criar=True):
            pass


def test_serializa_escrita_e_preserva_edicao(tmp_path):
    pasta = tmp_path / "lote"
    with Lote(pasta, criar=True) as lote:
        lote.publicar(lambda base: outputs(base, NUMERO, "primeiro"))
        with pytest.raises(ValueError, match="uso"):
            with Lote(pasta):
                pass
        (pasta / "pessoas.xlsx").write_text("alterado no Excel")
        with pytest.raises(ValueError, match="planilha"):
            lote.publicar(lambda base: outputs(base, NUMERO, "segundo"))
    assert (pasta / "pessoas.xlsx").read_text() == "alterado no Excel"


def test_interrupcao_e_recuperacao(tmp_path, monkeypatch):
    pasta = tmp_path / "lote"
    with Lote(pasta, criar=True) as lote:
        lote.publicar(lambda base: outputs(base, NUMERO, "primeiro"))
        real = Path.replace
        def interromper(self, destino):
            if self.name == "pessoas.xlsx":
                raise OSError("falha simulada")
            return real(self, destino)
        with monkeypatch.context() as m:
            m.setattr(Path, "replace", interromper)
            with pytest.raises(OSError):
                lote.publicar(lambda base: outputs(base, NUMERO, "segundo"))
    with Lote(pasta):
        assert (pasta / "pessoas.xlsx").read_text() == "segundo"
        assert (pasta / NUMERO / "pessoas.json").read_text() == "segundo"
        assert not (pasta / ".pessoas-publicar").exists()
