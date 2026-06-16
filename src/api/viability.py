"""Lógica pura da ficha de viabilidade (sem DB) — o moat, por isso testada.

Em João Pessoa a altura/nº de pavimentos é ESPACIAL (faixa de 500m da orla + IPHAEP +
barreira do Cabo Branco), não vem da zona. Aqui traduzimos as flags por lote
(geo.lote_restricao) num rótulo legível. Ordem = mais restritivo primeiro.
"""
from __future__ import annotations


def altura_label(
    faixa_orla: str | None,
    em_centro_historico: bool,
    em_barreira: bool,
    altura_livre: bool | None,
) -> str:
    """Rótulo humano da restrição de altura do lote."""
    if em_centro_historico:
        return "Restrito — IPHAEP (centro histórico)"
    if em_barreira:
        return "Restrito — barreira do Cabo Branco"
    if faixa_orla:
        return f"Faixa da orla ({faixa_orla}) — altura escalonada"
    if altura_livre:
        return "Livre — limitada pelos recuos"
    return "A confirmar"
