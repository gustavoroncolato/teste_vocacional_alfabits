import dataclasses
import os
import tempfile
import time

os.environ.update({
    "DATABASE_PATH": os.path.join(tempfile.mkdtemp(), "test.db"),
    "LLM_API_KEY": "", "LLM_MOCK": "0", "LLM_REASONING_EFFORT": "", "ADMIN_TOKEN": "segredo",
    "ADMIN_USER": "admin", "ADMIN_PASSWORD": "senha-teste",
    "ORG_WHATSAPP": "551832690000", "PUBLIC_URL": "https://teste.exemplo",
})

import pytest  # noqa: E402

from app import admin_auth, config, db, llm, main, worker  # noqa: E402

PERFIL = {
    "nome": "Maria Souza",
    "telefone": "(18) 99876-5432",
    "nascimento": "2008-05-10",
    "cidade": "Pirapozinho",
    "escola": "EE Professor Exemplo",
    "serie": "3º ano do Ensino Médio",
    "aceita_lgpd": True,
    "aceita_contato": True,
}


def patch_settings(monkeypatch, **kw):
    new = dataclasses.replace(config.settings, **kw)
    for mod in (config, db, llm, main, worker, admin_auth):
        monkeypatch.setattr(mod, "settings", new, raising=False)
    return new


ABERTAS = {"ab_livre": "gosto de desenhar e jogar bola", "ab_sonho": "ainda não sei, talvez tocar zabumba"}


def run_full_test(client, perfil=None, answer=lambda qid: 4, abertas=None):
    r = client.post("/api/iniciar", json=perfil or PERFIL)
    assert r.status_code == 200, r.text
    d = r.json()
    r = client.post("/api/fase2", json={"id": d["id"], "respostas": {q["id"]: answer(q["id"]) for q in d["perguntas"]}})
    assert r.status_code == 200, r.text
    f2 = r.json()
    body = {"id": d["id"], "respostas": {q["id"]: answer(q["id"]) for q in f2["perguntas"]},
            "abertas": abertas or ABERTAS}
    r = client.post("/api/finalizar", json=body)
    assert r.status_code == 200, r.text
    return d["id"], r.json()


def wait_status(pid, done=("pronto",), timeout=8.0):
    t = time.time()
    while time.time() - t < timeout:
        p = db.get_participant(pid)
        if p and p["status"] in done:
            return p
        time.sleep(0.05)
    raise AssertionError(f"status final não atingido: {db.get_participant(pid)['status']}")


@pytest.fixture
def client():
    from fastapi.testclient import TestClient

    admin_auth.reset()
    with TestClient(main.app) as c:
        yield c
