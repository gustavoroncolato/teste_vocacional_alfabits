"""Fluxo da API do teste: cadastro, validações, fases, finalização."""
import time

import pytest

from app import db
from app.main import normalize_phone
from tests.conftest import ABERTAS, PERFIL, run_full_test, wait_status


def test_normalize_phone():
    assert normalize_phone("(18) 99876-5432") == "5518998765432"
    assert normalize_phone("+55 18 3269-1234") == "551832691234"
    for ruim in ("123", "18 89876-5432", "(00) 99999-9999", ""):
        with pytest.raises(ValueError):
            normalize_phone(ruim)


@pytest.mark.parametrize("campo,valor,trecho", [
    ("aceita_lgpd", False, "LGPD"),
    ("telefone", "999", "WhatsApp"),
    ("nascimento", "2025-01-01", "nascimento"),
    ("nome", " ", "Nome"),
    ("escola", "", "Escola"),
])
def test_validacoes_do_cadastro(client, campo, valor, trecho):
    r = client.post("/api/iniciar", json={**PERFIL, campo: valor})
    assert r.status_code == 422
    assert trecho.lower() in r.json()["detail"].lower()


def test_contato_e_opcional_e_consentimentos_salvos(client):
    sem = {k: v for k, v in PERFIL.items() if k != "aceita_contato"}
    pid = client.post("/api/iniciar", json=sem).json()["id"]
    assert db.get_participant(pid)["aceita_contato"] == 0
    pid, _ = run_full_test(client)
    p = db.get_participant(pid)
    assert p["aceita_lgpd"] == 1 and p["aceita_contato"] == 1


def test_finalizar_responde_na_hora_com_link_do_resultado(client):
    t = time.perf_counter()
    pid, res = run_full_test(client)
    assert time.perf_counter() - t < 2
    assert res["url"] == f"/r/{res['token']}" and len(res["token"]) >= 16
    assert set(res) == {"token", "url"}  # não devolve dados pessoais
    p = wait_status(pid)
    assert p["token"] == res["token"] and p["status"] == "pronto"


def test_validacao_das_respostas(client):
    d = client.post("/api/iniciar", json=PERFIL).json()
    pid = d["id"]
    base = {q["id"]: 3 for q in d["perguntas"]}
    for ruim in ({"p1_r1": 5}, {**base, "p1_r1": 6}, {**base, "p1_r1": 0}, {**base, "extra": 3}, {**base, "p1_r1": True}):
        assert client.post("/api/fase2", json={"id": pid, "respostas": ruim}).status_code == 422
    assert client.post("/api/finalizar", json={"id": pid, "respostas": {}}).status_code == 409
    f2 = client.post("/api/fase2", json={"id": pid, "respostas": base}).json()
    assert client.post("/api/finalizar", json={"id": pid, "respostas": {"p2_r1": 3}}).status_code == 422
    ok = {q["id"]: 3 for q in f2["perguntas"]}
    assert client.post("/api/finalizar", json={"id": pid, "respostas": ok, "abertas": ABERTAS}).status_code == 200


def test_finalizar_duas_vezes_devolve_o_mesmo_link(client):
    d = client.post("/api/iniciar", json=PERFIL).json()
    f2 = client.post("/api/fase2", json={"id": d["id"], "respostas": {q["id"]: 3 for q in d["perguntas"]}}).json()
    body = {"id": d["id"], "respostas": {q["id"]: 3 for q in f2["perguntas"]}, "abertas": ABERTAS}
    r1, r2 = client.post("/api/finalizar", json=body).json(), client.post("/api/finalizar", json=body).json()
    assert r1 == r2
    assert client.post("/api/fase2", json={"id": d["id"], "respostas": {q["id"]: 3 for q in d["perguntas"]}}).status_code == 409


def test_respostas_abertas_limitadas(client):
    pid, _ = run_full_test(client, abertas={"ab_livre": "desenho " * 700, "ab_sonho": "quero ser arquiteta", "campo_estranho": "y"})
    p = db.get_participant(pid)
    assert len(p["abertas"]["ab_livre"]) == 400 and "campo_estranho" not in p["abertas"]


def test_sessao_inexistente(client):
    assert client.post("/api/fase2", json={"id": "naoexiste", "respostas": {}}).status_code == 404


def test_frontend_do_teste(client):
    html = client.get("/").text
    assert 'name="aceita_lgpd"' in html and 'name="aceita_contato"' in html
    assert client.get("/manifest.webmanifest").status_code == 200
    assert client.get("/sw.js").status_code == 200
    assert client.get("/static/app.js?v=3").status_code == 200


@pytest.mark.parametrize("abertas", [
    {"ab_livre": "jogar", "ab_sonho": "quero ser arquiteta"},          # curta demais
    {"ab_livre": "gosto de desenhar e jogar bola", "ab_sonho": ""},    # segunda em branco
    {"ab_livre": "aaaaaaaaaaaaaaaaaaaa", "ab_sonho": "quero ser arquiteta"},  # sem texto de verdade
])
def test_respostas_abertas_precisam_de_texto_minimo(client, abertas):
    r = client.post("/api/iniciar", json=PERFIL)
    d = r.json()
    r = client.post("/api/fase2", json={"id": d["id"], "respostas": {q["id"]: 4 for q in d["perguntas"]}})
    f2 = r.json()
    r = client.post("/api/finalizar", json={"id": d["id"], "respostas": {q["id"]: 4 for q in f2["perguntas"]}, "abertas": abertas})
    assert r.status_code == 422 and "mínimo" in r.json()["detail"]
