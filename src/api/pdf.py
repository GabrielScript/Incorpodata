"""PDF da ficha do lote (ReportLab, puro Python — sem libs de sistema, roda no Cloud Run).

Recebe um LotFicha (pydantic) e devolve os bytes do PDF. Foco: 1 página levável ao comitê,
com o VGV em destaque (envelope LUOS × R$/m² do bairro) e as premissas explícitas.
"""
from __future__ import annotations

from io import BytesIO

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    HRFlowable,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from src.api.schemas import LotFicha

_INK = colors.HexColor("#0f172a")
_MUTED = colors.HexColor("#64748b")
_ACCENT = colors.HexColor("#0e7490")
_LINE = colors.HexColor("#e2e8f0")


def _brl(v: float | None) -> str:
    if v is None:
        return "—"
    s = f"{v:,.0f}".replace(",", ".")
    return f"R$ {s}"


def _m2(v: float | None) -> str:
    if v is None:
        return "—"
    return f"{v:,.0f}".replace(",", ".") + " m²"


def _pct(v: float | None) -> str:
    return "—" if v is None else f"{v:,.0f}".replace(",", ".") + "%"


def _styles() -> dict[str, ParagraphStyle]:
    base = getSampleStyleSheet()
    return {
        "brand": ParagraphStyle("brand", parent=base["Normal"], fontName="Helvetica-Bold",
                                fontSize=16, leading=19, textColor=_ACCENT, spaceAfter=6),
        "h1": ParagraphStyle("h1", parent=base["Normal"], fontName="Helvetica-Bold",
                             fontSize=15, leading=18, textColor=_INK, spaceBefore=0, spaceAfter=4),
        "sub": ParagraphStyle("sub", parent=base["Normal"], fontSize=9.5, leading=12, textColor=_MUTED),
        "section": ParagraphStyle("section", parent=base["Normal"], fontName="Helvetica-Bold",
                                  fontSize=10.5, textColor=_INK, spaceBefore=8, spaceAfter=4),
        "vgvbig": ParagraphStyle("vgvbig", parent=base["Normal"], fontName="Helvetica-Bold",
                                 fontSize=20, textColor=_ACCENT),
        "vgvk": ParagraphStyle("vgvk", parent=base["Normal"], fontSize=8, textColor=_MUTED),
        "note": ParagraphStyle("note", parent=base["Normal"], fontSize=8, textColor=_MUTED,
                               leading=11),
        "foot": ParagraphStyle("foot", parent=base["Normal"], fontSize=7.5, textColor=_MUTED),
    }


def _kv_table(rows: list[tuple[str, str]]) -> Table:
    t = Table([[k, v] for k, v in rows], colWidths=[55 * mm, 105 * mm])
    t.setStyle(TableStyle([
        ("FONT", (0, 0), (0, -1), "Helvetica", 9),
        ("FONT", (1, 0), (1, -1), "Helvetica-Bold", 9),
        ("TEXTCOLOR", (0, 0), (0, -1), _MUTED),
        ("TEXTCOLOR", (1, 0), (1, -1), _INK),
        ("LINEBELOW", (0, 0), (-1, -2), 0.4, _LINE),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING", (0, 0), (0, -1), 0),
    ]))
    return t


def build_ficha_pdf(ficha: LotFicha) -> bytes:
    """Monta o PDF da ficha e devolve os bytes (começa com b'%PDF-')."""
    buf = BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4, title=f"Ficha lote {ficha.id} — IncorpoData",
        leftMargin=18 * mm, rightMargin=18 * mm, topMargin=16 * mm, bottomMargin=14 * mm,
    )
    s = _styles()
    flow: list = []

    flow.append(Paragraph("IncorpoData", s["brand"]))
    flow.append(Paragraph(ficha.logradouro or f"Lote {ficha.id}", s["h1"]))
    flow.append(Paragraph(
        f"{ficha.bairro or '—'} · {_m2(ficha.area_geom_m2)} · "
        f"{(ficha.viability.sigla if ficha.viability else None) or 's/ zona'} · lote #{ficha.id}",
        s["sub"],
    ))
    flow.append(Spacer(1, 6))
    flow.append(HRFlowable(width="100%", thickness=1, color=_LINE))

    # ───── Gleba/ZEPA: avisa e suprime VGV ─────
    if ficha.geometria_suspeita:
        flow.append(Paragraph("⚠ VGV não se aplica", s["section"]))
        flow.append(Paragraph(
            ficha.geometria_aviso
            or "Área acima do padrão de lote urbano (gleba/ZEPA). VGV de prédio único não se aplica.",
            s["vgvk"],
        ))
        flow.append(Spacer(1, 8))

    # ───── VGV em destaque ─────
    if ficha.vgv is not None:
        v = ficha.vgv
        flow.append(Paragraph("VGV potencial", s["section"]))
        head = Table(
            [[Paragraph(_brl(v.vgv_por_pavimento), s["vgvbig"]),
              Paragraph(_brl(v.vgv_total), s["vgvbig"])],
             [Paragraph("VGV por pavimento (independe de altura)", s["vgvk"]),
              Paragraph(f"VGV total — premissa {v.pavimentos} pavimentos", s["vgvk"])]],
            colWidths=[80 * mm, 80 * mm],
        )
        head.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#ecfeff")),
            ("BOX", (0, 0), (-1, -1), 0.5, _LINE),
            ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.white),
            ("TOPPADDING", (0, 0), (-1, -1), 8),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
            ("LEFTPADDING", (0, 0), (-1, -1), 10),
        ]))
        flow.append(head)
        flow.append(Spacer(1, 4))
        origem = "raio do lote" if v.fonte_preco == "raio" else "bairro"
        if v.preco_m2_q1 is not None and v.preco_m2_q3 is not None:
            preco_val = (
                f"{_brl(v.preco_m2_venda)}/m²  ·  Q1–Q3 "
                f"{_brl(v.preco_m2_q1)}–{_brl(v.preco_m2_q3)}  ·  n={v.n_comps}"
            )
        else:
            preco_val = f"{_brl(v.preco_m2_venda)}/m²  ·  n={v.n_comps} comps"
        vgv_rows = [(f"R$/m² de venda ({origem})", preco_val)]
        if v.vgv_por_pavimento_min is not None and v.vgv_por_pavimento_max is not None:
            vgv_rows.append((
                "Faixa VGV/pavimento (Q1–Q3)",
                f"{_brl(v.vgv_por_pavimento_min)} – {_brl(v.vgv_por_pavimento_max)}",
            ))
        vgv_rows += [
            ("Área privativa / pavimento", _m2(v.area_privativa_pavto_m2)),
            ("Área privativa total (premissa)", _m2(v.area_privativa_total_m2)),
            ("Eficiência adotada", _pct(v.eficiencia * 100)),
        ]
        flow.append(_kv_table(vgv_rows))
        flow.append(Paragraph(f"Premissas: {v.premissas}", s["note"]))

    # ───── Valor residual (quanto pagar) em destaque ─────
    if ficha.residual is not None:
        r = ficha.residual
        flow.append(Paragraph("Quanto pagar (valor residual)", s["section"]))
        if r.residual_total > 0:
            big = f"até {_brl(r.residual_total)}"
            sub = f"máximo p/ margem-alvo de {_pct(r.margem_alvo * 100)}"
            if r.terreno_pct_vgv is not None:
                sub += f"  ·  {_pct(r.terreno_pct_vgv * 100)} do VGV"
        else:
            big = "inviável às premissas"
            sub = "custo de obra + margem-alvo superam o VGV"
        head = Table([[Paragraph(big, s["vgvbig"])], [Paragraph(sub, s["vgvk"])]],
                     colWidths=[160 * mm])
        head.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#f1f5f9")),
            ("BOX", (0, 0), (-1, -1), 0.5, _LINE),
            ("TOPPADDING", (0, 0), (-1, -1), 8),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
            ("LEFTPADDING", (0, 0), (-1, -1), 10),
        ]))
        flow.append(head)
        flow.append(Spacer(1, 4))
        res_rows = [("Máximo por pavimento", _brl(r.residual_por_pavimento))]
        if r.residual_total_min is not None and r.residual_total_max is not None:
            res_rows.append((
                "Faixa do residual (Q1–Q3)",
                f"{_brl(r.residual_total_min)} – {_brl(r.residual_total_max)}",
            ))
        res_rows.append(("Custo de obra (premissa)", f"{_brl(r.custo_obra_m2)}/m²"))
        if r.gap_pct is not None:
            estado = "cabe no bolso" if r.cabe_no_bolso else "acima do máximo"
            res_rows.append((
                "Barganha vs preço pedido",
                f"{estado}  ·  {_pct(abs(r.gap_pct) * 100)} "
                + ("de folga" if r.cabe_no_bolso else "acima"),
            ))
        flow.append(_kv_table(res_rows))
        flow.append(Paragraph(f"Premissas: {r.premissas}", s["note"]))

    # ───── Envelope LUOS ─────
    if ficha.viability is not None:
        vb = ficha.viability
        flow.append(Paragraph("O que cabe (LUOS LC 166/2024)", s["section"]))
        flow.append(_kv_table([
            ("Zona", f"{vb.sigla or '—'}" + (f" · {vb.nome_zona}" if vb.nome_zona else "")),
            ("Projeção no térreo (TO)", f"{_m2(vb.area_projecao_max_m2)} ({_pct(vb.to_max_pct)})"),
            ("Área permeável mín (TAP)", f"{_m2(vb.area_permeavel_min_m2)} ({_pct(vb.tap_min_pct)})"),
            ("Recuo frontal", f"{vb.recuo_frontal_m} m" if vb.recuo_frontal_m is not None else "—"),
            ("Usos", vb.usos_obs or "—"),
        ]))

    # ───── Altura + terreno ─────
    flow.append(Paragraph("Altura e terreno", s["section"]))
    rows = [
        ("Altura permitida", ficha.restricao.altura_label),
        ("Faixa da orla", ficha.restricao.faixa_orla or "não"),
        ("IPHAEP (centro histórico)", "sim" if ficha.restricao.em_centro_historico else "não"),
        ("Área (cadastro)", _m2(ficha.area_cad_m2)),
        ("Área (geometria)", _m2(ficha.area_geom_m2)),
        ("Inscrição cadastral", ficha.inscricao or "—"),
    ]
    flow.append(_kv_table(rows))

    if ficha.listing is not None:
        flow.append(Paragraph("Mercado (anúncio casado)", s["section"]))
        flow.append(_kv_table([
            ("À venda por", f"{_brl(ficha.listing.preco)} · {ficha.listing.fonte}"),
            ("R$/m² do terreno", f"{_brl(ficha.listing.preco_m2)}/m²"),
        ]))

    flow.append(Spacer(1, 10))
    flow.append(HRFlowable(width="100%", thickness=0.5, color=_LINE))
    flow.append(Paragraph(
        "IncorpoData · viabilidade de terrenos · João Pessoa/PB. VGV e valor residual "
        "preliminares (método involutivo) — premissas de pavimentos/eficiência/custo de obra "
        "ajustáveis pelo incorporador. Não substitui projeto nem avaliação.",
        s["foot"],
    ))

    doc.build(flow)
    return buf.getvalue()
