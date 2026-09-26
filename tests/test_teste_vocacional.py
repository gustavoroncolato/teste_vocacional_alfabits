"""Validação do teste em si (etapas 2, 3 e 4): estrutura, adaptação, personas, equilíbrio e robustez.

Ideia: se o teste é bom, uma pessoa com perfil claro (ex.: quer ser médica) tem que cair na área
certa; ruído nas respostas não pode virar o resultado; e nenhuma área pode ser favorecida por
construção (com respostas aleatórias, todas as áreas precisam aparecer em proporções parecidas).
"""
import random
from collections import Counter

import pytest

from app.questions import AREAS, DIMENSIONS, OPEN_QUESTIONS, PHASE1, PHASE2, QUESTION_INDEX
from app.scoring import area_ranking, compute_profile, dimension_scores, fallback_options, phase2_questions

DIMS = list(DIMENSIONS)


# ---------------------------------------------------------------- estrutura
def test_estrutura_do_banco_de_perguntas():
    ids = [q["id"] for q in PHASE1] + [q["id"] for qs in PHASE2.values() for q in qs]
    assert len(ids) == len(set(ids)), "ids repetidos"
    assert Counter(q["dim"] for q in PHASE1) == {d: 2 for d in DIMS}, "fase 1: 2 perguntas por perfil"
    assert set(PHASE2) == set(DIMS) and all(len(v) == 4 for v in PHASE2.values()), "fase 2: 4 por perfil"
    textos = [q["texto"] for q in QUESTION_INDEX.values()]
    assert len(textos) == len(set(textos)), "textos repetidos"
    assert len(OPEN_QUESTIONS) == 2


def test_areas_bem_definidas():
    for key, a in AREAS.items():
        assert abs(sum(a["dims"].values()) - 1) < 1e-9, f"pesos de {key} devem somar 1"
        assert set(a["dims"]) <= set(DIMS)
        assert len(a["cursos"]) >= 4 and a["motivo"]
    tags = {q["area"] for qs in PHASE2.values() for q in qs}
    assert tags == set(AREAS), "toda área precisa de pelo menos 1 pergunta específica (e só áreas válidas)"


# ---------------------------------------------------------------- adaptação (fase 2)
def _p1(levels: dict[str, int], default=2):
    return {q["id"]: levels.get(q["dim"], default) for q in PHASE1}


@pytest.mark.parametrize("fortes", [("I", "A", "S"), ("R", "C", "E"), ("S", "E", "A"), ("C", "I", "R")])
def test_fase2_pergunta_sobre_os_3_perfis_mais_fortes(fortes):
    tops, qs = phase2_questions(_p1({fortes[0]: 5, fortes[1]: 4, fortes[2]: 4}))
    assert tops[0] == fortes[0] and set(tops) == set(fortes)
    assert len(qs) == 12 and Counter(q["dim"] for q in qs) == {d: 4 for d in fortes}
    assert [q["dim"] for q in qs[:3]] == list(tops), "perguntas intercaladas, não em bloco"


def test_fase2_com_respostas_todas_iguais_e_deterministica():
    a = _p1({}, default=3)
    assert phase2_questions(a) == phase2_questions(a)
    tops, qs = phase2_questions(a)
    assert len(qs) == 12 and len(set(tops)) == 3


def test_perguntas_da_fase2_nunca_repetem_as_da_fase1():
    for _ in range(200):
        a = {q["id"]: random.randint(1, 5) for q in PHASE1}
        _, qs = phase2_questions(a)
        assert not {q["id"] for q in qs} & set(a)


# ---------------------------------------------------------------- personas
# Cada persona: nível de interesse por perfil (1-5) e por área específica.
PERSONAS = {
    "futura médica": ({"S": 5, "I": 5}, {"saude": 5, "educacao_humanas": 3, "tecnologia": 1}, "saude"),
    "dev / programador": ({"I": 5, "C": 4, "R": 3}, {"tecnologia": 5, "exatas": 3, "saude": 1, "bio_agro": 1}, "tecnologia"),
    "designer": ({"A": 5, "R": 3}, {"artes_design": 5, "comunicacao": 3, "tecnico_pratico": 1}, "artes_design"),
    "advogada": ({"E": 5, "S": 4}, {"direito_publico": 5, "negocios": 2, "educacao_humanas": 2, "saude": 1}, "direito_publico"),
    "empreendedor": ({"E": 5, "C": 4}, {"negocios": 5, "financas_gestao": 3, "direito_publico": 2}, "negocios"),
    "agrônomo": ({"R": 5, "I": 4}, {"bio_agro": 5, "engenharia": 2, "tecnico_pratico": 2, "saude": 2, "tecnologia": 1, "exatas": 2}, "bio_agro"),
    "contadora": ({"C": 5, "E": 3}, {"financas_gestao": 5, "tecnologia": 2, "negocios": 3, "tecnico_pratico": 2}, "financas_gestao"),
    "psicóloga / professora": ({"S": 5, "A": 4}, {"educacao_humanas": 5, "saude": 2, "direito_publico": 2, "artes_design": 2, "comunicacao": 3}, "educacao_humanas"),
    "engenheiro": ({"R": 5, "I": 5}, {"engenharia": 5, "exatas": 3, "tecnico_pratico": 3, "bio_agro": 1, "saude": 1, "tecnologia": 2}, "engenharia"),
    "youtuber / jornalista": ({"A": 5, "E": 4, "S": 3}, {"comunicacao": 5, "artes_design": 3, "negocios": 2, "direito_publico": 2}, "comunicacao"),
    "técnico industrial": ({"R": 5, "C": 4}, {"tecnico_pratico": 5, "engenharia": 3, "financas_gestao": 2, "bio_agro": 1, "saude": 1}, "tecnico_pratico"),
    "cientista de exatas": ({"I": 5, "C": 4}, {"exatas": 5, "tecnologia": 3, "saude": 1, "bio_agro": 1, "financas_gestao": 2}, "exatas"),
}


def responder(dims: dict, areas: dict, noise: float = 0.0, rng=random):
    def answer(qid: str) -> int:
        q = QUESTION_INDEX[qid]
        if q.get("area"):  # pergunta da fase 2
            v = areas.get(q["area"], max(1, dims.get(q["dim"], 2) - 1))
        else:
            v = dims.get(q["dim"], 2)
        if noise and rng.random() < noise:
            v += rng.choice((-1, 1))
        return min(5, max(1, v))
    return answer


def simular(dims, areas, noise=0.0, rng=random):
    answer = responder(dims, areas, noise, rng)
    respostas = {q["id"]: answer(q["id"]) for q in PHASE1}
    _, qs = phase2_questions(respostas)
    respostas.update({q["id"]: answer(q["id"]) for q in qs})
    return compute_profile(respostas)


@pytest.mark.parametrize("nome", PERSONAS)
def test_persona_cai_na_area_certa(nome):
    dims, areas, esperado = PERSONAS[nome]
    perfil = simular(dims, areas)
    top = [a["id"] for a in perfil["areas"]]
    assert top[0] == esperado, f"{nome}: esperado {esperado}, veio {top}"


@pytest.mark.parametrize("nome", PERSONAS)
def test_persona_com_ruido_continua_estavel(nome):
    """30% das respostas trocadas em ±1 (gente distraída): a área certa continua no top 3 em >= 95% dos casos."""
    dims, areas, esperado = PERSONAS[nome]
    rng = random.Random(42)
    tops = [[a["id"] for a in simular(dims, areas, 0.3, rng)["areas"]] for _ in range(300)]
    top3 = sum(esperado in t for t in tops) / 300
    top1 = sum(esperado == t[0] for t in tops) / 300
    assert top3 >= 0.95 and top1 >= 0.90, f"{nome}: top3 {top3:.0%}, top1 {top1:.0%}"


MISTOS = [
    # (perfil, áreas, duas áreas que precisam aparecer no top 3)
    ({"S": 5, "I": 4, "A": 4}, {"saude": 5, "artes_design": 5}, {"saude", "artes_design"}),
    ({"I": 5, "E": 4, "C": 4}, {"tecnologia": 5, "negocios": 5}, {"tecnologia", "negocios"}),
    ({"R": 5, "S": 4, "I": 4}, {"bio_agro": 5, "educacao_humanas": 5}, {"bio_agro", "educacao_humanas"}),
    ({"A": 5, "C": 4, "I": 4}, {"comunicacao": 5, "tecnologia": 5}, {"comunicacao", "tecnologia"}),
]


@pytest.mark.parametrize("dims,areas,esperadas", MISTOS)
def test_perfil_misto_mostra_os_dois_lados(dims, areas, esperadas):
    top = {a["id"] for a in simular(dims, areas)["areas"]}
    assert esperadas <= top, f"esperado {esperadas} no top 3, veio {top}"


def test_todas_as_areas_sao_alcancaveis():
    ganhadoras = {p[2] for p in PERSONAS.values()}
    assert ganhadoras == set(AREAS), f"áreas sem persona: {set(AREAS) - ganhadoras}"


# ---------------------------------------------------------------- equilíbrio (sem viés estrutural)
def test_respostas_aleatorias_nao_favorecem_nenhuma_area():
    rng = random.Random(7)
    n = 6000
    top1 = Counter()
    for _ in range(n):
        a = {q["id"]: rng.randint(1, 5) for q in PHASE1}
        _, qs = phase2_questions(a)
        a.update({q["id"]: rng.randint(1, 5) for q in qs})
        top1[compute_profile(a)["areas"][0]["id"]] += 1
    justo = 1 / len(AREAS)  # ~8,3%
    for area in AREAS:
        share = top1[area] / n
        assert justo * 0.45 <= share <= justo * 1.6, f"{area}: {share:.1%} (justo seria {justo:.1%})"


def test_quem_responde_tudo_igual_recebe_resultado_misto():
    a = {q["id"]: 3 for q in PHASE1}
    _, qs = phase2_questions(a)
    a.update({q["id"]: 3 for q in qs})
    p = compute_profile(a)
    assert len({x["id"] for x in p["areas"]}) == 3


# ---------------------------------------------------------------- coerência da pontuação
def test_pontuacao_de_0_a_100():
    assert dimension_scores({q["id"]: 1 for q in PHASE1}) == {d: 0.0 for d in DIMS}
    assert dimension_scores({q["id"]: 5 for q in PHASE1}) == {d: 100.0 for d in DIMS}


def test_monotonicidade_subir_resposta_nunca_baixa_a_area_ligada():
    """Se a pessoa aumenta a nota de uma pergunta ligada à área X, a pontuação de X não pode cair."""
    rng = random.Random(3)
    for _ in range(300):
        a = {q["id"]: rng.randint(1, 5) for q in PHASE1}
        _, qs = phase2_questions(a)
        a.update({q["id"]: rng.randint(1, 4) for q in qs})
        q = rng.choice(qs)
        area = QUESTION_INDEX[q["id"]]["area"]
        antes = {x["id"]: x["score"] for x in area_ranking(a, dimension_scores(a))}[area]
        b = {**a, q["id"]: a[q["id"]] + 1}
        depois = {x["id"]: x["score"] for x in area_ranking(b, dimension_scores(b))}[area]
        assert depois >= antes


def test_fallback_sempre_tem_3_cursos_diferentes_com_motivo():
    rng = random.Random(11)
    for _ in range(200):
        a = {q["id"]: rng.randint(1, 5) for q in PHASE1}
        _, qs = phase2_questions(a)
        a.update({q["id"]: rng.randint(1, 5) for q in qs})
        ops = fallback_options(compute_profile(a))
        assert len(ops) == 3 and len({o["curso"] for o in ops}) == 3
        assert all(len(o["motivo"]) > 20 for o in ops)
