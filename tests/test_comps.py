"""Testes da lógica pura de parsing de comps (imoveis_jp.json) — sem rede/DB."""
from src.scrapers.comps import (
    Comp,
    canonical_bairro,
    comp_from_record,
    filter_to_official,
    normalize_bairro_key,
)

# registro real (trecho) do imoveis_jp.json
_REC = {
    "id": "2878107890",
    "external_id": "F7X1KLS",
    "source": "vivareal",
    "type": "Apartamento",
    "business": "SALE",
    "price": 50000,
    "area_min": 48,
    "area_max": 48,
    "bedrooms": 2,
    "parking": 1,
    "neighborhood": "Ernesto Geisel",
    "lat": -7.18812,
    "lng": -34.870084,
}


def test_comp_ok():
    c = comp_from_record(_REC)
    assert isinstance(c, Comp)
    assert c.source == "vivareal"
    assert c.source_id == "2878107890"
    assert c.tipo == "Apartamento"
    assert c.business == "SALE"
    assert c.preco == 50000.0
    assert c.area_m2 == 48.0
    assert c.quartos == 2
    assert c.vagas == 1
    assert c.bairro == "Ernesto Geisel"
    assert c.lat == -7.18812 and c.lon == -34.870084


def test_comp_descarta_sem_preco():
    assert comp_from_record({**_REC, "price": None}) is None
    assert comp_from_record({**_REC, "price": 0}) is None


def test_comp_descarta_area_zero_ou_ausente():
    assert comp_from_record({**_REC, "area_min": 0, "area_max": None}) is None
    assert comp_from_record({**_REC, "area_min": None, "area_max": None}) is None


def test_comp_descarta_sem_bairro():
    assert comp_from_record({**_REC, "neighborhood": ""}) is None
    assert comp_from_record({**_REC, "neighborhood": None}) is None


def test_comp_descarta_sem_id():
    assert comp_from_record({**_REC, "id": None}) is None


def test_comp_area_fallback_para_area_max():
    c = comp_from_record({**_REC, "area_min": None, "area_max": 60})
    assert c is not None and c.area_m2 == 60.0


def test_comp_business_default_sale():
    c = comp_from_record({**_REC, "business": None})
    assert c is not None and c.business == "SALE"


def test_comp_source_default_vivareal():
    c = comp_from_record({**_REC, "source": None})
    assert c is not None and c.source == "vivareal"


def test_comp_bairro_normaliza_espacos():
    c = comp_from_record({**_REC, "neighborhood": "  Jardim   Oceania "})
    assert c is not None and c.bairro == "Jardim Oceania"


def test_comp_sem_lat_lon_ok():
    c = comp_from_record({**_REC, "lat": None, "lng": None})
    assert c is not None and c.lat is None and c.lon is None


# ───────── normalização/whitelist de bairro (filtro de ingestão) ─────────
def test_normalize_bairro_key_translitera_acentos():
    # acento some (NFKD) → comp sem acento casa com bairro oficial acentuado
    assert normalize_bairro_key("Bancários") == "BANCARIOS"
    assert normalize_bairro_key("bancarios") == "BANCARIOS"
    assert normalize_bairro_key("Jardim  Oceania") == "JARDIMOCEANIA"
    assert normalize_bairro_key("Av. Epitácio, 123") == "AVEPITACIO123"


def test_canonical_bairro_canoniza_para_grafia_oficial():
    canon = {"BANCARIOS": "Bancários", "JARDIMOCEANIA": "Jardim Oceania"}
    assert canonical_bairro("bancarios", canon) == "Bancários"
    assert canonical_bairro("JARDIM OCEANIA", canon) == "Jardim Oceania"


def test_canonical_bairro_rejeita_rua_ou_desconhecido():
    canon = {"BANCARIOS": "Bancários"}
    assert canonical_bairro("Avenida Infante Dom Henrique", canon) is None
    assert canonical_bairro("Penha", canon) is None
    assert canonical_bairro(None, canon) is None


def test_filter_to_official_conta_e_canoniza():
    canon = {"BANCARIOS": "Bancários"}
    comps = [
        comp_from_record(_REC),  # "Ernesto Geisel" → fora da whitelist
        comp_from_record({**_REC, "id": "2", "neighborhood": "bancarios"}),  # → "Bancários"
    ]
    kept, rejeitados = filter_to_official(comps, canon)
    assert rejeitados == 1
    assert len(kept) == 1
    assert kept[0].bairro == "Bancários"  # grafia oficial, não "bancarios"
