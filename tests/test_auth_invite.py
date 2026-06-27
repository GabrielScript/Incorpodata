"""Registro por convite (lógica pura, sem DB/HTTP) — fecha o auto-cadastro."""
from __future__ import annotations

from src.api.security import convite_valido, registro_aberto


def test_sem_env_registro_fechado(monkeypatch):
    monkeypatch.delenv("REGISTER_INVITE_CODE", raising=False)
    assert registro_aberto() is False
    assert convite_valido("qualquer") is False
    assert convite_valido(None) is False


def test_env_vazio_registro_fechado(monkeypatch):
    monkeypatch.setenv("REGISTER_INVITE_CODE", "   ")
    assert registro_aberto() is False
    assert convite_valido("x") is False


def test_codigo_unico(monkeypatch):
    monkeypatch.setenv("REGISTER_INVITE_CODE", "ALFA-123")
    assert registro_aberto() is True
    assert convite_valido("ALFA-123") is True
    assert convite_valido("  ALFA-123  ") is True   # tolera espaços
    assert convite_valido("alfa-123") is False      # case-sensitive
    assert convite_valido("ALFA-124") is False
    assert convite_valido("") is False
    assert convite_valido(None) is False


def test_multiplos_codigos(monkeypatch):
    # Códigos por cliente: emitir/revogar sem afetar os outros.
    monkeypatch.setenv("REGISTER_INVITE_CODE", "CONSTR-A, CONSTR-B ,CONSTR-C")
    assert registro_aberto() is True
    assert convite_valido("CONSTR-A") is True
    assert convite_valido("CONSTR-B") is True
    assert convite_valido("CONSTR-C") is True
    assert convite_valido("CONSTR-D") is False
