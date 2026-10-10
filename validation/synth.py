"""Synthetic world for the demo seed and the matching benchmark (ML-7):  python -m validation.synth

Latent truth per candidate: specialization, ability θ ~ N(0, 1) (the CAT scale), per-skill
proficiency, an inflation tendency. Observables are derived from it the way a real platform
would see them:
  - declared skills with omissions and inflation, a claimed grade shifted by inflation;
  - a qualification run through the production IrtCatEngine with simulated answers on
    perturbed item parameters (validation.simulate); ~8 % never took the test (pending);
  - verified-by-test skills from the session (assessment.engine.topics.verified_skills);
  - FSP history for ~35 %, more likely and better placed for higher θ, in the registry contract
    of ARCHITECTURE §2.8;
  - salary expectations by grade and city (gross or net), work formats, activity, CV text;
  - Strength and percentile per league from matching.engine.strength.
Plus 12 fictional companies, 60 positions with JD texts, and the hero personas.

Everything is a deterministic function of the seed (string-seeded random.Random streams per
entity, fixed AS_OF date). The app never reads validation/data/truth.jsonl.
"""
from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import math
import random
import sys
from dataclasses import dataclass, field
from pathlib import Path

from assessment.engine.cat import IrtCatEngine
from assessment.engine.content import load_content
from assessment.engine.topics import verified_skills
from assessment.families.base import GRADES, SPECS
from assessment.families.registry import active_metas
from matching.engine.salary import to_net
from matching.engine.strength import strength
from matching.engine.types import CandidateCtx, FspResultCtx, SkillEvidence

from .simulate import perturbed_params, run_session

ROOT = Path(__file__).resolve().parents[1]
SEED_DIR = ROOT / "seed_data" / "full"
TRUTH_PATH = ROOT / "validation" / "data" / "truth.jsonl"
AS_OF = datetime.datetime(2026, 10, 10, 12, 0, tzinfo=datetime.UTC)
SCHEMA_VERSION = 1

SPEC_SHARE = {"backend": 0.45, "frontend": 0.35, "ml_data": 0.20}
EXTRA_SKILLS = {
    "backend": ("docker", "git", "linux", "kubernetes", "kafka", "rabbitmq", "django", "fastapi", "golang",
                "java", "spring_boot", "grpc", "microservices", "nginx", "ci_cd"),
    "frontend": ("vue", "angular", "nextjs", "webpack", "vite", "jest", "storybook", "sass", "redux",
                 "tailwindcss", "git", "graphql", "playwright", "cypress", "html"),
    "ml_data": ("pytorch", "tensorflow", "scikit_learn", "pandas", "numpy", "airflow", "spark", "mlflow",
                "catboost", "xgboost", "lightgbm", "llm", "nlp", "computer_vision", "git"),
}
CITIES = (("Москва", "Europe/Moscow", 1.0, 0.30), ("Санкт-Петербург", "Europe/Moscow", 0.9, 0.18),
          ("Казань", "Europe/Moscow", 0.72, 0.08), ("Новосибирск", "Asia/Novosibirsk", 0.75, 0.08),
          ("Екатеринбург", "Asia/Yekaterinburg", 0.75, 0.08), ("Нижний Новгород", "Europe/Moscow", 0.7, 0.06),
          ("Краснодар", "Europe/Moscow", 0.68, 0.06), ("Самара", "Europe/Samara", 0.66, 0.05),
          ("Пермь", "Asia/Yekaterinburg", 0.65, 0.05), ("Томск", "Asia/Tomsk", 0.68, 0.06))
BASE_GROSS = {"intern": 60_000, "junior": 120_000, "middle": 220_000, "senior": 350_000}
FIRST = ("Анна", "Алексей", "Мария", "Иван", "Елена", "Дмитрий", "Ольга", "Максим", "Наталья", "Сергей",
         "Татьяна", "Андрей", "Юлия", "Никита", "Ксения", "Павел", "Дарья", "Артём", "Полина", "Егор",
         "Вера", "Кирилл", "Алина", "Роман", "Софья", "Глеб", "Арина", "Тимур", "Ева", "Лев")
LAST = ("Смирнов", "Иванов", "Кузнецов", "Попов", "Васильев", "Петров", "Соколов", "Михайлов", "Новиков",
        "Фёдоров", "Морозов", "Волков", "Алексеев", "Лебедев", "Семёнов", "Егоров", "Павлов", "Козлов",
        "Степанов", "Николаев", "Орлов", "Андреев", "Макаров", "Никитин", "Захаров")
FEMALE = {"Анна", "Мария", "Елена", "Ольга", "Наталья", "Татьяна", "Юлия", "Ксения", "Дарья", "Полина", "Вера",
          "Алина", "Софья", "Арина", "Ева"}
DISCIPLINES = ("algorithmic", "product", "infosec", "robotics", "uas")
EVENTS = ("Чемпионат России по спортивному программированию", "Кубок России", "Всероссийские соревнования",
          "Первенство федерального округа", "Чемпионат региона", "Открытый кубок ФСП")
COMPANIES = (("Полярный код", "polar-code.example"), ("Северные системы", "sever-sys.example"),
             ("ТехноГрад", "technograd.example"), ("Квант Софт", "kvant-soft.example"),
             ("Байкал Дата", "baikal-data.example"), ("Волга Финтех", "volga-fintech.example"),
             ("Уральский облачный", "ural-cloud.example"), ("Невский продукт", "nevsky-product.example"),
             ("Сибирь ИИ", "sibir-ai.example"), ("Кремень Тех", "kremen-tech.example"),
             ("Лаборатория Ока", "oka-lab.example"), ("Амур Логистика", "amur-log.example"))


def _rng(seed: int, *parts) -> random.Random:
    return random.Random("|".join(str(p) for p in (seed, *parts)))


def _sigmoid(x: float) -> float:
    return 1 / (1 + math.exp(-x))


def band_of(theta: float) -> str:
    cuts = load_content().band_cuts
    return GRADES[sum(theta >= c for c in cuts)]


def spec_skills(spec: str) -> tuple[str, ...]:
    content = load_content()
    pool = {s for t in content.topics_for(spec) for s in content.topics[t].skills} | set(EXTRA_SKILLS[spec])
    return tuple(sorted(pool))


@dataclass
class World:
    seed: int
    candidates: list[dict] = field(default_factory=list)
    assessments: list[dict] = field(default_factory=list)
    leagues: list[dict] = field(default_factory=list)
    fsp: list[dict] = field(default_factory=list)
    companies: list[dict] = field(default_factory=list)
    positions: list[dict] = field(default_factory=list)
    truth: list[dict] = field(default_factory=list)


# ── heroes (README §8 personas + Ivan), injected with fixed latent truth ─────

HEROES = [
    {"key": "anna", "name": "Анна Соколова", "email": "anna.fsp@example.com", "spec": "backend", "theta": 2.0,
     "claim": "senior", "fsp": {"rank": "kms", "results": [("prize_winner", "algorithmic", 2), ("winner", "product", 1)]},
     "city": 0, "inflation": 0.1},
    {"key": "alex", "name": "Алексей Петров", "email": "alex.dev@example.com", "spec": "backend", "theta": 0.55,
     "claim": "middle", "fsp": None, "city": 1, "inflation": 0.2},
    {"key": "elena", "name": "Елена Морозова", "email": "elena.junior@example.com", "spec": "backend", "theta": -0.15,
     "claim": "junior", "fsp": None, "city": 2, "inflation": 0.2},
    {"key": "dmitry", "name": "Дмитрий Волков", "email": "dmitry.unconfirmed@example.com", "spec": "backend",
     "theta": -0.2, "claim": "senior", "fsp": None, "city": 0, "inflation": 0.9},
    {"key": "maksim", "name": "Максим Орлов", "email": "maksim.fsp@example.com", "spec": "backend", "theta": 0.6,
     "claim": "middle", "fsp": {"rank": "kms", "results": [("finalist", "algorithmic", 7), ("participant", "infosec", 30)]},
     "city": 3, "inflation": 0.2},
    {"key": "olga", "name": "Ольга Никитина", "email": "olga.fullstack@example.com", "spec": "frontend", "theta": 0.6,
     "claim": "middle", "fsp": None, "city": 1, "inflation": 0.3, "closed": True},
    {"key": "ivan", "name": "Иван Кузнецов", "email": "ivan.frontend@example.com", "spec": "frontend", "theta": 2.0,
     "claim": "senior", "fsp": {"rank": "cat1", "results": [("prize_winner", "product", 3)]}, "city": 0,
     "inflation": 0.1},
]


def build_world(seed: int = 2026, n_candidates: int = 1500, n_positions: int = 60) -> World:
    content = load_content()
    engine = IrtCatEngine(content)
    pools = {spec: active_metas(spec) for spec in SPECS}
    all_metas = {m.id: m for spec in SPECS for m in pools[spec]}
    true_params = perturbed_params(list(all_metas.values()), seed)
    world = World(seed=seed)

    people = [dict(h, hero=True) for h in HEROES] + [{"key": f"c{i:05d}", "hero": False} for i in range(n_candidates
                                                                                                        - len(HEROES))]
    for idx, person in enumerate(people):
        _make_candidate(world, person, idx, content, engine, pools, true_params)
    _attach_strength(world)
    _make_companies_and_positions(world, n_positions)
    return world


def _public_id(seed: int, key: str) -> str:
    return "C-" + hashlib.sha256(f"{seed}|{key}".encode()).hexdigest()[:8].upper()


def _make_candidate(world: World, person: dict, idx: int, content, engine, pools, true_params) -> None:
    seed = world.seed
    r = _rng(seed, "candidate", person["key"])
    hero = person["hero"]
    spec = person["spec"] if hero else r.choices(SPECS, weights=[SPEC_SHARE[s] for s in SPECS])[0]
    theta = person["theta"] if hero else r.gauss(0, 1)
    inflation = person["inflation"] if hero else r.random()
    true_grade = band_of(theta)

    # latent skills: exposure grows with ability; proficiency = sigmoid(1.2 (θ − d) + u)
    proficiency = {}
    for skill in spec_skills(spec):
        sr = _rng(seed, "skill", person["key"], skill)
        if sr.random() < min(0.9, max(0.15, 0.45 + 0.18 * theta)):
            proficiency[skill] = round(_sigmoid(1.2 * (theta - sr.gauss(-0.4, 0.7)) + sr.gauss(0, 0.6)), 4)

    # declared: omissions for weak-but-real skills, inflation adds skills the person barely has
    declared = sorted(s for s, p in proficiency.items() if p >= 0.45 and r.random() < 0.85)
    for skill in spec_skills(spec):
        if skill not in declared and r.random() < 0.05 + 0.12 * inflation:
            declared.append(skill)
    declared = sorted(set(declared))

    claim_theta = theta + 0.9 * (inflation - 0.4) + r.gauss(0, 0.35)
    claimed = person["claim"] if hero else band_of(claim_theta)
    city_i = person.get("city", r.choices(range(len(CITIES)), weights=[c[3] for c in CITIES])[0])
    city, tz, city_mult, _ = CITIES[city_i]
    years = max(0.0, round(2.5 + 2.4 * theta + r.gauss(0, 1.0), 1))

    public_id = _public_id(seed, person["key"])
    tested = hero or r.random() >= 0.08
    league = None
    verified: list[str] = []
    if tested:
        out = run_session(engine, pools[spec], true_params, spec, claimed, theta, session_id=public_id)
        res = out.result
        skills_by_family = {m.id: m.skills for m in pools[spec]}
        verified = verified_skills(res.topics, out.state.administered, skills_by_family)
        world.assessments.append({
            "public_id": public_id, "specialization": spec, "claimed_grade": claimed, "kind": "initial",
            "mode": "full", "families": out.families, "theta": round(res.theta, 4), "se": round(res.se, 4),
            "rating": res.rating, "rating_ci": res.rating_ci, "result_grade": res.result_grade,
            "decision": res.decision, "promotion_unlocked": res.promotion_unlocked,
            "fallback_grade": res.fallback_grade, "complete": res.complete, "stop_reason": res.stop_reason,
            "topics": [{"topic": t, "level": lv} for t, lv in res.topics],
            "evidence": [{"seq": s, "level": lv, "correct": c} for s, lv, c in res.evidence],
            "finished_at": (AS_OF - datetime.timedelta(days=r.randint(1, 300))).date().isoformat(),
        })
        league = {"public_id": public_id, "specialization": spec, "grade": claimed,
                  "status": "confirmed" if res.decision == "confirmed" else "unconfirmed",
                  "theta": round(res.theta, 4), "se": round(res.se, 4), "rating": res.rating,
                  "topic_levels": dict(res.topics)}

    fsp = _make_fsp(world, person, public_id, theta, r) if (hero and person.get("fsp")) or (
        not hero and r.random() < min(0.85, _sigmoid(-0.85 + 0.9 * theta))) else None

    gross = BASE_GROSS[claimed] * city_mult * math.exp(r.gauss(0, 0.15)) * (1 + 0.15 * inflation)
    gross = int(round(gross / 5000) * 5000)
    salary_type = r.choice(("gross", "net"))
    smin = gross if salary_type == "gross" else int(round(to_net(gross, "gross") / 5000) * 5000)
    smax = int(round(smin * r.uniform(1.1, 1.35) / 5000) * 5000)
    formats = sorted(r.sample(("remote", "hybrid", "office"), r.randint(1, 3)))
    active_days = int(r.expovariate(1 / 20))
    microtasks = sorted((AS_OF - datetime.timedelta(days=r.randint(1, 200))).date().isoformat()
                        for _ in range(r.randint(1, 4))) if r.random() < 0.15 else []

    name = person.get("name") or _name(r)
    world.candidates.append({
        "public_id": public_id, "email": person.get("email") or f"{public_id.lower()}@example.com",
        "full_name": name, "specialization": spec, "claimed_grade": claimed, "years_experience": years,
        "skills": [{"skill_id": s, "source": "declared"} for s in declared]
                  + [{"skill_id": s, "source": "test"} for s in verified]
                  + ([{"skill_id": "algorithms", "source": "fsp"}]
                     if fsp and any(x["discipline"] == "algorithmic" for x in fsp["results"]) else []),
        "salary_min": smin, "salary_max": smax, "salary_type": salary_type, "work_formats": formats,
        "city": city, "timezone": tz, "open_to_offers": not person.get("closed", False),
        "last_active_at": (AS_OF - datetime.timedelta(days=active_days)).isoformat(),
        "microtask_dates": microtasks, "fsp_participant_id": fsp["participant_id"] if fsp else None,
        "cv_text": _cv_text(r, spec, claimed, years, declared, city), "hero": person["key"] if hero else None,
        "consents": {"processing": True, "publication": True, "fsp_sync": bool(fsp)},
    })
    if league:
        world.leagues.append(league)
    world.truth.append({
        "public_id": public_id, "specialization": spec, "theta": round(theta, 4), "true_grade": true_grade,
        "inflation": round(inflation, 4), "proficiency": proficiency, "claimed_grade": claimed,
        "tested": tested, "hero": person["key"] if hero else None,
    })


def _name(r: random.Random) -> str:
    first, last = r.choice(FIRST), r.choice(LAST)
    return f"{first} {last + ('а' if first in FEMALE else '')}"


def _make_fsp(world: World, person: dict, public_id: str, theta: float, r: random.Random) -> dict:
    pid = f"FSP-{int(hashlib.sha256(public_id.encode()).hexdigest(), 16) % 1_000_000:06d}"
    if person["hero"]:
        spec = person["fsp"]
        rank, rows = spec["rank"], spec["results"]
    else:
        rank_score = theta + r.gauss(0, 0.6)
        rank = ("ms" if rank_score > 2.2 else "kms" if rank_score > 1.5 else "cat1" if rank_score > 0.9
                else "cat2" if rank_score > 0.3 else "cat3" if rank_score > -0.3 else None)
        rows = []
        for _ in range(1 + min(5, int(r.expovariate(0.9)))):
            q = theta + r.gauss(0, 0.8)
            tier = ("winner" if q > 2.0 else "prize_winner" if q > 1.2 else "finalist" if q > 0.4 else "participant")
            place = {"winner": 1, "prize_winner": r.randint(2, 3), "finalist": r.randint(4, 12),
                     "participant": r.randint(13, 150)}[tier]
            rows.append((tier, r.choice(DISCIPLINES), place))
    results = []
    for k, (tier, disc, place) in enumerate(rows):
        date = (AS_OF - datetime.timedelta(days=r.randint(30, 1100))).date()
        team = disc in ("product", "robotics", "uas")
        results.append({
            "event_id": f"EV-{date.year}-{pid[-6:]}-{k:02d}",
            "event_name": f"{r.choice(EVENTS)} {date.year}", "date": date.isoformat(), "discipline": disc,
            "stage": "final" if tier != "participant" else r.choice(("qualification", "final")),
            "format": "team" if team else "individual",
            "team": {"name": f"Команда {r.randint(1, 999)}", "size": r.randint(2, 5)} if team else None,
            "placement": place, "placement_tier": tier, "participants_total": max(place + r.randint(5, 200), 20),
        })
    payload = {"participant_id": pid,
               "sports_rank": {"title": rank, "awarded_at":
                               (AS_OF - datetime.timedelta(days=r.randint(60, 900))).date().isoformat()} if rank else None,
               "results": sorted(results, key=lambda x: (x["date"], x["event_id"])),
               "issued_at": AS_OF.isoformat()}
    payload["signature"] = hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    world.fsp.append({"public_id": public_id, "rank": rank, **payload})
    return payload


def _cv_text(r: random.Random, spec: str, grade: str, years: float, skills: list[str], city: str) -> str:
    role = {"backend": "Backend-разработчик", "frontend": "Frontend-разработчик", "ml_data": "ML-инженер"}[spec]
    level = {"intern": "стажёр", "junior": "junior", "middle": "middle", "senior": "senior"}[grade]
    shown = r.sample(skills, min(len(skills), r.randint(3, 8))) if skills else []
    projects = r.sample(("высоконагруженный API", "внутренняя CRM", "личный кабинет", "платёжный сервис",
                         "система рекомендаций", "дашборд аналитики", "мобильный бэкенд", "ETL-пайплайн",
                         "чат-бот поддержки", "поиск по каталогу"), 2)
    return (f"{role} ({level}), опыт {years:g} лет, {city}. Стек: {', '.join(shown) or 'не указан'}. "
            f"Проекты: {projects[0]}, {projects[1]}. Ищу команду с сильной инженерной культурой.")


def _attach_strength(world: World) -> None:
    """Strength and percentile per league, from the production formula over league θ."""
    by_id = {c["public_id"]: c for c in world.candidates}
    fsp_by_id = {f["public_id"]: f for f in world.fsp}
    groups: dict[tuple[str, str], list[dict]] = {}
    for lg in world.leagues:
        groups.setdefault((lg["specialization"], lg["grade"]), []).append(lg)
    for (_, _), members in sorted(groups.items()):
        thetas = [m["theta"] for m in members]
        for m in members:
            ctx = to_candidate_ctx(by_id[m["public_id"]], m, fsp_by_id.get(m["public_id"]))
            sb = strength(ctx, thetas, AS_OF)
            m.update({"percentile": round(sb.percentile, 2), "base_strength": round(sb.base, 2),
                      "fsp_boost": round(sb.fsp_boost, 2), "strength": round(sb.total, 2)})


def to_candidate_ctx(c: dict, league: dict | None, fsp: dict | None) -> CandidateCtx:
    """Public rows -> the matching DTO (what BE's batch loader will build from the DB)."""
    results = tuple(FspResultCtx(r["placement_tier"], datetime.date.fromisoformat(r["date"]), r["discipline"],
                                 r["participants_total"], (r["team"] or {}).get("size")) for r in (fsp or {}).get("results", []))
    return CandidateCtx(
        public_id=c["public_id"], specialization=c["specialization"],
        league_grade=league["grade"] if league else None, league_status=league["status"] if league else "pending",
        theta=league["theta"] if league else None, se=league["se"] if league else None,
        rating=league["rating"] if league else None, percentile=(league or {}).get("percentile"),
        strength=(league or {}).get("strength"),
        skills=tuple(SkillEvidence(s["skill_id"], s["source"], 1.0) for s in c["skills"]),
        topic_levels=dict((league or {}).get("topic_levels", {})), fsp_rank=(fsp or {}).get("rank"),
        fsp_results=results, salary_min=c["salary_min"], salary_max=c["salary_max"], salary_type=c["salary_type"],
        work_formats=tuple(c["work_formats"]), city=c["city"], timezone=c["timezone"],
        last_active_at=datetime.datetime.fromisoformat(c["last_active_at"]),
        microtask_dates=tuple(datetime.date.fromisoformat(d) for d in c["microtask_dates"]))


# ── companies and positions ────────────────────────────────────────────────

def _make_companies_and_positions(world: World, n_positions: int) -> None:
    seed = world.seed
    for i, (name, domain) in enumerate(COMPANIES):
        world.companies.append({"company_id": f"CO-{i + 1:02d}", "name": name, "domain": domain,
                                "trust_level": "domain" if i % 3 else "verified",
                                "budget_factor": round(_rng(seed, "company", i).uniform(0.85, 1.2), 3)})
    content = load_content()
    for j in range(n_positions):
        r = _rng(seed, "position", j)
        company = world.companies[j % len(world.companies)]
        spec = r.choices(SPECS, weights=[SPEC_SHARE[s] for s in SPECS])[0]
        grade = r.choices(GRADES, weights=(0.08, 0.3, 0.4, 0.22))[0]
        grades = [grade] + ([GRADES[GRADES.index(grade) + 1]] if grade != "senior" and r.random() < 0.3 else [])
        pool = list(spec_skills(spec))
        core = sorted({s for t in content.topics_for(spec) for s in content.topics[t].skills} & set(pool))
        must = sorted(r.sample(core, r.randint(2, 3)) + r.sample([s for s in pool if s not in core], r.randint(0, 1)))
        nice = sorted(r.sample([s for s in pool if s not in must], r.randint(1, 3)))
        city, _, mult, _ = CITIES[r.choices(range(len(CITIES)), weights=[c[3] for c in CITIES])[0]]
        top = BASE_GROSS[grades[-1]] * mult * company["budget_factor"] * r.uniform(1.0, 1.35)
        smax = int(round(top / 10_000) * 10_000)
        smin = int(round(smax * r.uniform(0.7, 0.85) / 10_000) * 10_000)
        stype = r.choice(("gross", "net"))
        if stype == "net":
            smin, smax = (int(round(to_net(x, "gross") / 10_000) * 10_000) for x in (smin, smax))
        formats = sorted(r.sample(("remote", "hybrid", "office"), r.randint(1, 3)))
        title = {"backend": "Backend-разработчик", "frontend": "Frontend-разработчик", "ml_data": "ML-инженер"}[spec]
        title = f"{grade.capitalize()} {title}"
        world.positions.append({
            "position_id": f"P-{j + 1:03d}", "company_id": company["company_id"], "title": title,
            "specialization": spec, "grades": grades, "allow_adjacent": r.random() < 0.35,
            "must_skills": must, "nice_skills": nice, "work_formats": formats, "location": city,
            "salary_min": smin, "salary_max": smax, "salary_type": stype,
            "preset": r.choice(("balanced", "balanced", "skills", "budget")),
            "description": (f"{company['name']} ищет: {title.lower()}. Обязательно: {', '.join(must)}. "
                            f"Будет плюсом: {', '.join(nice)}. Формат: {', '.join(formats)}, {city}. "
                            f"Вилка {smin:,}–{smax:,} ₽ {stype}.".replace(",", " ")),
        })


# ── output ─────────────────────────────────────────────────────────────────

FILES = ("candidates", "assessments", "leagues", "fsp_registry", "companies", "positions")


def write_world(world: World, seed_dir: Path = SEED_DIR, truth_path: Path = TRUTH_PATH) -> dict:
    seed_dir.mkdir(parents=True, exist_ok=True)
    truth_path.parent.mkdir(parents=True, exist_ok=True)
    rows = {"candidates": world.candidates, "assessments": world.assessments, "leagues": world.leagues,
            "fsp_registry": world.fsp, "companies": world.companies, "positions": world.positions}
    digests = {}
    for name in FILES:
        text = "".join(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n" for r in rows[name])
        (seed_dir / f"{name}.jsonl").write_text(text, encoding="utf-8", newline="\n")
        digests[name] = hashlib.sha256(text.encode()).hexdigest()
    truth = "".join(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n" for r in world.truth)
    truth_path.write_text(truth, encoding="utf-8", newline="\n")
    manifest = {"schema_version": SCHEMA_VERSION, "seed": world.seed, "as_of": AS_OF.isoformat(),
                "counts": {k: len(v) for k, v in rows.items()}, "sha256": digests,
                "truth_sha256": hashlib.sha256(truth.encode()).hexdigest()}
    (seed_dir / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
                                            encoding="utf-8", newline="\n")
    return manifest


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Generate the synthetic world (seed_data/full + hidden truth).")
    ap.add_argument("--seed", type=int, default=2026)
    ap.add_argument("--candidates", type=int, default=1500)
    ap.add_argument("--positions", type=int, default=60)
    args = ap.parse_args(argv)
    manifest = write_world(build_world(args.seed, args.candidates, args.positions))
    sys.stdout.write(json.dumps(manifest["counts"], ensure_ascii=False) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
