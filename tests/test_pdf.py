"""Testes da geração de PDF da ficha (puro — sem DB; só monta bytes a partir do LotFicha)."""
import io

import pytest

from src.api.pdf import build_ficha_pdf
from src.api.schemas import VGV, LotFicha, Restricao, Viability
from src.api.viability import aviso_area_grande


def _ficha_completa() -> LotFicha:
    return LotFicha(
        id=199917,
        logradouro="Rua Exemplo",
        bairro="BANCÁRIOS",
        tipo="TERRITORIAL",
        area_geom_m2=723.0,
        viability=Viability(sigla="ZH1", nome_zona="Zona Habitacional 1", to_max_pct=50, tap_min_pct=25,
                            area_projecao_max_m2=362.0, area_permeavel_min_m2=181.0),
        restricao=Restricao(altura_label="Livre — limitada pelos recuos"),
        vgv=VGV(
            preco_m2_venda=6345.0, n_comps=468, eficiencia=0.8, pavimentos=4,
            area_projecao_m2=362.0, area_privativa_pavto_m2=289.6, vgv_por_pavimento=1_836_164.0,
            area_construida_m2=1448.0, area_privativa_total_m2=1158.4, vgv_total=7_344_658.0,
            premissas="mediana de 468 comps; eficiência 80%; 4 pavimentos (premissa)",
        ),
    )


def test_pdf_tem_header_pdf_e_conteudo():
    pdf = build_ficha_pdf(_ficha_completa())
    assert isinstance(pdf, bytes)
    assert pdf[:5] == b"%PDF-"
    assert len(pdf) > 1000  # tem conteúdo real, não um stub vazio


def test_pdf_sem_viability_nem_vgv_nao_quebra():
    f = LotFicha(id=1, bairro="X", restricao=Restricao(altura_label="A confirmar"))
    pdf = build_ficha_pdf(f)
    assert pdf[:5] == b"%PDF-"


@pytest.mark.parametrize(
    ("area", "sigla", "trecho"),
    [(1_876_650, "ZEPA1", "Proteção Ambiental"), (647_225, "ZH2", "Gleba de 64,7 ha")],
)
def test_pdf_gleba_zepa_mostra_aviso_da_zona(area, sigla, trecho):
    pypdf = pytest.importorskip("pypdf")
    f = LotFicha(
        id=2, bairro="X", tipo="TERRITORIAL", area_geom_m2=area,
        viability=Viability(sigla=sigla),
        restricao=Restricao(altura_label="A confirmar"),
        geometria_suspeita=True,
        geometria_aviso=aviso_area_grande(area, sigla),
    )
    txt = " ".join(p.extract_text() for p in pypdf.PdfReader(io.BytesIO(build_ficha_pdf(f))).pages)
    txt = " ".join(txt.split())
    assert "VGV não se aplica" in txt
    assert trecho in txt
    assert "conferir geometria" not in txt
