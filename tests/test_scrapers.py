"""Testes da lógica pura de parsing dos scrapers (sem rede/DB)."""
from src.scrapers.sources import (
    Anuncio,
    clean_area,
    clean_bairro,
    clean_preco,
    fonte_id_from_url,
    normalize,
)


def test_fonte_id_vivareal():
    u = "https://www.vivareal.com.br/imovel/lote-terreno-paratibe-joao-pessoa-200m2-venda-RS150000-id-2892640397/?source=ranking%2Crp"
    assert fonte_id_from_url(u) == "2892640397"


def test_fonte_id_chavesnamao():
    u = "https://www.chavesnamao.com.br/imovel/terreno-a-venda-pb-joao-pessoa-gramame-360m2-RS210000/id-25641415/"
    assert fonte_id_from_url(u) == "25641415"


def test_fonte_id_ausente():
    assert fonte_id_from_url("https://exemplo.com/sem-id/") is None
    assert fonte_id_from_url(None) is None


def test_clean_preco_numero_e_string():
    assert clean_preco(210000) == 210000.0
    assert clean_preco("R$ 1.059.000,00") == 1059000.0
    assert clean_preco("R$ 95.000") == 95000.0
    assert clean_preco(0) is None
    assert clean_preco(None) is None


def test_clean_area_numero_e_string():
    assert clean_area(360) == 360.0
    assert clean_area("2.304 m²") == 2304.0
    assert clean_area("231 m²") == 231.0
    assert clean_area(None) is None


def test_clean_bairro():
    assert clean_bairro("  Barra  de   Gramame ") == "Barra de Gramame"
    assert clean_bairro("") is None


def test_normalize_ok():
    a = normalize("vivareal", {
        "url": "https://www.vivareal.com.br/imovel/x-id-2892640397/?source=rp",
        "titulo": "Lote 200 m²",
        "preco": 150000,
        "area_m2": 200,
        "bairro": "Paratibe",
    })
    assert isinstance(a, Anuncio)
    assert a.fonte_id == "2892640397" and a.preco == 150000.0 and a.area_anunc_m2 == 200.0


def test_normalize_descarta_sem_id_ou_sem_dados():
    assert normalize("vivareal", {"url": "https://x/sem-id/", "preco": 1}) is None
    assert normalize("vivareal", {"url": "https://x/id-9/", "preco": None, "area_m2": None}) is None
