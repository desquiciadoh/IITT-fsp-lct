"""Unit tests for FakeLlm rule-based extraction."""
from apps.llm_gateway.fake import FakeLlm


def test_fake_llm_resume_extraction():
    llm = FakeLlm()
    cv_text = """[NAME]
Python Backend Developer
Опыт работы: 3 года
Город: Москва
Формат: удаленно, возможен гибрид
Ожидания по зарплате: от 220 000 руб на руки
Стек: Python, FastAPI, PostgreSQL, Docker, Redis, Celery
Обо мне: Разрабатываю высоконагруженные асинхронные микросервисы.
"""
    draft = llm.resume(cv_text)

    assert draft.specialization == "backend"
    assert draft.claimed_grade in ("middle", "junior")
    assert draft.years_experience == 3.0
    assert "remote" in draft.work_formats
    assert draft.salary_min == 220000
    assert draft.salary_type == "net"
    assert draft.city == "Москва"
    assert "Python" in draft.skills_raw
    assert "FastAPI" in draft.skills_raw
    assert "PostgreSQL" in draft.skills_raw


def test_fake_llm_jd_extraction():
    llm = FakeLlm()
    jd_text = """Senior Frontend Engineer (React)
Требования:
- Отличное знание JavaScript, TypeScript, React
- Опыт работы с Redux Toolkit, Next.js
Будет плюсом:
- Понимание Docker, CI/CD, Jest
Условия:
- Удаленная работа (remote)
- Зарплата от 300 000 до 400 000 руб на руки
"""
    draft = llm.jd(jd_text)

    assert draft.specialization == "frontend"
    assert "senior" in draft.grades
    assert "remote" in draft.work_formats
    assert draft.salary_min == 300000
    assert draft.salary_max == 400000
    assert draft.salary_type == "net"
    # Skills split
    assert any("React" in s or "TypeScript" in s for s in draft.must_skills_raw)
    assert any("Docker" in s or "CI/CD" in s for s in draft.nice_skills_raw)


def test_fake_llm_phrase():
    llm = FakeLlm()
    facts = [
        "Опыт разработки на Python более 4 лет",
        "Подтвержденный грейд Senior по результатам тестирования",
    ]
    res = llm.phrase(facts)
    assert "Python" in res
    assert "Senior" in res
    assert res.endswith(".")
