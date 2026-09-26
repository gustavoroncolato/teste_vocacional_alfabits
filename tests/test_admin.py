"""Tela /admin: login, bloqueio exponencial por senha errada e dados completos de cada aluno."""
from app import admin_auth
from tests.conftest import patch_settings, run_full_test, wait_status

LOGIN = {"usuario": "admin", "senha": "senha-teste"}


def _login(client, **kw):
    return client.post("/api/admin/login", json={**LOGIN, **kw})


def test_pagina_admin_abre_e_dados_exigem_login(client):
    r = client.get("/admin")
    assert r.status_code == 200 and "noindex" in r.headers["x-robots-tag"]
    assert client.get("/api/admin/participantes").status_code == 401


def test_login_libera_painel_e_logout_encerra(client):
    r = _login(client)
    assert r.status_code == 200
    cookie = r.headers["set-cookie"].lower()
    assert "httponly" in cookie and "samesite=strict" in cookie
    assert client.get("/api/admin/participantes").status_code == 200
    assert client.get("/api/admin/leads.csv").status_code == 200  # planilhas também usam a sessão
    client.post("/api/admin/logout")
    assert client.get("/api/admin/participantes").status_code == 401


def test_senha_errada_bloqueia_3_min_e_multiplica_por_3(client, monkeypatch):
    agora = [1000.0]
    monkeypatch.setattr(admin_auth.time, "time", lambda: agora[0])

    r = _login(client, senha="errada")
    assert r.status_code == 401 and r.json()["espera"] == 180
    # durante o bloqueio nem a senha certa entra
    r = _login(client)
    assert r.status_code == 429 and 0 < r.json()["espera"] <= 180

    agora[0] += 181
    assert _login(client, senha="errada").json()["espera"] == 540  # 9 min
    agora[0] += 541
    assert _login(client, usuario="outro").json()["espera"] == 1620  # 27 min
    agora[0] += 1621
    assert _login(client).status_code == 200  # acertou: zera o contador
    client.post("/api/admin/logout")
    assert _login(client, senha="errada").json()["espera"] == 180


def test_bloqueio_tem_teto_de_24h(client, monkeypatch):
    agora = [0.0]
    monkeypatch.setattr(admin_auth.time, "time", lambda: agora[0])
    for _ in range(12):
        espera = _login(client, senha="errada").json()["espera"]
        agora[0] += espera + 1
    assert espera == 24 * 3600


def test_participantes_traz_tudo_do_aluno(client):
    pid, res = run_full_test(client)
    wait_status(pid)
    tok = res["token"]
    for tipo, extra in (("abriu_pagina", {}), ("abriu_pagina", {"dono": False}), ("compartilhou", {"detalhe": "nativo"}),
                        ("salvou_pdf", {}), ("clicou_conversar", {})):
        client.post("/api/evento", json={"token": tok, "tipo": tipo, **extra})
    cursos = client.get(f"/api/resultado/{tok}").json()["cursos"]
    client.post("/api/interesse", json={"token": tok, "curso": cursos[0]["curso"], "periodo": "tarde", "quem": "aluno"})

    assert _login(client).status_code == 200
    out = client.get("/api/admin/participantes").json()
    p = next(x for x in out["participantes"] if x["id"] == pid)
    assert p["nome"] == "Maria Souza" and p["idade"] >= 17 and p["telefone"] == "5518998765432"
    assert p["cidade"] == "Pirapozinho" and p["escola"] == "EE Professor Exemplo" and p["serie"].startswith("3º")
    assert p["aceita_contato"] is True and len(p["cursos"]) == 3 and len(p["perfil"]) == 3
    assert p["views_aluno"] == 1 and p["views_outros"] == 1 and p["pdf"] == 1 and p["clicou_conversar"] == 1
    assert p["compartilhou"] == 1 and p["compartilhou_como"] == ["nativo"]
    assert p["interesse"]["periodo"] == "tarde" and p["temperatura"] == "quente"
    assert len(p["respostas"]) == 24 and all(r["pergunta"] and r["resposta"] for r in p["respostas"])
    assert p["abertas"][0]["resposta"] == "gosto de desenhar e jogar bola"
    assert p["link"] == f"/r/{tok}" and p["ultima_visita"]
    assert out["stats"]["querem_conversar"] >= 1


def test_login_desativado_sem_senha_configurada(client, monkeypatch):
    patch_settings(monkeypatch, admin_password="")
    assert _login(client).status_code == 401
