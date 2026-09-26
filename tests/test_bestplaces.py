"""Parsing puro do inventário do BestPlaces (camada "À venda") + selo de oportunidade — sem DB."""
import math

import pytest

from src.scrapers.bestplaces import (
    area_terreno_texto,
    categoria,
    from_record,
    oportunidade_tier,
)
from src.scrapers.load_bestplaces import _campos, sigma_hedonico

_TERRENO = {
    "id": "32988098", "source": "chavesnamao", "sources": ["chavesnamao", "zap"],
    "url": "https://www.chavesnamao.com.br/imovel/terreno/id-32988098/",
    "type": "Terreno / Lote", "business": "SALE", "title": "Terreno 450 m² no Altiplano",
    "price": 900000, "area_max": 450, "neighborhood": "Altiplano Cabo Branco",
    "lat": -7.13022, "lng": -34.82985, "approx_location": False,
    "images": ["https://img/1.jpg"], "iptu": 1200,
    "advertiser": {"name": "Imobiliária X", "phone": "(83) 99999-0000", "creci": "1234-J"},
}


@pytest.mark.parametrize("tipo,esperado", [
    ("Terreno / Lote", "terreno"), ("Lote/Terreno", "terreno"), ("Terreno em Condomínio", "terreno"),
    ("Casa", "casa"), ("Casa / Sobrado", "casa"), ("Sobrado", "casa"),
    ("Casa de condomínio", None), ("Casa / Sobrado em Condomínio", None),
    ("Apartamento", None), ("Flat", None), (None, None),
])
def test_categoria(tipo, esperado):
    assert categoria(tipo) == esperado


def test_terreno_ok_e_sem_telefone():
    a = from_record(_TERRENO)
    assert a is not None and a.categoria == "terreno"
    assert a.area_terreno_m2 == 450.0 and a.preco == 900000.0
    assert a.anunciante_creci == "1234-J" and a.anunciante_nome == "Imobiliária X"
    assert a.fontes == ("chavesnamao", "zap")
    assert "99999" not in repr(a)          # LGPD: telefone nunca entra


def test_apartamento_e_aluguel_ficam_fora():
    assert from_record(_TERRENO | {"type": "Apartamento"}) is None
    assert from_record(_TERRENO | {"business": "RENTAL"}) is None


def test_comodos_zero_e_terreno_viram_nao_informado():
    zeros = {"bedrooms": 0, "bathrooms": 0, "suites": 0, "parking": 0}
    t = from_record(_TERRENO | zeros)
    assert (t.quartos, t.banheiros, t.suites, t.vagas) == (None, None, None, None)
    c = from_record(_TERRENO | zeros | {"type": "Casa", "bedrooms": 3})
    assert (c.quartos, c.banheiros, c.suites, c.vagas) == (3, None, None, 0)  # 0 vaga é real


def test_casa_area_de_terreno_vem_do_texto():
    casa = _TERRENO | {"type": "Casa", "area_max": 180,
                       "description": "Casa ampla em terreno de 12x30, 3 quartos."}
    a = from_record(casa)
    assert a.area_anunc_m2 == 180.0 and a.area_terreno_m2 == 360.0


@pytest.mark.parametrize("txt,m2", [
    ("terreno de 360 m²", 360.0), ("Lote com 450,5m2 plano", 450.5),
    ("área do terreno: 1.200 m²", 1200.0), ("lote medindo 10 x 25", 250.0),
    ("casa com 3 quartos", None), (None, None),
])
def test_area_terreno_texto(txt, m2):
    assert area_terreno_texto(txt) == m2


@pytest.mark.parametrize("desc,conf,susp,tier", [
    (0.50, 0.30, False, "rara"), (0.50, 0.10, False, "incerta"),
    (0.25, 0.30, False, "boa"), (0.25, 0.00, False, "incerta"),
    (0.00, 0.90, False, "mercado"), (-0.20, 0.90, False, "acima"),
    (0.90, 0.90, True, "suspeito"), (None, 0.9, False, None),
])
def test_tier_igual_ao_card_do_bestplaces(desc, conf, susp, tier):
    assert oportunidade_tier(desc, conf, susp) == tier


def test_campos_hedonico_terreno_barato_mas_incerto():
    # σ do hedônico de terreno é alto (≈0,6) → confiabilidade 0 → nunca "rara/boa", só "incerta".
    art = {"cv_espacial": {"mae_log_modelo": 0.4846}}
    s = sigma_hedonico(art)
    c = _campos(preco=600_000, esperado=1_000_000, sigma=s, modelo="hedonico")
    assert c["confiabilidade"] == 0.0
    assert c["oportunidade_tier"] == "incerta"
    assert math.isclose(c["desconto_pct"], 0.4)
    assert c["preco_esperado_lo"] < 1_000_000 < c["preco_esperado_hi"]


def test_campos_suspeito_quando_longe_demais():
    c = _campos(preco=100_000, esperado=2_000_000, sigma=0.3, modelo="lightgbm")
    assert c["suspeito"] is True and c["oportunidade_tier"] == "suspeito"
