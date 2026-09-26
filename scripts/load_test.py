"""Simula o pico: N pessoas abrindo o site e fazendo o teste completo.

Uso:
    uv run python scripts/load_test.py --url http://127.0.0.1:8000 --users 400 --ramp 120

--ramp: em quantos segundos as N pessoas começam (ex.: 600 = 10 minutos).
--think: segundos "pensando" entre as etapas (0 = o mais rápido possível, pior caso).
"""
from __future__ import annotations

import argparse
import asyncio
import random
import statistics
import time
from collections import Counter, defaultdict

import httpx

timings: dict[str, list[float]] = defaultdict(list)
errors: dict[str, int] = defaultdict(int)
espera: dict[str, list[float]] = defaultdict(list)
fontes: Counter = Counter()


async def timed(name: str, coro):
    t = time.perf_counter()
    try:
        r = await coro
        timings[name].append(time.perf_counter() - t)
        if r.status_code >= 400:
            errors[f"{name} HTTP {r.status_code}"] += 1
            return None
        return r
    except Exception as exc:  # noqa: BLE001
        errors[f"{name} {type(exc).__name__}"] += 1
        return None


async def user(client: httpx.AsyncClient, n: int, delay: float, think: float):
    await asyncio.sleep(delay)
    if not await timed("GET /", client.get("/")):
        return
    await timed("GET app.js", client.get("/static/app.js?v=3"))
    await asyncio.sleep(think)
    perfil = {
        "nome": f"Aluno Teste {n}", "telefone": f"(18) 9{random.randint(1000, 9999)}-{random.randint(1000, 9999)}",
        "nascimento": "2008-03-15", "cidade": "Pirapozinho", "escola": "Escola Teste", "aceita_lgpd": True, "aceita_contato": random.random() < 0.6,
    }
    r = await timed("POST iniciar", client.post("/api/iniciar", json=perfil))
    if not r:
        return
    d = r.json()
    await asyncio.sleep(think * 3)
    r = await timed("POST fase2", client.post("/api/fase2", json={"id": d["id"], "respostas": {q["id"]: random.randint(1, 5) for q in d["perguntas"]}}))
    if not r:
        return
    f2 = r.json()
    await asyncio.sleep(think * 3)
    body = {"id": d["id"], "respostas": {q["id"]: random.randint(1, 5) for q in f2["perguntas"]},
            "abertas": {"ab_livre": "jogar bola e desenhar", "ab_sonho": "ainda não sei, gosto de computador"}}
    r = await timed("POST finalizar", client.post("/api/finalizar", json=body))
    if not r:
        return
    token = r.json()["token"]
    # a pessoa é levada para a página de resultado, que consulta a API até ficar pronta
    t0 = time.perf_counter()
    await timed("GET /r/token", client.get(f"/r/{token}"))
    got_courses = False
    while time.perf_counter() - t0 < 300:
        rr = await timed("GET resultado", client.get(f"/api/resultado/{token}"))
        if rr:
            dd = rr.json()
            if dd["cursos"] and not got_courses:
                got_courses = True
                espera["3 cursos na tela"].append(time.perf_counter() - t0)
            if dd["status"] == "pronto":
                espera["página completa"].append(time.perf_counter() - t0)
                fontes.update(c["detalhe"]["fonte"] for c in dd["cursos"])
                return
        await asyncio.sleep(1.5)
    errors["resultado não ficou pronto em 5 min"] += 1


def pct(vals: list[float], p: float) -> float:
    vals = sorted(vals)
    return vals[min(len(vals) - 1, int(len(vals) * p))]


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://127.0.0.1:8000")
    ap.add_argument("--users", type=int, default=400)
    ap.add_argument("--ramp", type=float, default=60)
    ap.add_argument("--think", type=float, default=0.5)
    a = ap.parse_args()

    limits = httpx.Limits(max_connections=500, max_keepalive_connections=100)
    async with httpx.AsyncClient(base_url=a.url, timeout=60, limits=limits) as client:
        t0 = time.perf_counter()
        await asyncio.gather(*(user(client, i, random.uniform(0, a.ramp), a.think) for i in range(a.users)))
        total = time.perf_counter() - t0

    print(f"\n{a.users} usuários, rampa {a.ramp:.0f}s, duração total {total:.1f}s")
    print(f"{'requisição':<18}{'n':>6}{'p50 (s)':>10}{'p95 (s)':>10}{'max (s)':>10}")
    for name, vals in timings.items():
        print(f"{name:<18}{len(vals):>6}{statistics.median(vals):>10.3f}{pct(vals, .95):>10.3f}{max(vals):>10.3f}")
    print("\nespera na página de resultado (a partir do fim do teste):")
    for name, vals in espera.items():
        print(f"  {name:<18}{len(vals):>6}  p50 {statistics.median(vals):5.1f}s  p95 {pct(vals, .95):5.1f}s  max {max(vals):5.1f}s")
    print("conteúdo dos cursos:", dict(fontes))
    print("erros:", dict(errors) or "nenhum")


if __name__ == "__main__":
    asyncio.run(main())
