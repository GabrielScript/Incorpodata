"""Landbank: salvar/listar/mover/remover lotes do usuário. Tudo escopado por user_id."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import text
from sqlalchemy.engine import Connection

from src.api.auth import get_current_user
from src.api.db import get_conn
from src.api.schemas import LandbankIn, LandbankItem, LandbankPatch

router = APIRouter(prefix="/api/landbank", tags=["landbank"])

ESTAGIOS = {"triagem", "analise", "opcao", "due_diligence", "adquirido", "descartado"}

_SELECT = """
    SELECT li.id, li.lote_id, li.estagio::text AS estagio, li.notas,
           l.logradouro, l.bairro, l.area_geom_m2
    FROM app.landbank_items li
    LEFT JOIN geo.lotes l ON l.id = li.lote_id
"""


@router.get("", response_model=list[LandbankItem])
def list_items(user_id: int = Depends(get_current_user), conn: Connection = Depends(get_conn)) -> list[LandbankItem]:
    rows = conn.execute(
        text(_SELECT + " WHERE li.user_id = :u ORDER BY li.atualizado_em DESC"), {"u": user_id}
    ).mappings().all()
    return [LandbankItem(**r) for r in rows]


@router.post("", response_model=LandbankItem, status_code=status.HTTP_201_CREATED)
def add_item(
    body: LandbankIn, user_id: int = Depends(get_current_user), conn: Connection = Depends(get_conn)
) -> LandbankItem:
    conn.execute(
        text(
            "INSERT INTO app.landbank_items (user_id, lote_id) VALUES (:u, :l) "
            "ON CONFLICT (user_id, lote_id) DO NOTHING"
        ),
        {"u": user_id, "l": body.lote_id},
    )
    conn.commit()
    row = conn.execute(
        text(_SELECT + " WHERE li.user_id = :u AND li.lote_id = :l"),
        {"u": user_id, "l": body.lote_id},
    ).mappings().first()
    if row is None:
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, "falha ao salvar")
    return LandbankItem(**row)


@router.patch("/{item_id}", response_model=LandbankItem)
def patch_item(
    item_id: int,
    body: LandbankPatch,
    user_id: int = Depends(get_current_user),
    conn: Connection = Depends(get_conn),
) -> LandbankItem:
    if body.estagio is not None and body.estagio not in ESTAGIOS:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"estágio inválido; use {sorted(ESTAGIOS)}")
    # confirma posse → bloqueia escalonamento horizontal
    owner = conn.execute(
        text("SELECT 1 FROM app.landbank_items WHERE id = :i AND user_id = :u"),
        {"i": item_id, "u": user_id},
    ).first()
    if owner is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "item não encontrado")
    conn.execute(
        text(
            "UPDATE app.landbank_items "
            "SET estagio = COALESCE(CAST(:e AS app.estagio_lote), estagio), "
            "    notas = COALESCE(:n, notas), atualizado_em = now() "
            "WHERE id = :i AND user_id = :u"
        ),
        {"e": body.estagio, "n": body.notas, "i": item_id, "u": user_id},
    )
    conn.commit()
    row = conn.execute(text(_SELECT + " WHERE li.id = :i"), {"i": item_id}).mappings().first()
    return LandbankItem(**row)


@router.delete("/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_item(
    item_id: int, user_id: int = Depends(get_current_user), conn: Connection = Depends(get_conn)
) -> None:
    res = conn.execute(
        text("DELETE FROM app.landbank_items WHERE id = :i AND user_id = :u"),
        {"i": item_id, "u": user_id},
    )
    conn.commit()
    if res.rowcount == 0:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "item não encontrado")
