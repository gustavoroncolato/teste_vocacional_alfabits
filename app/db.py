"""Persistência em SQLite (WAL). No Railway, monte um Volume e aponte DATABASE_PATH para ele.

Status do participante:
  respondendo -> na_fila (aguardando LLM) -> detalhando (cursos escolhidos, detalhes sendo gerados) -> pronto
"""
from __future__ import annotations

import json
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path

from .config import settings

_local = threading.local()

TABLE = """
CREATE TABLE IF NOT EXISTS participantes (
    id TEXT PRIMARY KEY,
    token TEXT UNIQUE,
    criado_em TEXT NOT NULL,
    nome TEXT NOT NULL,
    telefone TEXT NOT NULL,
    nascimento TEXT NOT NULL,
    cidade TEXT NOT NULL,
    escola TEXT NOT NULL,
    serie TEXT,
    aceita_lgpd INTEGER NOT NULL DEFAULT 1,
    aceita_contato INTEGER NOT NULL DEFAULT 0,
    respostas TEXT NOT NULL DEFAULT '{}',
    abertas TEXT NOT NULL DEFAULT '{}',
    top_fase1 TEXT,
    perfil TEXT,
    opcoes TEXT,
    fonte_cursos TEXT,
    detalhe_0 TEXT,
    detalhe_1 TEXT,
    detalhe_2 TEXT,
    interesse TEXT,
    status TEXT NOT NULL DEFAULT 'respondendo',
    respondido_em TEXT,
    pronto_em TEXT
)"""

EVENTS = """
CREATE TABLE IF NOT EXISTS eventos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    participante_id TEXT NOT NULL,
    em TEXT NOT NULL,
    tipo TEXT NOT NULL,
    curso TEXT,
    detalhe TEXT,
    dono INTEGER NOT NULL DEFAULT 1
)"""

_COLS = {
    "token": "TEXT", "aceita_lgpd": "INTEGER NOT NULL DEFAULT 1", "aceita_contato": "INTEGER NOT NULL DEFAULT 0",
    "opcoes": "TEXT", "fonte_cursos": "TEXT", "detalhe_0": "TEXT", "detalhe_1": "TEXT", "detalhe_2": "TEXT",
    "interesse": "TEXT", "status": "TEXT NOT NULL DEFAULT 'respondendo'", "respondido_em": "TEXT", "pronto_em": "TEXT",
}
JSON_COLS = ("top_fase1", "perfil", "opcoes", "detalhe_0", "detalhe_1", "detalhe_2", "interesse")


def _conn() -> sqlite3.Connection:
    c = getattr(_local, "conn", None)
    if c is None or getattr(_local, "path", None) != settings.database_path:
        Path(settings.database_path).parent.mkdir(parents=True, exist_ok=True)
        c = sqlite3.connect(settings.database_path, timeout=10, check_same_thread=False)
        c.row_factory = sqlite3.Row
        c.execute("PRAGMA journal_mode=WAL")
        c.execute("PRAGMA synchronous=NORMAL")
        c.execute("PRAGMA busy_timeout=10000")
        _local.conn, _local.path = c, settings.database_path
    return c


def init() -> None:
    c = _conn()
    c.execute(TABLE)
    c.execute(EVENTS)
    cols = {r["name"] for r in c.execute("PRAGMA table_info(participantes)")}
    for col, ddl in _COLS.items():  # migração de bancos antigos
        if col not in cols:
            c.execute(f"ALTER TABLE participantes ADD COLUMN {col} {ddl}")
    c.execute("CREATE INDEX IF NOT EXISTS idx_status ON participantes(status)")
    c.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_token ON participantes(token)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_ev ON eventos(participante_id)")
    c.commit()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _decode(row: sqlite3.Row | None) -> dict | None:
    if not row:
        return None
    d = dict(row)
    for k in ("respostas", "abertas"):
        d[k] = json.loads(d[k] or "{}")
    for k in JSON_COLS:
        d[k] = json.loads(d[k]) if d.get(k) else None
    return d


def create_participant(pid: str, p: dict) -> None:
    c = _conn()
    c.execute(
        "INSERT INTO participantes (id, criado_em, nome, telefone, nascimento, cidade, escola, serie, aceita_lgpd, aceita_contato)"
        " VALUES (?,?,?,?,?,?,?,?,?,?)",
        (pid, _now(), p["nome"], p["telefone"], p["nascimento"], p["cidade"], p["escola"], p.get("serie"),
         int(p["aceita_lgpd"]), int(p["aceita_contato"])),
    )
    c.commit()


def get_participant(pid: str) -> dict | None:
    return _decode(_conn().execute("SELECT * FROM participantes WHERE id = ?", (pid,)).fetchone())


def get_by_token(token: str) -> dict | None:
    return _decode(_conn().execute("SELECT * FROM participantes WHERE token = ?", (token,)).fetchone())


def save_phase1(pid: str, respostas: dict, tops: list[str]) -> None:
    c = _conn()
    c.execute("UPDATE participantes SET respostas = ?, top_fase1 = ? WHERE id = ?", (json.dumps(respostas), json.dumps(tops), pid))
    c.commit()


def save_answers_and_queue(pid: str, token: str, respostas: dict, abertas: dict, perfil: dict) -> bool:
    """Salva as respostas finais e coloca na fila. Retorna False se já estava finalizado (idempotente)."""
    c = _conn()
    cur = c.execute(
        "UPDATE participantes SET token=?, respostas=?, abertas=?, perfil=?, status='na_fila', respondido_em=? "
        "WHERE id=? AND status='respondendo'",
        (token, json.dumps(respostas), json.dumps(abertas, ensure_ascii=False), json.dumps(perfil, ensure_ascii=False), _now(), pid),
    )
    c.commit()
    return cur.rowcount == 1


def save_courses(pid: str, opcoes: list[dict], fonte: str) -> None:
    c = _conn()
    c.execute("UPDATE participantes SET opcoes=?, fonte_cursos=?, status='detalhando' WHERE id=?",
              (json.dumps(opcoes, ensure_ascii=False), fonte, pid))
    c.commit()


def save_detail(pid: str, idx: int, detalhe: dict) -> None:
    assert idx in (0, 1, 2)
    c = _conn()
    c.execute(f"UPDATE participantes SET detalhe_{idx}=? WHERE id=?", (json.dumps(detalhe, ensure_ascii=False), pid))
    c.commit()


def mark_ready(pid: str) -> None:
    c = _conn()
    c.execute("UPDATE participantes SET status='pronto', pronto_em=? WHERE id=?", (_now(), pid))
    c.commit()


def ids_with_status(*status: str) -> list[str]:
    q = f"SELECT id FROM participantes WHERE status IN ({','.join('?' * len(status))}) ORDER BY respondido_em"
    return [r[0] for r in _conn().execute(q, status)]


def ids_with_fallback_details() -> list[str]:
    q = ("SELECT id FROM participantes WHERE status='pronto' AND (fonte_cursos='padrao' OR "
         + " OR ".join(f"json_extract(detalhe_{i}, '$.fonte')='padrao'" for i in range(3)) + ")")
    return [r[0] for r in _conn().execute(q)]


def reset_details(pid: str) -> None:
    """Apaga os detalhes para a IA gerar de novo. Se os cursos também eram o padrão, escolhe de novo
    (menos para quem já pediu para conversar sobre um desses cursos)."""
    c = _conn()
    c.execute("UPDATE participantes SET detalhe_0=NULL, detalhe_1=NULL, detalhe_2=NULL, "
              "status=CASE WHEN fonte_cursos='padrao' AND interesse IS NULL THEN 'na_fila' ELSE 'detalhando' END "
              "WHERE id=?", (pid,))
    c.commit()


# ---------------------------------------------------------------- eventos e interesse
def count_events(pid: str) -> int:
    return _conn().execute("SELECT COUNT(*) FROM eventos WHERE participante_id=?", (pid,)).fetchone()[0]


def add_event(pid: str, tipo: str, curso: str | None, detalhe: str | None, dono: bool) -> None:
    c = _conn()
    c.execute("INSERT INTO eventos (participante_id, em, tipo, curso, detalhe, dono) VALUES (?,?,?,?,?,?)",
              (pid, _now(), tipo, curso, detalhe, int(dono)))
    c.commit()


def save_interest(pid: str, interesse: dict) -> None:
    c = _conn()
    c.execute("UPDATE participantes SET interesse=?, aceita_contato=1 WHERE id=?",
              (json.dumps({**interesse, "em": _now()}, ensure_ascii=False), pid))
    c.commit()


def events_summary() -> dict[str, dict]:
    out: dict[str, dict] = {}
    for r in _conn().execute("SELECT participante_id, tipo, curso, detalhe, dono, em FROM eventos"):
        s = out.setdefault(r["participante_id"], {"views_dono": 0, "views_outros": 0, "cursos": set(),
                                                   "instituicoes": set(), "compartilhou": 0, "pdf": 0,
                                                   "compartilhou_numero": 0, "compartilhou_como": set(),
                                                   "clicou_conversar": 0, "ultima_visita": ""})
        if r["tipo"] == "abriu_pagina":
            s["views_dono" if r["dono"] else "views_outros"] += 1
            if r["dono"]:
                s["ultima_visita"] = max(s["ultima_visita"], r["em"])
        elif r["tipo"] == "abriu_curso" and r["curso"]:
            s["cursos"].add(r["curso"])
        elif r["tipo"] == "clicou_instituicao" and r["detalhe"]:
            s["instituicoes"].add(r["detalhe"])
        elif r["tipo"] in ("compartilhou", "compartilhou_numero"):
            s["compartilhou"] += 1
            if r["tipo"] == "compartilhou_numero":
                s["compartilhou_numero"] += 1
            s["compartilhou_como"].add(r["detalhe"] or "numero")
        elif r["tipo"] == "clicou_conversar":
            s["clicou_conversar"] += 1
        elif r["tipo"] == "salvou_pdf":
            s["pdf"] += 1
    return out


def all_participants() -> list[dict]:
    return [_decode(r) for r in _conn().execute("SELECT * FROM participantes ORDER BY criado_em").fetchall()]


def stats() -> dict:
    c = _conn()
    by_status = {r[0]: r[1] for r in c.execute("SELECT status, COUNT(*) FROM participantes GROUP BY status")}
    interessados = c.execute("SELECT COUNT(*) FROM participantes WHERE interesse IS NOT NULL").fetchone()[0]
    return {"total": sum(by_status.values()), "por_status": by_status, "querem_conversar": interessados}
