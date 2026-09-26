"""Geração do resultado em segundo plano.

A pessoa termina o teste e vai direto para a página de resultado, que se completa sozinha:
1. escolha dos 3 cursos (LLM rápido)      -> status 'detalhando' (a página já mostra os 3 cursos)
2. detalhes dos 3 cursos, em paralelo    -> cada curso aparece assim que fica pronto
3. status 'pronto'
Se o LLM falhar, entra o conteúdo padrão. Tudo fica no SQLite: se o servidor reiniciar,
o que estava pendente volta para a fila.
IMPORTANTE: rode com 1 processo (sem --workers N), senão cada processo teria sua própria fila.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import date

from . import db, llm
from .config import settings
from .questions import DIMENSIONS
from .scoring import area_of_course, fallback_detail, fallback_options

log = logging.getLogger("worker")


def age_from(nasc: date) -> int:
    today = date.today()
    return today.year - nasc.year - ((today.month, today.day) < (nasc.month, nasc.day))


class Pipeline:
    def __init__(self) -> None:
        self.queue: asyncio.Queue[str] | None = None
        self.tasks: list[asyncio.Task] = []
        self._active = 0

    async def start(self) -> None:
        self.queue, self._active = asyncio.Queue(), 0
        pend = await asyncio.to_thread(db.ids_with_status, "na_fila", "detalhando")
        for pid in pend:
            self.queue.put_nowait(pid)
        if pend:
            log.info("Recuperados da fila: %s", len(pend))
        self.tasks = [asyncio.create_task(self._worker()) for _ in range(settings.llm_workers)]

    async def stop(self) -> None:
        for t in self.tasks:
            t.cancel()
        await asyncio.gather(*self.tasks, return_exceptions=True)
        self.tasks = []

    def enqueue(self, pid: str) -> None:
        if self.queue is not None:
            self.queue.put_nowait(pid)

    def pending(self) -> int:
        return (self.queue.qsize() if self.queue else 0) + self._active

    async def _worker(self) -> None:
        while True:
            pid = await self.queue.get()
            self._active += 1
            try:
                await self.process(pid)
            except Exception:  # noqa: BLE001 - worker nunca pode morrer
                log.exception("Erro processando %s", pid)
            finally:
                self._active -= 1
                self.queue.task_done()

    async def process(self, pid: str) -> None:
        part = await asyncio.to_thread(db.get_participant, pid)
        if not part or part["status"] not in ("na_fila", "detalhando"):
            return
        first = part["nome"].split(" ")[0]
        idade = age_from(date.fromisoformat(part["nascimento"]))
        perfil = part["perfil"]

        # etapa 1: 3 cursos
        opcoes = part["opcoes"]
        if part["status"] == "na_fila" or not opcoes:
            opcoes = await llm.choose_courses(first, idade, perfil, part["abertas"], part.get("serie"))
            fonte = "llm"
            if not opcoes:
                opcoes, fonte = fallback_options(perfil), "padrao"
            await asyncio.to_thread(db.save_courses, pid, opcoes, fonte)

        # etapa 2: detalhes em paralelo (só os que faltam)
        resumo = ", ".join(DIMENSIONS[d]["nome"] for d in perfil["top_dimensoes"])

        async def detalhar(i: int, op: dict) -> None:
            if part.get(f"detalhe_{i}"):
                return
            det = await llm.course_detail(op["curso"], first, idade, part["cidade"], resumo, part.get("serie"))
            if not det:
                det = fallback_detail(op.get("area") or area_of_course(op["curso"]) or perfil["areas"][min(i, 2)]["id"])
            await asyncio.to_thread(db.save_detail, pid, i, det)

        await asyncio.gather(*(detalhar(i, op) for i, op in enumerate(opcoes[:3])))
        await asyncio.to_thread(db.mark_ready, pid)


pipeline = Pipeline()
