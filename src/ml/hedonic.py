"""Modelo hedônico de preço de terreno (baseline OLS log-log) — treina de imoveis_jp.json.

Contrato de dados
-----------------
Grão:    1 anúncio de Lote/Terreno (source, source_id), João Pessoa.
Target:  log(preco_m2). ATENÇÃO: preço PEDIDO (anúncio), não transação — o modelo
         estima o nível de anúncio do mercado; útil p/ ranking relativo (sub/sobre-
         preçado vs mercado), não como laudo de valor absoluto.
Features (todas disponíveis em tempo de predição p/ qualquer lote com centróide):
  - log_area          : log(area_m2) — elasticidade do preço/m² vs tamanho
  - dist_mar_km       : distância haversine ao ponto costeiro mais próximo (âncoras aprox.)
  - dist_manaira_km   : distância ao polo Manaíra Shopping
  - dist_centro_km    : distância à Lagoa (Centro)
  - log_apt_m2_bairro : log da mediana R$/m² de APARTAMENTO no bairro (covariável de
                        mercado calculada de linhas distintas do target → não é vazamento
                        de label; fallback = mediana da cidade quando bairro tem < MIN_APT)
Saneamento: preco_m2 ∈ [100, 20000], area ∈ [100, 100000] m², lat/lng obrigatórios.
Split:   GroupKFold por bairro (spatial CV). Random K-fold superestima o desempenho
         porque anúncios do mesmo bairro dividem o efeito local (autocorrelação espacial).
Baseline a bater: mediana de preco_m2 do bairro no fold de treino (≈ sistema atual).

Retransformação: E[preço|X] = exp(Xβ)·E[exp(ε)] ≠ exp(Xβ). Para valor esperado em R$
usa-se o fator de Duan (smearing) ŝ = média(exp(resíduos)); exp(Xβ) puro estima a
MEDIANA condicional — suficiente (e preferível) p/ ranking e p/ "X% abaixo do previsto".
Hipótese do smearing: E[exp(ε)] < ∞ (cauda direita do resíduo-log mais leve que
exponencial; falha p/ caudas t-pesadas — vigiar outliers de anúncio). Se o corte de
oportunidade for por RAZÃO ABSOLUTA (ex.: preço < 0,7×previsto), usar a previsão de
mediana consistentemente — trocar smearing depois de calibrar o corte muda o flag.

Uso:
    python -m src.ml.hedonic                 # treina + spatial CV + salva artefato
    python -m src.ml.hedonic --file dados.json --out artifacts/hedonic.json
Reprodutível: sem estado oculto; seed fixa; artefato carrega config + hash dos dados.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_FILE = ROOT / "imoveis_jp.json"
DEFAULT_OUT = ROOT / "artifacts" / "hedonic.json"

SEED = 42
MIN_APT_POR_BAIRRO = 15  # mesmo corte do preco_m2_bairro/VGV

# Saneamento (lote é mais barato que o corte geral 800–30000 da view de apto)
PRECO_M2_MIN, PRECO_M2_MAX = 100.0, 20000.0
AREA_MIN, AREA_MAX = 100.0, 100_000.0

# Âncoras geográficas (aprox., WGS84). Costa de JP corre ~N-S; 5 pontos bastam
# p/ distância-ao-mar com erro << variação entre bairros.
COSTA = [
    (-7.070, -34.834),   # Bessa
    (-7.098, -34.828),   # Manaíra
    (-7.115, -34.823),   # Tambaú
    (-7.135, -34.810),   # Cabo Branco
    (-7.155, -34.796),   # Ponta do Seixas
]
MANAIRA_SHOPPING = (-7.1006, -34.8360)
CENTRO_LAGOA = (-7.1195, -34.8811)

FEATURES = ["log_area", "dist_mar_km", "dist_manaira_km", "dist_centro_km", "log_apt_m2_bairro"]


@dataclass(frozen=True)
class HedonicConfig:
    dataset: str
    seed: int = SEED
    min_apt_por_bairro: int = MIN_APT_POR_BAIRRO
    preco_m2_min: float = PRECO_M2_MIN
    preco_m2_max: float = PRECO_M2_MAX


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Distância grande-círculo em km."""
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = math.radians(lat2 - lat1), math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def dist_mar_km(lat: float, lng: float) -> float:
    return min(haversine_km(lat, lng, la, lo) for la, lo in COSTA)


def _preco(raw: dict) -> float | None:
    v = raw.get("price")
    try:
        v = float(v)
    except (TypeError, ValueError):
        return None
    return v if v > 0 else None


def _area(raw: dict) -> float | None:
    for k in ("area_min", "area_max"):
        try:
            v = float(raw.get(k))
        except (TypeError, ValueError):
            continue
        if v > 0:
            return v
    return None


def load_frames(path: Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    """(lotes, aptos) saneados de imoveis_jp.json. Lote exige lat/lng; apto só preço/área/bairro."""
    data = json.loads(path.read_text(encoding="utf-8"))
    lots, apts = [], []
    for r in data:
        preco, area, bairro = _preco(r), _area(r), (r.get("neighborhood") or "").strip()
        if not (preco and area and bairro):
            continue
        ppm = preco / area
        row = {"bairro": bairro, "preco_m2": ppm, "area_m2": area}
        tipo = r.get("type") or ""
        if tipo == "Lote/Terreno":
            lat, lng = r.get("lat"), r.get("lng")
            if lat is None or lng is None:
                continue
            if not (PRECO_M2_MIN <= ppm <= PRECO_M2_MAX and AREA_MIN <= area <= AREA_MAX):
                continue
            row.update(id=str(r.get("id")), lat=float(lat), lng=float(lng))
            lots.append(row)
        elif tipo == "Apartamento" and 800 <= ppm <= 30000:  # mesmo corte da view
            apts.append(row)
    lots_df = pd.DataFrame(lots).drop_duplicates(subset="id").reset_index(drop=True)
    return lots_df, pd.DataFrame(apts)


def apt_m2_por_bairro(apts: pd.DataFrame, min_n: int = MIN_APT_POR_BAIRRO) -> tuple[dict, float]:
    """{bairro: mediana R$/m² apto} (n>=min_n) + mediana global (fallback)."""
    g = apts.groupby("bairro")["preco_m2"]
    med = g.median()[g.count() >= min_n]
    return med.to_dict(), float(apts["preco_m2"].median())


def build_features(lots: pd.DataFrame, apt_med: dict, apt_global: float) -> pd.DataFrame:
    df = lots.copy()
    df["log_area"] = np.log(df["area_m2"])
    df["dist_mar_km"] = [dist_mar_km(la, lo) for la, lo in zip(df["lat"], df["lng"])]
    df["dist_manaira_km"] = [haversine_km(la, lo, *MANAIRA_SHOPPING) for la, lo in zip(df["lat"], df["lng"])]
    df["dist_centro_km"] = [haversine_km(la, lo, *CENTRO_LAGOA) for la, lo in zip(df["lat"], df["lng"])]
    df["log_apt_m2_bairro"] = np.log([apt_med.get(b, apt_global) for b in df["bairro"]])
    df["y"] = np.log(df["preco_m2"])
    return df


def fit_ols(df: pd.DataFrame):
    """OLS log-log com erros-padrão cluster-robust por bairro (problema de Moulton:
    erros correlacionados dentro do bairro + covariável de nível de bairro tornam
    HC1 otimista ~2-3x na variância; pontos/predições/ranking não mudam)."""
    import statsmodels.api as sm

    x = sm.add_constant(df[FEATURES], has_constant="add")
    return sm.OLS(df["y"], x).fit(
        cov_type="cluster", cov_kwds={"groups": df["bairro"]}
    )


def duan_smearing(residuos: np.ndarray) -> float:
    """Fator de retransformação de Duan: E[exp(ε)] estimado sem hipótese de normalidade."""
    return float(np.mean(np.exp(residuos)))


def spatial_cv(df: pd.DataFrame, n_splits: int = 5, seed: int = SEED) -> dict:
    """GroupKFold por bairro: modelo vs baseline (mediana do bairro no treino).

    Tudo — inclusive a mediana-baseline — é recalculado só com o fold de treino,
    p/ nenhuma informação do fold de teste vazar. Métricas em nível (R$/m²):
    MdAPE (mediana do erro % absoluto) e MAE-log.
    """
    from sklearn.model_selection import GroupKFold

    rng = np.random.default_rng(seed)  # GroupKFold é determinístico; seed p/ ordem estável
    _ = rng
    gkf = GroupKFold(n_splits=n_splits)
    rows = []
    for tr, te in gkf.split(df, groups=df["bairro"]):
        train, test = df.iloc[tr], df.iloc[te]
        res = fit_ols(train)
        import statsmodels.api as sm

        xte = sm.add_constant(test[FEATURES], has_constant="add")
        pred_log = res.predict(xte)
        pred = np.exp(pred_log)  # mediana condicional — é o que se compara com preço pedido

        med_bairro = train.groupby("bairro")["preco_m2"].median()
        base = np.array([med_bairro.get(b, train["preco_m2"].median()) for b in test["bairro"]])

        yv = test["preco_m2"].to_numpy()
        rows.append({
            "n_test": len(test),
            "mdape_modelo": float(np.median(np.abs(pred - yv) / yv)),
            "mdape_baseline": float(np.median(np.abs(base - yv) / yv)),
            "mae_log_modelo": float(np.mean(np.abs(pred_log - test["y"]))),
            "mae_log_baseline": float(np.mean(np.abs(np.log(base) - test["y"]))),
        })
    folds = pd.DataFrame(rows)
    return {
        "n_splits": n_splits,
        "mdape_modelo": float(folds["mdape_modelo"].mean()),
        "mdape_baseline": float(folds["mdape_baseline"].mean()),
        "mae_log_modelo": float(folds["mae_log_modelo"].mean()),
        "mae_log_baseline": float(folds["mae_log_baseline"].mean()),
        "folds": rows,
    }


def train(path: Path, out: Path) -> dict:
    lots, apts = load_frames(path)
    apt_med, apt_global = apt_m2_por_bairro(apts)
    df = build_features(lots, apt_med, apt_global)

    cv = spatial_cv(df)
    res = fit_ols(df)  # modelo final: todos os dados
    smear = duan_smearing(res.resid.to_numpy())

    artifact = {
        "modelo": "hedonic-ols-loglog",
        "versao": 1,
        "config": asdict(HedonicConfig(dataset=str(path))),
        "dados": {
            "n_lotes": int(len(df)),
            "n_aptos": int(len(apts)),
            "n_bairros": int(df["bairro"].nunique()),
            "sha256_12": hashlib.sha256(path.read_bytes()).hexdigest()[:12],
        },
        "coeficientes": {k: float(v) for k, v in res.params.items()},
        "erros_padrao_cluster_bairro": {k: float(v) for k, v in res.bse.items()},
        "p_valores": {k: float(v) for k, v in res.pvalues.items()},
        "r2": float(res.rsquared),
        "r2_ajustado": float(res.rsquared_adj),
        "smearing_duan": smear,
        "cv_espacial": cv,
        "apt_m2_bairro": {k: float(v) for k, v in apt_med.items()},
        "apt_m2_global": apt_global,
        "features": FEATURES,
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(artifact, ensure_ascii=False, indent=2), encoding="utf-8")
    return artifact


def predict_m2(artifact: dict, area_m2: float, lat: float, lng: float, bairro: str,
               esperanca: bool = False) -> float:
    """R$/m² previsto p/ um lote. esperanca=False → mediana condicional (ranking);
    True → valor esperado (multiplica pelo fator de Duan)."""
    c = artifact["coeficientes"]
    apt = artifact["apt_m2_bairro"].get(bairro, artifact["apt_m2_global"])
    x = {
        "log_area": math.log(area_m2),
        "dist_mar_km": dist_mar_km(lat, lng),
        "dist_manaira_km": haversine_km(lat, lng, *MANAIRA_SHOPPING),
        "dist_centro_km": haversine_km(lat, lng, *CENTRO_LAGOA),
        "log_apt_m2_bairro": math.log(apt),
    }
    log_pred = c["const"] + sum(c[f] * x[f] for f in artifact["features"])
    pred = math.exp(log_pred)
    return pred * artifact["smearing_duan"] if esperanca else pred


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Treina modelo hedônico de terreno (OLS log-log)")
    ap.add_argument("--file", default=str(DEFAULT_FILE))
    ap.add_argument("--out", default=str(DEFAULT_OUT))
    args = ap.parse_args(argv)

    art = train(Path(args.file), Path(args.out))
    print(f"n lotes={art['dados']['n_lotes']}  bairros={art['dados']['n_bairros']}  "
          f"R2={art['r2']:.3f} (aj {art['r2_ajustado']:.3f})  smearing={art['smearing_duan']:.3f}")
    print("coeficientes (log-log -> elasticidades):")
    for k, v in art["coeficientes"].items():
        p = art["p_valores"][k]
        print(f"  {k:<20} {v:>9.4f}   p={p:.4f}")
    cv = art["cv_espacial"]
    print(f"\nCV espacial (GroupKFold bairro, {cv['n_splits']} folds) — erro em R$/m²:")
    print(f"  MdAPE modelo   {cv['mdape_modelo']:.1%}   baseline(mediana bairro) {cv['mdape_baseline']:.1%}")
    print(f"  MAE-log modelo {cv['mae_log_modelo']:.3f}   baseline {cv['mae_log_baseline']:.3f}")
    print(f"\nartefato: {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
