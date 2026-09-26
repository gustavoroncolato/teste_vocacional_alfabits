"""Login do painel admin: sessão por cookie + bloqueio exponencial por tentativa errada.

Errou a senha: espera 3 min. Errou de novo: 9 min, depois 27, 81... (x3 a cada erro, até 24 h).
Tudo em memória: o app roda em 1 processo só (reiniciar o servidor zera sessões e bloqueios).
"""
from __future__ import annotations

import secrets
import time

from fastapi import Request

from .config import settings

BASE_WAIT = 180  # 3 minutos
FACTOR = 3
MAX_WAIT = 24 * 3600
SESSION_TTL = 12 * 3600
COOKIE = "tv_admin"

_sessions: dict[str, float] = {}  # token -> expira em
_fails: dict[str, dict] = {}  # ip -> {"n": erros seguidos, "until": bloqueado até}


def client_ip(request: Request) -> str:
    # No Railway o proxy informa o IP real em X-Real-IP / X-Forwarded-For (último da lista = quem chegou no proxy).
    real = request.headers.get("x-real-ip")
    if real:
        return real.strip()
    fwd = request.headers.get("x-forwarded-for")
    if fwd:
        return fwd.split(",")[-1].strip()
    return request.client.host if request.client else "?"


def wait_left(ip: str) -> int:
    """Segundos que esse IP ainda precisa esperar (0 = pode tentar)."""
    f = _fails.get(ip)
    return max(0, int(f["until"] - time.time() + 0.999)) if f else 0


def check_login(ip: str, usuario: str, senha: str) -> tuple[bool, int]:
    """Retorna (ok, segundos de espera). Não deve ser chamada durante o bloqueio."""
    if not settings.admin_user or not settings.admin_password:
        return False, 0
    ok = secrets.compare_digest(usuario.encode(), settings.admin_user.encode()) & \
        secrets.compare_digest(senha.encode(), settings.admin_password.encode())
    if ok:
        _fails.pop(ip, None)
        return True, 0
    f = _fails.setdefault(ip, {"n": 0, "until": 0.0})
    f["n"] += 1
    wait = min(BASE_WAIT * FACTOR ** (f["n"] - 1), MAX_WAIT)
    f["until"] = time.time() + wait
    return False, wait


def new_session() -> str:
    now = time.time()
    for t in [t for t, exp in _sessions.items() if exp < now]:  # limpa as vencidas
        _sessions.pop(t, None)
    token = secrets.token_urlsafe(32)
    _sessions[token] = now + SESSION_TTL
    return token


def valid_session(request: Request) -> bool:
    token = request.cookies.get(COOKIE)
    exp = _sessions.get(token or "")
    return bool(exp and exp > time.time())


def end_session(request: Request) -> None:
    _sessions.pop(request.cookies.get(COOKIE) or "", None)


def is_https(request: Request) -> bool:
    return request.url.scheme == "https" or request.headers.get("x-forwarded-proto", "").startswith("https")


def reset() -> None:
    """Para os testes."""
    _sessions.clear()
    _fails.clear()
