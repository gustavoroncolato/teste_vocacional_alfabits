"""WAHA falso para testes locais (não envia nada de verdade).

Uso:  uv run uvicorn scripts.fake_waha:app --port 3000
Depois, no .env do app:  WAHA_URL=http://127.0.0.1:3000
Ver mensagens recebidas: http://127.0.0.1:3000/_messages

FAKE_WAHA_FAIL_RATE=0.1 -> 10% dos envios retornam 500 (testa o retry)
FAKE_WAHA_DELAY=0.3     -> latência simulada por chamada (s)
"""
import asyncio
import os
import random
import time

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

app = FastAPI(title="Fake WAHA")
FAIL = float(os.getenv("FAKE_WAHA_FAIL_RATE", "0"))
DELAY = float(os.getenv("FAKE_WAHA_DELAY", "0.2"))
MESSAGES: list[dict] = []
CALLS = {"check": 0, "typing": 0, "send": 0, "fail": 0}


@app.get("/api/contacts/check-exists")
async def check(phone: str, session: str = "default"):
    CALLS["check"] += 1
    await asyncio.sleep(DELAY)
    if phone.endswith("0000"):  # convenção de teste: final 0000 = sem WhatsApp
        return {"numberExists": False}
    return {"numberExists": True, "chatId": f"{phone}@c.us"}


@app.post("/api/startTyping")
@app.post("/api/stopTyping")
async def typing(_: Request):
    CALLS["typing"] += 1
    return {"ok": True}


@app.post("/api/sendText")
async def send(req: Request):
    body = await req.json()
    CALLS["send"] += 1
    await asyncio.sleep(DELAY)
    if random.random() < FAIL:
        CALLS["fail"] += 1
        return JSONResponse({"error": "falha simulada"}, status_code=500)
    MESSAGES.append({"t": time.time(), "chatId": body["chatId"], "text": body["text"]})
    print(f"\n--- mensagem para {body['chatId']} ---\n{body['text']}\n", flush=True)
    return {"id": f"fake_{len(MESSAGES)}"}


@app.get("/_messages")
async def messages():
    return {"total": len(MESSAGES), "calls": CALLS, "ultimas": MESSAGES[-5:]}
