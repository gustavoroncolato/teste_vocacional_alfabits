"""Cálculo determinístico do perfil (não depende do LLM)."""
from __future__ import annotations

from .questions import AREAS, DIMENSIONS, PHASE1, PHASE2, QUESTION_INDEX

DIM_ORDER = list(DIMENSIONS.keys())


def _norm(mean: float) -> float:
    """Converte média de 1..5 para 0..100."""
    return round((mean - 1) / 4 * 100, 1)


def dimension_scores(answers: dict[str, int]) -> dict[str, float]:
    buckets: dict[str, list[int]] = {d: [] for d in DIM_ORDER}
    for qid, val in answers.items():
        q = QUESTION_INDEX.get(qid)
        if q:
            buckets[q["dim"]].append(val)
    return {d: (_norm(sum(v) / len(v)) if v else 0.0) for d, v in buckets.items()}


def top_dimensions(scores: dict[str, float], n: int = 3) -> list[str]:
    # desempate estável pela ordem RIASEC
    return sorted(DIM_ORDER, key=lambda d: (-scores[d], DIM_ORDER.index(d)))[:n]


def phase2_questions(phase1_answers: dict[str, int]) -> tuple[list[str], list[dict]]:
    scores = dimension_scores({k: v for k, v in phase1_answers.items() if k in {q["id"] for q in PHASE1}})
    tops = top_dimensions(scores, 3)
    qs: list[dict] = []
    # intercala as dimensões para não ficar repetitivo
    for i in range(4):
        for d in tops:
            q = PHASE2[d][i]
            qs.append({"id": q["id"], "dim": d, "texto": q["texto"]})
    return tops, qs


def area_ranking(answers: dict[str, int], dim_scores: dict[str, float]) -> list[dict]:
    area_answers: dict[str, list[int]] = {}
    for qid, val in answers.items():
        q = QUESTION_INDEX.get(qid)
        if q and q.get("area"):
            area_answers.setdefault(q["area"], []).append(val)

    ranking = []
    for key, area in AREAS.items():
        dim_part = sum(dim_scores[d] * w for d, w in area["dims"].items())
        if key in area_answers:
            vals = area_answers[key]
            specific = _norm(sum(vals) / len(vals))
            score = 0.5 * dim_part + 0.5 * specific
        else:
            score = dim_part * 0.85  # sem pergunta específica respondida: leve penalidade
        ranking.append({"id": key, "nome": area["nome"], "score": round(score, 1), "cursos": area["cursos"]})
    ranking.sort(key=lambda a: -a["score"])
    return ranking


def compute_profile(answers: dict[str, int]) -> dict:
    scores = dimension_scores(answers)
    tops = top_dimensions(scores, 3)
    areas = area_ranking(answers, scores)
    return {
        "dimensoes": [
            {"id": d, "nome": DIMENSIONS[d]["nome"], "score": scores[d]} for d in top_dimensions(scores, 6)
        ],
        "codigo": "".join(tops),
        "top_dimensoes": tops,
        "areas": areas[:3],
        "candidatas": areas[:5],  # opções que o LLM pode usar
    }


def area_of_course(curso: str) -> str | None:
    for key, area in AREAS.items():
        if curso in area["cursos"]:
            return key
    return None


def fallback_options(profile: dict) -> list[dict]:
    """3 opções determinísticas (1 curso por área) usadas se o LLM falhar."""
    return [
        {"curso": a["cursos"][0], "motivo": f"Combina com você porque {AREAS[a['id']]['motivo']}.", "area": a["id"]}
        for a in profile["areas"][:3]
    ]


def fallback_detail(area_id: str | None) -> dict:
    """Conteúdo básico (escrito por nós) para quando o LLM não consegue gerar os detalhes do curso."""
    a = AREAS.get(area_id or "", {})
    return {
        "duracao": "",
        "dia_a_dia": a.get("dia_a_dia", ""),
        "onde_trabalha": a.get("onde_trabalha", []),
        "dicas": a.get("dicas", []),
        "curiosidades": [],
        "fonte": "padrao",
    }
