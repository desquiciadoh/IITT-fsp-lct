"""Unit tests for FakeLlm rule-based extraction and AI-R6 regressions."""
from llm_gateway.fake import FakeLlm


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


def test_fake_llm_air6_regressions():
    llm = FakeLlm()

    # 1. Experience vs salary range: опыт от 3 до 5 лет ... зарплата от 300 000 до 400 000
    jd1 = "Требуется инженер. Опыт от 3 до 5 лет. Зарплата от 300 000 до 400 000 руб."
    draft1 = llm.jd(jd1)
    assert draft1.salary_min == 300000
    assert draft1.salary_max == 400000

    # 2. Cyrillic k / к suffix: от 150к до 250к
    jd2 = "Зарплатная вилка от 150к до 250к на руки."
    draft2 = llm.jd(jd2)
    assert draft2.salary_min == 150000
    assert draft2.salary_max == 250000
    assert draft2.salary_type == "net"

    # 3. Gross vs .NET/Kubernetes
    jd3 = "Зарплата от 300 000 руб gross. Стек: Kubernetes, .NET Core."
    draft3 = llm.jd(jd3)
    assert draft3.salary_min == 300000
    assert draft3.salary_type == "gross"

    # 4. Specialization scoring: Header 'Backend developer' outweighs body mention of 'React'
    cv4 = """[NAME]
Backend developer
Опыт 4 года
Знаю немного React для личных проектов, но основной профиль backend на Python.
"""
    draft4 = llm.resume(cv4)
    assert draft4.specialization == "backend"

    # 5. Grade: Ignore 'под руководством senior', derive from 1 year experience -> junior
    cv5 = """[NAME]
Leading projects под руководством senior архитектора.
Опыт 1 год в стартапе.
"""
    draft5 = llm.resume(cv5)
    assert draft5.claimed_grade == "junior"

    # 6. Empty JD defaults
    draft6 = llm.jd("")
    assert draft6.title is None
    assert draft6.specialization is None
    assert draft6.grades == []
    assert draft6.work_formats == []
    assert draft6.salary_type is None
