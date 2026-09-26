"""Envio do resultado pelo WhatsApp usando WAHA (WhatsApp HTTP API).

Endpoints usados (WAHA padrão):
  GET  /api/contacts/check-exists?phone=...&session=...   -> confere se o número tem WhatsApp
  POST /api/startTyping / /api/stopTyping                  -> "digitando..." (mais natural, reduz risco de ban)
  POST /api/sendText  {session, chatId, text}              -> envia a mensagem
Sem WAHA_URL configurada: modo console (a mensagem só aparece no log) - útil para testes locais.
"""
from __future__ import annotations

import asyncio
import logging
import random

import httpx

from .config import settings

log = logging.getLogger("whatsapp")
_client: httpx.AsyncClient | None = None


class TemporaryError(Exception):
    """Falha que vale tentar de novo (rede, 429, 5xx)."""


async def startup() -> None:
    global _client
    if _client is None and settings.waha_url:
        headers = {"X-Api-Key": settings.waha_api_key} if settings.waha_api_key else {}
        _client = httpx.AsyncClient(base_url=settings.waha_url, headers=headers, timeout=20)


async def shutdown() -> None:
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None


def mask_phone(phone_digits: str) -> str:
    d = phone_digits[2:] if phone_digits.startswith("55") else phone_digits
    return f"({d[:2]}) {'9' if len(d) == 11 else ''}****-{d[-4:]}"


async def _resolve_chat_id(phone: str) -> str | None:
    """Retorna o chatId correto (trata o 9º dígito) ou None se o número não tem WhatsApp."""
    default = f"{phone}@c.us"
    if not settings.waha_check_number:
        return default
    try:
        r = await _client.get("/api/contacts/check-exists", params={"phone": phone, "session": settings.waha_session})
    except httpx.HTTPError as exc:
        raise TemporaryError(f"check-exists: {exc}") from exc
    if r.status_code == 429 or r.status_code >= 500:
        raise TemporaryError(f"check-exists HTTP {r.status_code}")
    if r.status_code >= 400:  # versão do WAHA sem esse endpoint: segue com o padrão
        return default
    data = r.json()
    if data.get("numberExists") is False:
        return None
    return data.get("chatId") or default


async def _typing(chat_id: str) -> None:
    body = {"session": settings.waha_session, "chatId": chat_id}
    try:
        await _client.post("/api/startTyping", json=body)
        await asyncio.sleep(random.uniform(1.5, 3.0))
        await _client.post("/api/stopTyping", json=body)
    except httpx.HTTPError:
        pass  # "digitando" é só cosmético


async def send_result(phone: str, text: str) -> str:
    """Envia o texto. Retorna 'enviado', 'console', 'sem_whatsapp' ou 'erro: ...' (definitivo).
    Lança TemporaryError quando vale tentar de novo."""
    if not settings.waha_url:
        log.info("[WhatsApp console] para %s:\n%s", phone, text)
        return "console"
    if _client is None:
        await startup()

    chat_id = await _resolve_chat_id(phone)
    if chat_id is None:
        return "sem_whatsapp"
    if settings.waha_typing:
        await _typing(chat_id)
    try:
        r = await _client.post(
            "/api/sendText",
            json={"session": settings.waha_session, "chatId": chat_id, "text": text, "linkPreview": False},
        )
    except httpx.HTTPError as exc:
        raise TemporaryError(f"sendText: {exc}") from exc
    if r.status_code < 300:
        return "enviado"
    if r.status_code == 429 or r.status_code >= 500:
        raise TemporaryError(f"sendText HTTP {r.status_code}: {r.text[:200]}")
    log.error("WAHA recusou (%s): %s", r.status_code, r.text[:300])
    return f"erro: HTTP {r.status_code}"
