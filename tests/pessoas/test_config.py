import pickle
import pytest

from guicredito.pessoas.config import carregar_config


def test_defaults_e_slots(tmp_path):
    cfg = carregar_config(tmp_path / ".env", {})
    assert (cfg.busca, cfg.provedor, cfg.indice_cnpj) == (None, None, None)
    assert (cfg.intervalo, cfg.max_bytes, cfg.web_timeout) == (5, 5_000_000, 25)
    assert (cfg.hermes_timeout, cfg.hermes_contexto) == (180, 262144)
    assert cfg.hermes_url == "http://127.0.0.1:8642/v1"
    assert not cfg.diagnosticos


def test_env_sem_execucao_e_precedencia(tmp_path):
    env = tmp_path / ".env"
    env.write_text(
        "PESSOAS_BUSCA=hermes\nPESSOAS_HERMES_MODELO=antigo\n"
        'PESSOAS_HERMES_KEY="$(touch executado)"\n'
        'PESSOAS_INDICE_CNPJ=indice.sqlite\n', encoding="utf-8")
    cfg = carregar_config(env, {"PESSOAS_HERMES_MODELO": "hermes-agent"})
    assert cfg.hermes_modelo == "hermes-agent" and cfg.busca == "hermes"
    assert cfg.hermes_key == "$(touch executado)" and not cfg.diagnosticos
    assert cfg.indice_cnpj.name == "indice.sqlite"
    assert not (tmp_path / "executado").exists()
    assert "executado" not in repr(cfg)
    with pytest.raises(TypeError):
        pickle.dumps(cfg)


@pytest.mark.parametrize("env,termo", [
    ({"PESSOAS_BUSCA": "pago"}, "PESSOAS_BUSCA"),
    ({"PESSOAS_BUSCA": "hermes"}, "PESSOAS_HERMES_KEY"),
    ({"PESSOAS_BUSCA": "hermes"}, "PESSOAS_HERMES_MODELO"),
    ({"PESSOAS_INTERVALO": "2"}, "PESSOAS_INTERVALO"),
    ({"PESSOAS_INTERVALO": "NaN"}, "PESSOAS_INTERVALO"),
    ({"PESSOAS_HERMES_CONTEXTO": "zero"}, "PESSOAS_HERMES_CONTEXTO"),
    ({"PESSOAS_HERMES_TIMEOUT": "0"}, "PESSOAS_HERMES_TIMEOUT"),
])
def test_config_invalida_nao_expoe_valores(tmp_path, env, termo):
    cfg = carregar_config(tmp_path / ".env", env)
    assert termo in " ".join(cfg.diagnosticos)
