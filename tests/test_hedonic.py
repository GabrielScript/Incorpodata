"""Testes do modelo hedônico: transforms, retransformação de Duan, CV sem vazamento."""
from __future__ import annotations

import math

import numpy as np
import pandas as pd
import pytest

from src.ml.hedonic import (
    FEATURES,
    apt_m2_por_bairro,
    build_features,
    dist_mar_km,
    duan_smearing,
    haversine_km,
    predict_m2,
    spatial_cv,
)


def test_haversine_conhecida():
    # Manaíra Shopping -> Lagoa: ~5,4 km em linha reta
    d = haversine_km(-7.1006, -34.8360, -7.1195, -34.8811)
    assert 4.5 < d < 6.5
    assert haversine_km(-7.1, -34.8, -7.1, -34.8) == 0.0


def test_dist_mar_no_litoral_quase_zero():
    assert dist_mar_km(-7.115, -34.823) < 0.5   # Tambaú
    assert dist_mar_km(-7.12, -34.88) > 4.0     # Centro/Lagoa


def test_duan_smearing():
    assert duan_smearing(np.zeros(10)) == 1.0
    # Jensen: E[exp(eps)] > exp(E[eps]) = 1 p/ resíduos centrados não-degenerados
    rng = np.random.default_rng(0)
    assert duan_smearing(rng.normal(0, 0.5, 5000)) > 1.0


def _df_sintetico(n_por_bairro: int = 30) -> pd.DataFrame:
    """6 bairros com níveis de preço distintos + ruído; geometria plausível de JP."""
    rng = np.random.default_rng(7)
    rows = []
    bairros = {"A": 8.0, "B": 7.6, "C": 7.2, "D": 6.9, "E": 6.6, "F": 6.3}
    for i, (b, nivel) in enumerate(bairros.items()):
        for _ in range(n_por_bairro):
            area = float(rng.uniform(200, 2000))
            lat = -7.07 - 0.02 * i + rng.normal(0, 0.004)
            lng = -34.83 - 0.01 * i + rng.normal(0, 0.004)
            y = nivel - 0.1 * math.log(area) + rng.normal(0, 0.25)
            rows.append({
                "id": f"{b}{len(rows)}", "bairro": b, "area_m2": area,
                "lat": lat, "lng": lng, "preco_m2": math.exp(y),
            })
    return pd.DataFrame(rows)


def _com_features(df: pd.DataFrame) -> pd.DataFrame:
    apt_med = {b: 6000.0 for b in df["bairro"].unique()}
    return build_features(df, apt_med, 5000.0)


def test_build_features_schema():
    df = _com_features(_df_sintetico())
    for f in FEATURES + ["y"]:
        assert f in df.columns
        assert df[f].notna().all(), f
    assert (df["log_area"] > 0).all()


def test_spatial_cv_baseline_sem_vazamento():
    """Cada fold de teste = bairros ausentes do treino -> baseline cai no fallback
    (mediana global do treino), nunca na mediana do próprio bairro de teste."""
    df = _com_features(_df_sintetico())
    cv = spatial_cv(df, n_splits=3)
    assert cv["n_splits"] == 3
    # bairros têm níveis bem separados: baseline global erra muito; modelo (usa
    # geografia contínua) tem que errar menos em log
    assert cv["mae_log_modelo"] < cv["mae_log_baseline"]
    assert 0 < cv["mdape_modelo"] < 2.0


def test_cv_determinismo():
    df = _com_features(_df_sintetico())
    a, b = spatial_cv(df, n_splits=3), spatial_cv(df, n_splits=3)
    assert a["mae_log_modelo"] == b["mae_log_modelo"]


def test_predict_m2_mediana_vs_esperanca():
    artifact = {
        "coeficientes": {"const": 4.0, "log_area": -0.1, "dist_mar_km": -0.03,
                         "dist_manaira_km": -0.05, "dist_centro_km": 0.02,
                         "log_apt_m2_bairro": 0.5},
        "features": FEATURES,
        "smearing_duan": 1.12,
        "apt_m2_bairro": {"Manaíra": 9000.0},
        "apt_m2_global": 5500.0,
    }
    mediana = predict_m2(artifact, 500, -7.10, -34.84, "Manaíra")
    esperanca = predict_m2(artifact, 500, -7.10, -34.84, "Manaíra", esperanca=True)
    assert mediana > 0
    assert esperanca == pytest.approx(mediana * 1.12)
    # bairro desconhecido -> fallback global, ainda prediz
    assert predict_m2(artifact, 500, -7.10, -34.84, "Bairro X") > 0


def test_apt_m2_por_bairro_min_n():
    apts = pd.DataFrame({
        "bairro": ["A"] * 20 + ["B"] * 3,
        "preco_m2": [5000.0] * 20 + [9000.0] * 3,
    })
    med, glob = apt_m2_por_bairro(apts, min_n=15)
    assert med == {"A": 5000.0}   # B descartado (n<15)
    assert glob == 5000.0
