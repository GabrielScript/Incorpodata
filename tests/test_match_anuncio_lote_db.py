"""Integração DB (gated): casamento anúncio → lote confere o pino com a rua anunciada.

Só roda com INCORPODATA_DB_TESTS=1 e Postgres alcançável (DATABASE_URL ou dev local);
caso contrário skip — a suíte padrão continua 100% offline. Tudo numa transação desfeita.

Contexto (26/09): casa do Chaves na Mão anunciada na R. Iracema Guedes Lins (Altiplano) com
pino "exato" a 647 m dali, dentro de um lote de 7.588 m² de outra rua; sem área de terreno p/
conferir, o ponto_no_lote casava com 0,85. Lotes de teste ficam no mar (sem lote real perto).
"""
from __future__ import annotations

import os

import pytest
from sqlalchemy import text

pytestmark = pytest.mark.skipif(
    os.getenv("INCORPODATA_DB_TESTS") != "1",
    reason="integração DB: export INCORPODATA_DB_TESTS=1 (e Postgres de pé) p/ rodar",
)

FONTE = "__test_rua__"
# Dois lotes de 20×20 m no mar, a ~600 m um do outro (EPSG:31985, metros).
X_ANUNCIADA, X_OUTRA, Y = 310_000.0, 310_600.0, 9_210_000.0

_LOTE = text(
    """
    INSERT INTO geo.lotes (logradouro, bairro, tipo, geom)
    VALUES (:logradouro, 'ZZTESTE', 'PREDIAL',
            ST_Multi(ST_MakeEnvelope(:x, :y, :x + 20, :y + 20, 31985)))
    RETURNING id
    """
)
_ANUNCIO = text(
    """
    INSERT INTO market.anuncios
      (fonte, fonte_id, url, tipo, preco, bairro_texto, logradouro_texto, ativo,
       loc_aproximada, geom, lat, lon)
    SELECT :fonte, :fid, 'https://x/' || :fid, 'Casa', 1000000, 'ZZTESTE', :rua, true, false,
           ST_SetSRID(ST_MakePoint(:x, :y), 31985), ST_Y(p), ST_X(p)
    FROM ST_Transform(ST_SetSRID(ST_MakePoint(:x, :y), 31985), 4326) p
    RETURNING id
    """
)


@pytest.fixture()
def conn():
    from src.db.database import get_engine

    c = get_engine().connect()
    tx = c.begin()
    try:
        yield c
    finally:
        tx.rollback()
        c.close()


def _lote_casado(conn, anuncio_id: int) -> int | None:
    return conn.execute(
        text("SELECT lote_id FROM market.anuncio_lote WHERE anuncio_id = :a"), {"a": anuncio_id}
    ).scalar()


def test_pino_longe_da_rua_anunciada_nao_casa_por_ponto(conn):
    from src.scrapers.match_anuncio_lote import casar_em

    conn.execute(_LOTE, {"logradouro": "ZZTESTE ANUNCIADA", "x": X_ANUNCIADA, "y": Y})
    lote_outra = conn.execute(_LOTE, {"logradouro": "ZZTESTE OUTRA", "x": X_OUTRA, "y": Y}).scalar()

    def anuncio(fid: str, rua: str | None, dx: float) -> int:
        return conn.execute(_ANUNCIO, {"fonte": FONTE, "fid": fid, "rua": rua,
                                       "x": X_OUTRA + dx, "y": Y + 10}).scalar()

    errado = anuncio("pino-errado", "Rua ZZteste Anunciada", 5)      # pino a ~600 m da rua dele
    certo = anuncio("pino-certo", "Av. ZZTESTE Outra", 10)            # pino no lote da rua dele
    sem_rua = anuncio("sem-rua", None, 15)                            # nada a conferir
    rua_fora = anuncio("rua-fora", "Rua Que Nao Existe ZZ", 12)       # rua fora do cadastro

    casar_em(conn)

    assert _lote_casado(conn, errado) is None
    assert _lote_casado(conn, certo) == lote_outra
    assert _lote_casado(conn, sem_rua) == lote_outra
    assert _lote_casado(conn, rua_fora) == lote_outra


@pytest.mark.parametrize("rua,chave", [
    ("Rua Iracema Guedes Lins", "IRACEMAGUEDESLINS"),
    ("IRACEMA GUEDES LINS", "IRACEMAGUEDESLINS"),
    ("Av. Epitácio Pessoa", "EPITACIOPESSOA"),
    ("R. São João", "SAOJOAO"),
    ("Ruan Silva", "RUANSILVA"),       # "Rua" só como palavra inteira
    ("Rua", "RUA"),
    ("Rodovia BR-230", "BR230"),
    # grafias do cadastro: número/condomínio colado, artigo invertido; preposição some dos dois lados
    ("JOAO CIRILO DA SILVA, 1700 - RES. VILA REAL", "JOAOCIRILOSILVA"),
    ("HILTON SOUTO MAIOR,6701- C. CABO BRANCO PRIVE", "HILTONSOUTOMAIOR"),
    ("DOUTOR VALDEVINO GREGORIO DE ANDRADE - PARK COWBOY", "DOUTORVALDEVINOGREGORIOANDRADE"),
    ("Rua Doutor Valdevino Gregório de Andrade", "DOUTORVALDEVINOGREGORIOANDRADE"),
    ("CORTIÇAS, DAS", "CORTICAS"),
    ("Rua das Cortiças", "CORTICAS"),
    ("JOSÉ CÂNDIDO DA SILVA", "JOSECANDIDOSILVA"),
    ("Rua José Cândido Silva", "JOSECANDIDOSILVA"),
    ("", None),
    (None, None),
])
def test_chave_rua(conn, rua, chave):
    assert conn.execute(text("SELECT market.chave_rua(:r)"), {"r": rua}).scalar() == chave
