"""Testes da lógica pura de geocodificação (Nominatim) — sem rede/DB."""
from src.scrapers.comps import comp_from_record
from src.scrapers.geocode import (
    build_query,
    cache_key,
    nominatim_params,
    parse_nominatim,
)

# registro real (trecho) do imoveis_jp.json — com street e sem coordenada
_REC = {
    "id": "2878107890",
    "source": "vivareal",
    "type": "Apartamento",
    "business": "SALE",
    "price": 50000,
    "area_min": 48,
    "neighborhood": "Ernesto Geisel",
    "street": "Rua Radialista Antônio Assunção de Jesus",
    "lat": None,
    "lng": None,
}


# ───────── Comp carrega o endereço (street) p/ o backfill de geocodificação ─────────
def test_comp_carrega_endereco():
    c = comp_from_record(_REC)
    assert c is not None
    assert c.endereco == "Rua Radialista Antônio Assunção de Jesus"


def test_comp_endereco_normaliza_espacos():
    c = comp_from_record({**_REC, "street": "  Av.   Epitácio Pessoa, 500 "})
    assert c is not None and c.endereco == "Av. Epitácio Pessoa, 500"


def test_comp_sem_street_endereco_none():
    c = comp_from_record({**_REC, "street": None})
    assert c is not None and c.endereco is None
    c = comp_from_record({**_REC, "street": ""})
    assert c is not None and c.endereco is None


# ───────── Comp marca coordenada aproximada (pino de portal ≠ endereço exato) ─────────
def test_comp_loc_aproximada():
    c = comp_from_record({**_REC, "lat": -7.115, "lng": -34.838, "approx_location": True})
    assert c is not None and c.loc_aproximada is True


def test_comp_loc_exata_ou_ausente():
    c = comp_from_record({**_REC, "lat": -7.115, "lng": -34.838, "approx_location": False})
    assert c is not None and c.loc_aproximada is False
    c = comp_from_record(_REC)  # sem o campo → não aproximada
    assert c is not None and c.loc_aproximada is False


# ───────── build_query: monta a consulta freeform do Nominatim ─────────
def test_build_query_com_endereco_e_bairro():
    q = build_query("Av. Epitácio Pessoa, 500", "Tambaú")
    assert q == "Av. Epitácio Pessoa, 500, Tambaú, João Pessoa, Paraíba, Brasil"


def test_build_query_sem_bairro():
    q = build_query("Av. Epitácio Pessoa, 500", None)
    assert q == "Av. Epitácio Pessoa, 500, João Pessoa, Paraíba, Brasil"


def test_build_query_sem_endereco_none():
    # sem street NÃO geocodificamos: centroide de bairro empilharia pontos idênticos
    # e distorceria a mediana por raio (o caso bairro já é coberto pela view).
    assert build_query(None, "Tambaú") is None
    assert build_query("", "Tambaú") is None
    assert build_query("   ", "Tambaú") is None


# ───────── cache_key: chave estável p/ market.geocode_cache ─────────
def test_cache_key_ignora_caixa_acento_espacos_pontuacao():
    a = cache_key("Av. Epitácio Pessoa, 500", "Tambaú")
    b = cache_key("  av epitacio pessoa 500 ", "TAMBAU")
    assert a == b


def test_cache_key_distingue_bairros():
    # mesma rua em bairros diferentes = consultas diferentes
    assert cache_key("Rua São Paulo", "Bancários") != cache_key("Rua São Paulo", "Manaíra")


def test_cache_key_bairro_none():
    assert cache_key("Rua São Paulo", None) == cache_key("Rua São Paulo", None)
    assert cache_key("Rua São Paulo", None) != cache_key("Rua São Paulo", "Bancários")


# ───────── nominatim_params: parâmetros da requisição ─────────
def test_nominatim_params_restringe_a_joao_pessoa():
    p = nominatim_params("Rua X, João Pessoa, Paraíba, Brasil")
    assert p["q"] == "Rua X, João Pessoa, Paraíba, Brasil"
    assert p["format"] == "jsonv2"
    assert p["limit"] == "1"
    assert p["bounded"] == "1"  # com viewbox: descarta resultado fora do envelope
    # viewbox = lon1,lat1,lon2,lat2 (envelope de JP)
    parts = [float(x) for x in p["viewbox"].split(",")]
    assert len(parts) == 4


# ───────── parse_nominatim: resposta → (lat, lon) validado ─────────
def test_parse_nominatim_ok():
    payload = [{"lat": "-7.1195", "lon": "-34.8450", "display_name": "Tambaú, João Pessoa"}]
    assert parse_nominatim(payload) == (-7.1195, -34.8450)


def test_parse_nominatim_vazio():
    assert parse_nominatim([]) is None
    assert parse_nominatim(None) is None


def test_parse_nominatim_fora_de_jp_rejeita():
    # Recife: casamento errado de rua homônima → descarta
    assert parse_nominatim([{"lat": "-8.0476", "lon": "-34.8770"}]) is None
    # São Paulo
    assert parse_nominatim([{"lat": "-23.5505", "lon": "-46.6333"}]) is None


def test_parse_nominatim_malformado():
    assert parse_nominatim([{"lat": "abc", "lon": "-34.84"}]) is None
    assert parse_nominatim([{"lon": "-34.84"}]) is None
    assert parse_nominatim([{}]) is None
