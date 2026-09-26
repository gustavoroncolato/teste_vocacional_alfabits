"""Página de resultado: geração em 2 etapas, fallback, privacidade, eventos, interesse e leads."""
import asyncio
import csv
import io
import json

import httpx

from app import db, llm
from tests.conftest import PERFIL, patch_settings, run_full_test, wait_status


def _resultado(client, token):
    r = client.get(f"/api/resultado/{token}")
    assert r.status_code == 200
    return r.json()


# ---------------------------------------------------------------- página
def test_pagina_existe_e_nao_e_indexada(client):
    _, res = run_full_test(client)
    r = client.get(res["url"])
    assert r.status_code == 200 and "resultado.js" in r.text
    assert "noindex" in r.headers["x-robots-tag"] and 'name="robots" content="noindex' in r.text
    assert client.get("/r/tokenquenaoexiste123").status_code == 404
    assert client.get("/r/../../etc").status_code == 404


def test_resultado_sem_llm_usa_conteudo_padrao_completo(client):
    pid, res = run_full_test(client)
    wait_status(pid)
    out = _resultado(client, res["token"])
    assert out["status"] == "pronto" and out["nome"] == "Maria"
    assert len(out["cursos"]) == 3 and len({c["curso"] for c in out["cursos"]}) == 3
    for c in out["cursos"]:
        d = c["detalhe"]
        assert c["motivo"] and d["fonte"] == "padrao"
        assert d["dia_a_dia"] and len(d["onde_trabalha"]) >= 4 and len(d["dicas"]) >= 3
    assert len(out["perfil"]) == 2 and out["org"]["whatsapp"] is True


def test_resultado_nao_expoe_dados_pessoais(client):
    pid, res = run_full_test(client)
    wait_status(pid)
    texto = json.dumps(_resultado(client, res["token"]), ensure_ascii=False)
    for segredo in ("Souza", "99876", "5432", "2008-05-10", "EE Professor", "desenhar", "zabumba", pid):
        assert segredo not in texto


def test_resultado_com_llm_simulado(monkeypatch, client):
    patch_settings(monkeypatch, llm_mock=True, llm_mock_delay=0.01)
    pid, res = run_full_test(client)
    wait_status(pid)
    out = _resultado(client, res["token"])
    assert all(c["detalhe"]["fonte"] == "llm" for c in out["cursos"])
    assert db.get_participant(pid)["fonte_cursos"] == "llm"
    assert out["cursos"][0]["detalhe"]["dia_a_dia"]


def test_pagina_se_completa_aos_poucos(monkeypatch, client):
    """Primeiro aparecem os 3 cursos (status 'detalhando'), depois os detalhes."""
    patch_settings(monkeypatch, llm_mock=True, llm_mock_delay=0.4)
    pid, res = run_full_test(client)
    wait_status(pid, done=("detalhando",))
    parcial = _resultado(client, res["token"])
    assert len(parcial["cursos"]) == 3 and all(c["detalhe"] is None for c in parcial["cursos"])
    wait_status(pid, timeout=10)
    assert all(c["detalhe"] for c in _resultado(client, res["token"])["cursos"])


def test_um_curso_falha_os_outros_seguem(monkeypatch, client):
    patch_settings(monkeypatch, llm_mock=True, llm_mock_delay=0.01)
    real = llm.course_detail
    calls = {"n": 0}

    async def flaky(curso, *a):
        calls["n"] += 1
        return None if calls["n"] == 2 else await real(curso, *a)

    monkeypatch.setattr(llm, "course_detail", flaky)
    pid, res = run_full_test(client)
    wait_status(pid)
    fontes = [c["detalhe"]["fonte"] for c in _resultado(client, res["token"])["cursos"]]
    assert sorted(fontes) == ["llm", "llm", "padrao"]


def test_admin_reprocessa_quem_caiu_no_padrao(monkeypatch, client):
    pid, res = run_full_test(client)  # sem LLM -> padrão
    wait_status(pid)
    patch_settings(monkeypatch, llm_mock=True, llm_mock_delay=0.01)
    r = client.post("/api/admin/reprocessar?token=segredo")
    assert r.json()["reprocessando"] >= 1
    wait_status(pid)
    assert all(c["detalhe"]["fonte"] == "llm" for c in _resultado(client, res["token"])["cursos"])
    assert db.get_participant(pid)["fonte_cursos"] == "llm"  # os cursos padrão também foram escolhidos de novo


def test_fila_sobrevive_a_reinicio(monkeypatch):
    from fastapi.testclient import TestClient

    from app.main import app

    patch_settings(monkeypatch, start_workers=False)
    with TestClient(app) as c:
        pid, _ = run_full_test(c)
    assert db.get_participant(pid)["status"] == "na_fila"
    patch_settings(monkeypatch, start_workers=True)
    with TestClient(app):
        assert wait_status(pid)["status"] == "pronto"


def test_muitos_ao_mesmo_tempo(monkeypatch, client):
    patch_settings(monkeypatch, llm_mock=True, llm_mock_delay=0.05)
    ids = [run_full_test(client, {**PERFIL, "nome": f"Aluno {i}"})[0] for i in range(40)]
    for pid in ids:
        assert wait_status(pid, timeout=30)["status"] == "pronto"


# ---------------------------------------------------------------- eventos
def test_eventos_validos_e_invalidos(client):
    pid, res = run_full_test(client)
    tok = res["token"]
    assert client.post("/api/evento", json={"token": tok, "tipo": "abriu_pagina"}).status_code == 204
    assert client.post("/api/evento", json={"token": tok, "tipo": "abriu_pagina", "dono": False}).status_code == 204
    assert client.post("/api/evento", json={"token": tok, "tipo": "hackear"}).status_code == 422
    assert client.post("/api/evento", json={"token": "naoexiste123", "tipo": "abriu_pagina"}).status_code == 404
    assert db.count_events(pid) == 2


def test_teto_de_eventos(client):
    pid, res = run_full_test(client)
    for _ in range(310):
        client.post("/api/evento", json={"token": res["token"], "tipo": "abriu_curso", "curso": "X"})
    assert db.count_events(pid) == 300


# ---------------------------------------------------------------- quero conversar
def _interesse(client, token, **kw):
    body = {"token": token, "curso": "Ainda não sei", "periodo": "noite", **kw}
    return client.post("/api/interesse", json=body)


def test_interesse_salva_e_devolve_link_para_a_alfabits(client):
    pid, res = run_full_test(client, perfil={**PERFIL, "aceita_contato": False})
    wait_status(pid)
    curso = _resultado(client, res["token"])["cursos"][0]["curso"]
    r = _interesse(client, res["token"], curso=curso, quem="responsavel", responsavel_nome="Ana",
                   responsavel_telefone="(18) 99111-2222", mensagem="Dúvida entre dois")
    assert r.status_code == 200
    link = r.json()["whatsapp_link"]
    assert link.startswith("https://wa.me/551832690000?text=") and "Maria" in httpx.URL(link).params["text"]
    p = db.get_participant(pid)
    assert p["aceita_contato"] == 1  # pediu contato = autorizou
    assert p["interesse"]["responsavel_telefone"] == "5518991112222"
    assert _resultado(client, res["token"])["interesse_enviado"] is True


def test_um_toque_leva_ao_whatsapp_da_alfabits(client):
    pid, res = run_full_test(client, perfil={**PERFIL, "aceita_contato": False})
    wait_status(pid)
    out = _resultado(client, res["token"])
    texto = httpx.URL(out["whatsapp_link"]).params["text"]
    assert out["whatsapp_link"].startswith("https://wa.me/551832690000?text=")
    assert texto == "Olá! Sou Maria, fiz o Teste Vocacional. Quero conhecer os cursos da Alfabits."
    r = client.post("/api/interesse", json={"token": res["token"], "dono": True})  # só o toque, sem formulário
    assert r.status_code == 200
    p = db.get_participant(pid)
    assert p["interesse"] and p["aceita_contato"] == 1
    assert _resultado(client, res["token"])["interesse_enviado"] is True


def test_interesse_validacoes(client):
    pid, res = run_full_test(client)
    wait_status(pid)
    assert _interesse(client, res["token"], curso="Curso inventado").status_code == 422
    assert _interesse(client, res["token"], periodo="madrugada").status_code == 422
    assert _interesse(client, res["token"], responsavel_telefone="123").status_code == 422
    assert _interesse(client, "naoexiste123").status_code == 404


def test_interesse_sem_whatsapp_configurado(monkeypatch, client):
    patch_settings(monkeypatch, org_whatsapp="")
    pid, res = run_full_test(client)
    wait_status(pid)
    assert _interesse(client, res["token"]).json()["whatsapp_link"] is None


# ---------------------------------------------------------------- admin / leads
def _csv(client, path):
    r = client.get(f"{path}?token=segredo")
    assert r.status_code == 200
    return list(csv.DictReader(io.StringIO(r.text.lstrip("﻿")), delimiter=";"))


def test_leads_ordenados_por_temperatura(client):
    frio_id, frio = run_full_test(client, {**PERFIL, "nome": "Frio Silva"})
    morno_id, morno = run_full_test(client, {**PERFIL, "nome": "Morno Lima"})
    quente_id, quente = run_full_test(client, {**PERFIL, "nome": "Quente Souza"})
    for pid in (frio_id, morno_id, quente_id):
        wait_status(pid)
    for tipo, extra in [("compartilhou", {}), ("abriu_pagina", {"dono": False}), ("salvou_pdf", {})]:
        client.post("/api/evento", json={"token": morno["token"], "tipo": tipo, **extra})
    client.post("/api/evento", json={"token": quente["token"], "tipo": "clicou_instituicao", "curso": "X", "detalhe": "Unesp"})
    _interesse(client, quente["token"], periodo="tarde")

    rows = _csv(client, "/api/admin/leads.csv")
    nomes = [r["nome"] for r in rows]
    assert nomes.index("Quente Souza") < nomes.index("Morno Lima") < nomes.index("Frio Silva")
    by = {r["nome"]: r for r in rows}
    assert by["Quente Souza"]["temperatura"] == "quente" and by["Quente Souza"]["melhor_periodo"] == "tarde"
    assert by["Quente Souza"]["instituicoes_clicadas"] == "Unesp"
    assert by["Morno Lima"]["temperatura"] == "morno" and by["Morno Lima"]["visitas_outros"] == "1"
    assert by["Frio Silva"]["temperatura"] == "frio"
    assert by["Frio Silva"]["link_resultado"].startswith("https://teste.exemplo/r/")
    assert by["Frio Silva"]["abertas_tempo_livre"] == "gosto de desenhar e jogar bola"


def test_admin_protegido(client):
    for path in ("/api/admin/stats", "/api/admin/export.csv", "/api/admin/leads.csv"):
        assert client.get(path).status_code == 401
        assert client.get(path + "?token=errado").status_code == 401
    assert client.post("/api/admin/reprocessar").status_code == 401
    s = client.get("/api/admin/stats", headers={"x-admin-token": "segredo"}).json()
    assert "querem_conversar" in s and "na_fila_agora" in s
