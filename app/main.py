"""API do Teste Vocacional (FastAPI) + frontend PWA estático."""
from __future__ import annotations

import csv
import io
import logging
import re
import secrets
import uuid
from urllib.parse import quote
from contextlib import asynccontextmanager
from datetime import date
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, StrictInt, field_validator

from . import admin_auth, db, llm
from .config import settings
from .questions import (DIMENSIONS, MIN_ABERTA, OPEN_IDS, OPEN_QUESTIONS, PHASE1, PHASE1_IDS, PHASE2, QUESTION_INDEX,
                        SCALE)
from .scoring import compute_profile, phase2_questions
from .worker import age_from, pipeline

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
STATIC = Path(__file__).parent / "static"


@asynccontextmanager
async def lifespan(_: FastAPI):
    db.init()
    await llm.startup()
    if settings.start_workers:
        await pipeline.start()
    yield
    await pipeline.stop()
    await llm.shutdown()


app = FastAPI(title="Teste Vocacional", lifespan=lifespan, docs_url="/api/docs", redoc_url=None)
app.add_middleware(GZipMiddleware, minimum_size=800)


# ---------------------------------------------------------------- modelos
def normalize_phone(raw: str) -> str:
    digits = re.sub(r"\D", "", raw or "")
    if digits.startswith("55") and len(digits) in (12, 13):
        digits = digits[2:]
    if len(digits) not in (10, 11) or not (11 <= int(digits[:2]) <= 99):
        raise ValueError("número inválido. Use DDD + número, ex.: (18) 99999-9999")
    if len(digits) == 11 and digits[2] != "9":
        raise ValueError("celular inválido: deve começar com 9 depois do DDD")
    return "55" + digits


class Perfil(BaseModel):
    nome: str = Field(min_length=2, max_length=80)
    telefone: str = Field(max_length=25)
    nascimento: date
    cidade: str = Field(min_length=2, max_length=80)
    escola: str = Field(min_length=2, max_length=120)
    serie: str | None = Field(default=None, max_length=60)
    aceita_lgpd: bool
    aceita_contato: bool = False

    @field_validator("nome", "cidade", "escola")
    @classmethod
    def _strip(cls, v: str) -> str:
        v = re.sub(r"\s+", " ", v).strip()
        if len(v) < 2:
            raise ValueError("preencha corretamente")
        return v

    @field_validator("telefone")
    @classmethod
    def _phone(cls, v: str) -> str:
        return normalize_phone(v)

    @field_validator("nascimento")
    @classmethod
    def _nasc(cls, v: date) -> date:
        if not 8 <= age_from(v) <= 100:
            raise ValueError("data inválida")
        return v

    @field_validator("aceita_lgpd")
    @classmethod
    def _lgpd(cls, v: bool) -> bool:
        if not v:
            raise ValueError("é preciso aceitar para fazer o teste")
        return v


Respostas = dict[str, StrictInt]


def _check_answers(respostas: Respostas, expected: set[str]) -> None:
    if set(respostas) != expected:
        raise HTTPException(422, "Responda todas as perguntas")
    if any(not isinstance(v, int) or isinstance(v, bool) or not 1 <= v <= 5 for v in respostas.values()):
        raise HTTPException(422, "Respostas devem ser de 1 a 5")


class Fase2In(BaseModel):
    id: str = Field(max_length=40)
    respostas: Respostas


class FinalizarIn(BaseModel):
    id: str = Field(max_length=40)
    respostas: Respostas
    abertas: dict[str, str] = Field(default_factory=dict)

    @field_validator("abertas")
    @classmethod
    def _abertas(cls, v: dict[str, str]) -> dict[str, str]:
        return {k: re.sub(r"\s+", " ", s or "").strip()[:400] for k, s in v.items() if k in OPEN_IDS}


def _check_open(abertas: dict[str, str]) -> None:
    """Cada resposta aberta precisa de um mínimo de texto de verdade (não vale "aaaaaaaaaaaaaaa")."""
    for q in OPEN_QUESTIONS:
        txt = abertas.get(q["id"], "")
        letras = {c for c in txt.lower() if c.isalpha()}
        if len(txt) < MIN_ABERTA or len(letras) < 5:
            raise HTTPException(422, f"Escreva um pouco mais em: \"{q['texto']}\" (mínimo {MIN_ABERTA} caracteres).")


# ---------------------------------------------------------------- API
@app.get("/health")
async def health():
    return {"ok": True}


@app.get("/api/config")
async def public_config():
    return {"org": settings.org_name}


@app.post("/api/iniciar")
async def iniciar(p: Perfil):
    pid = uuid.uuid4().hex
    data = p.model_dump()
    data["nascimento"] = p.nascimento.isoformat()
    await run_in_threadpool(db.create_participant, pid, data)
    return {"id": pid, "escala": SCALE, "perguntas": [{"id": q["id"], "texto": q["texto"]} for q in PHASE1]}


async def _load(pid: str) -> dict:
    part = await run_in_threadpool(db.get_participant, pid)
    if not part:
        raise HTTPException(404, "Sessão não encontrada. Comece o teste novamente.")
    return part


@app.post("/api/fase2")
async def fase2(body: Fase2In):
    part = await _load(body.id)
    if part["status"] != "respondendo":
        raise HTTPException(409, "Este teste já foi finalizado.")
    _check_answers(body.respostas, PHASE1_IDS)
    tops, qs = phase2_questions(body.respostas)
    await run_in_threadpool(db.save_phase1, body.id, body.respostas, tops)
    return {"perguntas": [{"id": q["id"], "texto": q["texto"]} for q in qs], "abertas": OPEN_QUESTIONS}


@app.post("/api/finalizar")
async def finalizar(body: FinalizarIn):
    """Salva e responde na hora com o link da página de resultado (que se completa sozinha)."""
    part = await _load(body.id)
    if part["status"] != "respondendo":  # idempotente: duplo toque devolve o mesmo link
        return {"token": part["token"], "url": f"/r/{part['token']}"}
    if not part["top_fase1"]:
        raise HTTPException(409, "Responda a primeira parte do teste antes.")
    expected = {q["id"] for d in part["top_fase1"] for q in PHASE2[d]}
    _check_answers(body.respostas, expected)
    _check_open(body.abertas)

    todas = {**part["respostas"], **body.respostas}
    perfil = compute_profile(todas)
    token = secrets.token_urlsafe(12)
    if await run_in_threadpool(db.save_answers_and_queue, body.id, token, todas, body.abertas, perfil):
        pipeline.enqueue(body.id)
    else:
        token = (await _load(body.id))["token"]
    return {"token": token, "url": f"/r/{token}"}


# ---------------------------------------------------------------- página de resultado
TOKEN_RE = re.compile(r"^[A-Za-z0-9_-]{8,40}$")


async def _by_token(token: str) -> dict:
    part = await run_in_threadpool(db.get_by_token, token) if TOKEN_RE.match(token or "") else None
    if not part:
        raise HTTPException(404, "Resultado não encontrado.")
    return part


@app.get("/api/resultado/{token}")
async def resultado(token: str):
    part = await _by_token(token)
    perfil = part["perfil"]
    cursos = [
        {"curso": o["curso"], "motivo": o["motivo"], "detalhe": part.get(f"detalhe_{i}")}
        for i, o in enumerate(part["opcoes"] or [])
    ]
    return {
        "status": part["status"],
        "nome": part["nome"].split(" ")[0],
        "cidade": part["cidade"],
        "perfil": [{"nome": DIMENSIONS[d]["nome"], "descricao": DIMENSIONS[d]["descricao"]} for d in perfil["top_dimensoes"][:2]],
        "cursos": cursos,
        "org": {"nome": settings.org_name, "whatsapp": bool(settings.org_whatsapp)},
        "whatsapp_link": _wa_alfabits(part),
        "interesse_enviado": part["interesse"] is not None,
    }


EVENT_TYPES = {"abriu_pagina", "abriu_curso", "clicou_instituicao", "compartilhou", "compartilhou_numero",
               "salvou_pdf", "clicou_conversar"}


class EventoIn(BaseModel):
    token: str = Field(max_length=40)
    tipo: str = Field(max_length=30)
    curso: str | None = Field(default=None, max_length=80)
    detalhe: str | None = Field(default=None, max_length=120)
    dono: bool = True


@app.post("/api/evento", status_code=204)
async def evento(ev: EventoIn):
    if ev.tipo not in EVENT_TYPES:
        raise HTTPException(422, "Evento inválido")
    part = await _by_token(ev.token)
    if await run_in_threadpool(db.count_events, part["id"]) < 300:  # teto por participante (anti-spam)
        await run_in_threadpool(db.add_event, part["id"], ev.tipo, ev.curso, ev.detalhe, ev.dono)
    return Response(status_code=204)


class InteresseIn(BaseModel):
    """Hoje a página só manda token + dono (o aluno clica e vai direto para o WhatsApp da Alfabits).
    Os outros campos continuam aceitos, opcionais."""
    token: str = Field(max_length=40)
    curso: str = Field(default="", max_length=80)
    periodo: str = Field(default="", max_length=20)
    quem: str = Field(default="aluno", max_length=20)
    mensagem: str = Field(default="", max_length=300)
    responsavel_nome: str = Field(default="", max_length=80)
    responsavel_telefone: str = Field(default="", max_length=25)
    dono: bool = True

    @field_validator("periodo")
    @classmethod
    def _periodo(cls, v: str) -> str:
        if v not in {"", "manha", "tarde", "noite", "qualquer"}:
            raise ValueError("escolha um período")
        return v

    @field_validator("responsavel_telefone")
    @classmethod
    def _tel(cls, v: str) -> str:
        return normalize_phone(v) if v.strip() else ""


@app.post("/api/interesse")
async def interesse(body: InteresseIn):
    part = await _by_token(body.token)
    cursos_validos = {o["curso"] for o in part["opcoes"] or []} | {"Ainda não sei"}
    if body.curso and body.curso not in cursos_validos:
        raise HTTPException(422, "Escolha um dos cursos")
    dados = body.model_dump(exclude={"token"})
    dados["mensagem"] = dados["mensagem"].strip()
    await run_in_threadpool(db.save_interest, part["id"], dados)
    await run_in_threadpool(db.add_event, part["id"], "enviou_interesse", body.curso, body.periodo, body.dono)
    return {"ok": True, "whatsapp_link": _wa_alfabits(part, body.curso)}


def _wa_alfabits(part: dict, curso: str = "") -> str | None:
    """Link para o aluno chamar a Alfabits no WhatsApp, com a mensagem pronta."""
    if not settings.org_whatsapp:
        return None
    texto = f"Olá! Sou {part['nome'].split(' ')[0]}, fiz o Teste Vocacional. Quero conhecer os cursos da {settings.org_name}."
    return f"https://wa.me/{settings.org_whatsapp}?text={quote(texto)}"


# ---------------------------------------------------------------- admin
def _admin(request: Request) -> None:
    """Aceita a sessão da tela /admin (cookie) ou o ADMIN_TOKEN (header/URL, para scripts)."""
    if admin_auth.valid_session(request):
        return
    token = request.headers.get("x-admin-token") or request.query_params.get("token") or ""
    if not settings.admin_token or not secrets.compare_digest(token.encode(), settings.admin_token.encode()):
        raise HTTPException(401, "Não autorizado")


def _espera(seg: int) -> str:
    if seg >= 3600:
        return f"{seg // 3600} h {seg % 3600 // 60} min"
    return f"{max(1, (seg + 59) // 60)} min"


class LoginIn(BaseModel):
    usuario: str = Field(max_length=100)
    senha: str = Field(max_length=200)


@app.post("/api/admin/login")
async def admin_login(body: LoginIn, request: Request):
    ip = admin_auth.client_ip(request)
    wait = admin_auth.wait_left(ip)
    if wait:
        return JSONResponse({"detail": f"Muitas tentativas. Tente de novo em {_espera(wait)}.", "espera": wait}, status_code=429)
    ok, wait = admin_auth.check_login(ip, body.usuario.strip(), body.senha)
    if not ok:
        logging.getLogger("admin").warning("login admin falhou (ip %s), bloqueado por %ss", ip, wait)
        return JSONResponse({"detail": f"Usuário ou senha incorretos. Tente de novo em {_espera(wait)}.", "espera": wait},
                            status_code=401)
    res = JSONResponse({"ok": True})
    res.set_cookie(admin_auth.COOKIE, admin_auth.new_session(), max_age=admin_auth.SESSION_TTL, httponly=True,
                   samesite="strict", secure=admin_auth.is_https(request), path="/")
    return res


@app.post("/api/admin/logout")
async def admin_logout(request: Request):
    admin_auth.end_session(request)
    res = JSONResponse({"ok": True})
    res.delete_cookie(admin_auth.COOKIE, path="/")
    return res


SCALE_LABEL = {o["value"]: o["label"] for o in SCALE}
QUEM = {"aluno": "o próprio aluno", "responsavel": "o responsável"}


def _admin_rows() -> list[dict]:
    """Tudo de cada aluno para a tela /admin."""
    evs = db.events_summary()
    rows = []
    for p in db.all_participants():
        ev = evs.get(p["id"], {})
        it = p["interesse"]
        score = lead_score(ev, it)
        try:
            idade = age_from(date.fromisoformat(p["nascimento"]))
        except ValueError:
            idade = None
        rows.append({
            "id": p["id"], "criado_em": p["criado_em"], "respondido_em": p["respondido_em"],
            "nome": p["nome"], "idade": idade, "nascimento": p["nascimento"], "telefone": p["telefone"],
            "cidade": p["cidade"], "escola": p["escola"], "serie": p["serie"] or "",
            "aceita_contato": bool(p["aceita_contato"]), "status": p["status"], "fonte": p["fonte_cursos"] or "",
            "perfil": [DIMENSIONS[d]["nome"] for d in (p["perfil"] or {}).get("top_dimensoes", [])[:3]],
            "cursos": [{"curso": o["curso"], "motivo": o["motivo"]} for o in p["opcoes"] or []],
            "cursos_abertos": sorted(ev.get("cursos", ())),
            "abertas": [{"pergunta": q["texto"], "resposta": p["abertas"].get(q["id"], "")} for q in OPEN_QUESTIONS],
            "respostas": [{"pergunta": QUESTION_INDEX[k]["texto"], "resposta": SCALE_LABEL.get(v, v)}
                          for k, v in p["respostas"].items() if k in QUESTION_INDEX],
            "interesse": {**it, "periodo": PERIODOS.get(it.get("periodo", ""), ""), "quem": QUEM.get(it.get("quem", ""), "")}
            if it else None,
            "clicou_conversar": ev.get("clicou_conversar", 0),
            "compartilhou": ev.get("compartilhou", 0), "compartilhou_numero": ev.get("compartilhou_numero", 0),
            "compartilhou_como": sorted(ev.get("compartilhou_como", ())),
            "views_aluno": ev.get("views_dono", 0), "views_outros": ev.get("views_outros", 0),
            "pdf": ev.get("pdf", 0), "ultima_visita": ev.get("ultima_visita", ""),
            "pontos": score, "temperatura": temperatura(score) if p["token"] else "",
            "link": f"/r/{p['token']}" if p["token"] else "",
        })
    return rows


@app.get("/api/admin/participantes")
async def admin_participantes(request: Request):
    _admin(request)
    rows = await run_in_threadpool(_admin_rows)
    s = await run_in_threadpool(db.stats)
    s["na_fila_agora"] = pipeline.pending()
    return {"participantes": rows, "stats": s}


def lead_score(ev: dict, interesse: dict | None) -> int:
    score = 100 if interesse else 0
    score += min(ev.get("compartilhou", 0) * 15, 30)
    score += 15 if ev.get("views_outros", 0) else 0  # família/amigos abriram o link
    score += 10 if ev.get("pdf", 0) else 0
    score += min(len(ev.get("instituicoes", ())) * 5, 20)
    score += len(ev.get("cursos", ())) * 3
    score += 5 if ev.get("views_dono", 0) > 1 else 0  # voltou a olhar
    return score


def temperatura(score: int) -> str:
    return "quente" if score >= 100 else "morno" if score >= 20 else "frio"


PERIODOS = {"manha": "manhã", "tarde": "tarde", "noite": "noite", "qualquer": "qualquer horário"}


def _lead_rows() -> list[dict]:
    evs = db.events_summary()
    rows = []
    for p in db.all_participants():
        ev = evs.get(p["id"], {})
        it = p["interesse"] or {}
        score = lead_score(ev, p["interesse"])
        base = f"{settings.public_url}/r/{p['token']}" if p["token"] else ""
        rows.append({
            "temperatura": temperatura(score) if p["token"] else "", "pontos": score,
            "criado_em": p["criado_em"], "nome": p["nome"], "telefone": p["telefone"], "nascimento": p["nascimento"],
            "cidade": p["cidade"], "escola": p["escola"], "serie": p["serie"] or "",
            "aceita_contato": "sim" if p["aceita_contato"] else "não",
            "perfil": p["perfil"]["codigo"] if p["perfil"] else "",
            "cursos_sugeridos": " | ".join(o["curso"] for o in p["opcoes"] or []),
            "quer_conversar": "sim" if p["interesse"] else "",
            "curso_de_interesse": it.get("curso", ""), "melhor_periodo": PERIODOS.get(it.get("periodo", ""), ""),
            "quem_pediu": it.get("quem", ""), "mensagem": it.get("mensagem", ""),
            "responsavel": it.get("responsavel_nome", ""), "telefone_responsavel": it.get("responsavel_telefone", ""),
            "visitas_aluno": ev.get("views_dono", 0), "visitas_outros": ev.get("views_outros", 0),
            "cursos_abertos": " | ".join(sorted(ev.get("cursos", ()))),
            "instituicoes_clicadas": " | ".join(sorted(ev.get("instituicoes", ()))),
            "compartilhou": ev.get("compartilhou", 0), "salvou_pdf": ev.get("pdf", 0),
            "abertas_tempo_livre": p["abertas"].get("ab_livre", ""), "abertas_curso_pensado": p["abertas"].get("ab_sonho", ""),
            "status": p["status"], "fonte_cursos": p["fonte_cursos"] or "", "link_resultado": base,
        })
    return rows


def _csv(rows: list[dict], filename: str) -> Response:
    buf = io.StringIO()
    if rows:
        w = csv.DictWriter(buf, fieldnames=list(rows[0]), delimiter=";")
        w.writeheader()
        w.writerows(rows)
    return Response("\ufeff" + buf.getvalue(), media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": f"attachment; filename={filename}"})


@app.get("/api/admin/stats")
async def admin_stats(request: Request):
    _admin(request)
    s = await run_in_threadpool(db.stats)
    s["na_fila_agora"] = pipeline.pending()
    return s


@app.get("/api/admin/export.csv")
async def admin_export(request: Request):
    _admin(request)
    return _csv(await run_in_threadpool(_lead_rows), "teste_vocacional.csv")


@app.get("/api/admin/leads.csv")
async def admin_leads(request: Request):
    """Mesmos dados, ordenados do lead mais quente para o mais frio."""
    _admin(request)
    rows = sorted(await run_in_threadpool(_lead_rows), key=lambda r: -r["pontos"])
    return _csv(rows, "leads_teste_vocacional.csv")


@app.post("/api/admin/reprocessar")
async def admin_reprocess(request: Request):
    """Gera de novo os detalhes que caíram no conteúdo padrão (ex.: LLM estava fora do ar)."""
    _admin(request)
    ids = await run_in_threadpool(db.ids_with_fallback_details)
    for pid in ids:
        await run_in_threadpool(db.reset_details, pid)
        pipeline.enqueue(pid)
    return {"reprocessando": len(ids)}


# ---------------------------------------------------------------- erros
FIELD_NAMES = {"nome": "Nome", "telefone": "WhatsApp", "nascimento": "Data de nascimento", "cidade": "Cidade",
               "escola": "Escola", "serie": "Série", "aceita_lgpd": "Autorização LGPD",
               "periodo": "Período", "responsavel_telefone": "WhatsApp do responsável", "curso": "Curso"}


@app.exception_handler(HTTPException)
async def http_exc(_: Request, exc: HTTPException):
    return JSONResponse({"detail": exc.detail}, status_code=exc.status_code)


@app.exception_handler(RequestValidationError)
async def validation_exc(_: Request, exc: RequestValidationError):
    errs = exc.errors()
    first = errs[0] if errs else {}
    field = next((str(x) for x in reversed(first.get("loc", [])) if isinstance(x, str) and x != "body"), "")
    msg = str(first.get("msg", "Dados inválidos")).replace("Value error, ", "")
    if first.get("type") in {"string_too_short", "missing", "date_from_datetime_parsing", "date_parsing"}:
        msg = "preencha corretamente"
    label = FIELD_NAMES.get(field)
    return JSONResponse({"detail": f"{label}: {msg}" if label else msg, "field": field}, status_code=422)


# ---------------------------------------------------------------- frontend
@app.get("/")
async def index():
    return FileResponse(STATIC / "index.html", headers={"Cache-Control": "no-cache"})


@app.get("/admin")
async def pagina_admin():
    return FileResponse(STATIC / "admin.html", headers={"Cache-Control": "no-cache", "X-Robots-Tag": "noindex, nofollow"})


@app.get("/sw.js")
async def service_worker():
    return FileResponse(STATIC / "sw.js", media_type="application/javascript", headers={"Cache-Control": "no-cache"})


@app.get("/r/{token}")
async def pagina_resultado(token: str):
    await _by_token(token)
    return FileResponse(STATIC / "resultado.html",
                        headers={"Cache-Control": "no-cache", "X-Robots-Tag": "noindex, nofollow"})


@app.get("/manifest.webmanifest")
async def manifest():
    return FileResponse(STATIC / "manifest.webmanifest", media_type="application/manifest+json")


app.mount("/static", StaticFiles(directory=STATIC), name="static")
