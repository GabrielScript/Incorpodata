"""Guarda da allowlist de ordenação: o pattern do Query é derivado de _ORDER, então
toda chave válida casa e qualquer valor fora dela é recusado (nada injeta no SQL)."""
import re

from src.api.lots import _ORDER, _SORT_PATTERN


def test_pattern_aceita_toda_chave():
    for key in _ORDER:
        assert re.match(_SORT_PATTERN, key), f"{key} deveria ser aceito"


def test_pattern_recusa_valor_estranho():
    for ruim in ["", "drop", "l.id", "area", "preco; --", "PROJ_ASC"]:
        assert re.match(_SORT_PATTERN, ruim) is None, f"{ruim} não deveria passar"


def test_default_e_variaveis_importantes_presentes():
    assert _ORDER["none"] == "l.id"
    for v in ("area", "proj", "preco", "preco_m2"):
        assert f"{v}_asc" in _ORDER and f"{v}_desc" in _ORDER


def test_toda_ordenacao_desempata_por_id():
    # menos a 'none' (que já é só l.id), toda ordenação termina em ", l.id"
    for key, expr in _ORDER.items():
        if key == "none":
            continue
        assert expr.endswith(", l.id"), f"{key} sem desempate estável"
