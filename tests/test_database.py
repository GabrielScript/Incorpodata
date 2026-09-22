"""Engine resiliente ao Neon: conexão ociosa derrubada pelo servidor não pode virar 500."""
from src.db.database import get_engine


def test_engine_testa_conexao_antes_de_usar(monkeypatch):
    # O Neon suspende o compute ocioso e fecha as conexões do pool. Sem pre-ping, o 1º request
    # depois disso pegava uma conexão morta → "SSL connection has been closed unexpectedly" → 500
    # (visto em prod em 22/09). create_engine não conecta: dispensa banco.
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@localhost:5432/x")
    assert get_engine().pool._pre_ping is True
