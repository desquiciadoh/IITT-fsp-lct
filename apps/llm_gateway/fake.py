"""Rule-based Fake LLM implementation.

Permanent fallback and CI default.
Extracts fields from resume and JD texts using regex heuristics and taxonomy rules.
"""
from __future__ import annotations

import re
from typing import Any

from apps.taxonomy import extract_skills, load_skills
from .types import JdDraft, ResumeDraft


class FakeLlm:
    """Rule-based LLM gateway implementation."""

    name: str = "fake"

    def resume(self, redacted_text: str) -> ResumeDraft:
        """Extract resume draft using regex and taxonomy heuristics."""
        lowered = redacted_text.lower()

        # 1. Extract skills from taxonomy
        matches, _ = extract_skills(redacted_text)
        skills_raw = [m.name for m in matches]

        # 2. Infer specialization
        specialization = self._infer_specialization(lowered, matches)

        # 3. Infer years of experience
        years_exp = self._extract_years_experience(lowered)

        # 4. Infer grade (intern, junior, middle, senior)
        claimed_grade = self._infer_grade(lowered, years_exp)

        # 5. Infer salary and salary_type
        sal_min, sal_max, sal_type = self._extract_salary(lowered)

        # 6. Infer work formats (office, hybrid, remote)
        work_formats = self._extract_work_formats(lowered)

        # 7. Infer city
        city = self._extract_city(lowered)

        # 8. Infer roles
        roles = self._extract_roles(redacted_text, specialization)

        # 9. Clean about & experience_text
        about = self._extract_about(redacted_text)

        return ResumeDraft(
            specialization=specialization,
            claimed_grade=claimed_grade,
            years_experience=years_exp,
            roles=roles,
            skills_raw=skills_raw,
            work_formats=work_formats,
            salary_min=sal_min,
            salary_max=sal_max,
            salary_type=sal_type,
            city=city,
            about=about,
            experience_text=redacted_text[:1500] if redacted_text else None,
        )

    def jd(self, text: str) -> JdDraft:
        """Extract job description draft using regex heuristics."""
        lowered = text.lower()

        # 1. Split text into "must" and "nice" sections if present
        must_skills_raw, nice_skills_raw = self._extract_jd_skills(text)

        # 2. Extract title & specialization
        title = self._extract_jd_title(text)
        all_matches, _ = extract_skills(text)
        specialization = self._infer_specialization(lowered, all_matches)

        # 3. Extract grades
        grades = self._extract_jd_grades(lowered)

        # 4. Extract work formats & location
        work_formats = self._extract_work_formats(lowered)
        location = self._extract_city(lowered)

        # 5. Extract salary
        sal_min, sal_max, sal_type = self._extract_salary(lowered)

        return JdDraft(
            title=title,
            specialization=specialization,
            grades=grades,
            must_skills_raw=must_skills_raw,
            nice_skills_raw=nice_skills_raw,
            work_formats=work_formats,
            location=location,
            salary_min=sal_min,
            salary_max=sal_max,
            salary_type=sal_type,
            team_context=None,
            description=text[:2000] if text else None,
        )

    def phrase(self, facts: list[str]) -> str:
        """Combine factual statements into Russian summary sentences."""
        if not facts:
            return "Кандидат соответствует ключевым требованиям позиции."

        clean_facts = [f.strip().rstrip(".") for f in facts if f.strip()]
        if not clean_facts:
            return "Кандидат соответствует ключевым требованиям позиции."

        if len(clean_facts) == 1:
            return f"Кандидат подходит на позицию: {clean_facts[0].lower()}."

        joined = ", ".join(clean_facts[:-1]) + f" и {clean_facts[-1]}"
        return f"Сильные стороны кандидата: {joined}."

    # ── Helpers ──

    def _infer_specialization(self, lowered: str, matches: list[Any]) -> str:
        """Infer backend | frontend | ml_data from text and matched skills."""
        # Keyword checks
        if any(w in lowered for w in ("ml engineer", "data scientist", "machine learning", "дата саентист", "nlp", "computer vision")):
            return "ml_data"
        if any(w in lowered for w in ("frontend", "фронтенд", "react", "vue", "angular", "верстальщик")):
            return "frontend"
        if any(w in lowered for w in ("backend", "бэкенд", "бэкендер", "django", "fastapi", "spring", "golang")):
            return "backend"

        # Topic counts from matched skills
        catalog = load_skills()
        topic_counts = {"backend": 0, "frontend": 0, "ml_data": 0}
        for m in matches:
            entry = catalog.get(m.skill_id)
            if not entry:
                continue
            t = entry.topic
            if t.startswith("backend") or t.startswith("infrastructure"):
                topic_counts["backend"] += 1
            elif t.startswith("frontend"):
                topic_counts["frontend"] += 1
            elif t.startswith("ml"):
                topic_counts["ml_data"] += 1

        top_spec = max(topic_counts, key=topic_counts.get)  # type: ignore
        if topic_counts[top_spec] > 0:
            return top_spec
        return "backend"

    def _extract_years_experience(self, lowered: str) -> float | None:
        """Extract experience in years from text."""
        # e.g. "опыт 3 года", "опыт работы: 5 лет", "4.5 года"
        m = re.search(r"опыт(?:а|\s+работы)?\s*(?:составляет)?\s*[:—\-]?\s*(\d+(?:[.,]\d+)?)\s*(?:лет|года|год|г)", lowered)
        if m:
            val = m.group(1).replace(",", ".")
            try:
                return float(val)
            except ValueError:
                pass

        # "X лет опыта"
        m2 = re.search(r"(\d+(?:[.,]\d+)?)\s*(?:лет|года|год)\s+опыта", lowered)
        if m2:
            val = m2.group(1).replace(",", ".")
            try:
                return float(val)
            except ValueError:
                pass

        # Date range e.g. 2019 — 2024
        ranges = re.findall(r"\b(20[0-2]\d)\s*[-—–]\s*(20[0-2]\d|наст|по сей день|present)\b", lowered)
        if ranges:
            total_years = 0
            for start_y, end_y in ranges:
                try:
                    s = int(start_y)
                    e = 2026 if not end_y.isdigit() else int(end_y)
                    if e >= s:
                        total_years += (e - s)
                except ValueError:
                    continue
            if total_years > 0:
                return float(min(total_years, 30))

        return None

    def _infer_grade(self, lowered: str, years: float | None) -> str:
        """Infer intern | junior | middle | senior."""
        if any(w in lowered for w in ("senior", "сеньор", "тимлид", "lead", "ведущий")):
            return "senior"
        if any(w in lowered for w in ("middle", "мидл", "миддл")):
            return "middle"
        if any(w in lowered for w in ("junior", "джуниор", "джун")):
            return "junior"
        if any(w in lowered for w in ("intern", "стажер", "стажёр")):
            return "intern"

        # Experience fallback
        if years is not None:
            if years >= 5.0:
                return "senior"
            if years >= 2.0:
                return "middle"
            if years >= 0.8:
                return "junior"
            return "intern"

        return "middle"

    def _extract_salary(self, lowered: str) -> tuple[int | None, int | None, str | None]:
        """Extract salary_min, salary_max, salary_type (gross/net)."""
        sal_type = "net" if any(w in lowered for w in ("на руки", "net", "чистыми")) else (
            "gross" if any(w in lowered for w in ("до вычета", "gross", "грязными")) else "net"
        )

        # Patterns like: "от 150 000 до 250 000", "150к - 250к", "от 200 000 руб"
        # 1. Range: от X до Y
        m_range = re.search(r"от\s*(\d[\d\s]*\d|\d+k?)\s*до\s*(\d[\d\s]*\d|\d+k?)", lowered)
        if m_range:
            s_min = self._parse_num(m_range.group(1))
            s_max = self._parse_num(m_range.group(2))
            return s_min, s_max, sal_type

        # 2. Single "от X"
        m_min = re.search(r"от\s*(\d[\d\s]*\d|\d+k?)\s*(?:руб|р|₽|k|\b)", lowered)
        if m_min:
            s_min = self._parse_num(m_min.group(1))
            if s_min and s_min > 5000:
                return s_min, None, sal_type

        # 3. Single "до Y"
        m_max = re.search(r"до\s*(\d[\d\s]*\d|\d+k?)\s*(?:руб|р|₽|k|\b)", lowered)
        if m_max:
            s_max = self._parse_num(m_max.group(1))
            if s_max and s_max > 5000:
                return None, s_max, sal_type

        return None, None, None

    def _parse_num(self, val: str) -> int | None:
        val = val.strip().lower()
        if "k" in val or "к" in val:
            num = re.sub(r"[^\d.]", "", val)
            try:
                return int(float(num) * 1000)
            except ValueError:
                return None
        cleaned = re.sub(r"\D", "", val)
        return int(cleaned) if cleaned else None

    def _extract_work_formats(self, lowered: str) -> list[str]:
        """Extract office, hybrid, remote formats."""
        formats: list[str] = []
        if any(w in lowered for w in ("удаленка", "удаленно", "удаленный", "remote")):
            formats.append("remote")
        if any(w in lowered for w in ("гибрид", "гибридный", "hybrid")):
            formats.append("hybrid")
        if any(w in lowered for w in ("офис", "office")):
            formats.append("office")
        return formats or ["remote"]

    def _extract_city(self, lowered: str) -> str | None:
        """Extract Russian cities."""
        cities = [
            ("москва", "Москва"),
            ("санкт-петербург", "Санкт-Петербург"),
            ("питер", "Санкт-Петербург"),
            ("новосибирск", "Новосибирск"),
            ("екатеринбург", "Екатеринбург"),
            ("казань", "Казань"),
            ("нижний новгород", "Нижний Новгород"),
            ("самара", "Самара"),
            ("краснодар", "Краснодар"),
            ("сочи", "Сочи"),
            ("ростов-на-дону", "Ростов-на-Дону"),
            ("минск", "Минск"),
        ]
        for c_pat, c_name in cities:
            if c_pat in lowered:
                return c_name
        return None

    def _extract_roles(self, text: str, spec: str) -> list[str]:
        """Extract target roles from resume header/title."""
        for line in text.splitlines()[:5]:
            stripped = line.strip()
            if any(w in stripped.lower() for w in ("developer", "инженер", "разработчик", "специалист", "engineer")):
                if len(stripped) < 60:
                    return [stripped]
        fallback_role = {
            "backend": "Backend Developer",
            "frontend": "Frontend Developer",
            "ml_data": "ML Engineer",
        }.get(spec, "Software Engineer")
        return [fallback_role]

    def _extract_about(self, text: str) -> str | None:
        """Extract a short <= 500 chars summary without PII placeholders."""
        # Find 'обо мне' section or first descriptive paragraph
        m = re.search(r"(?:обо мне|about me)[:\s]+(.*?)(?=\n\s*\n|\n[А-ЯЁA-Z]|$)", text, re.IGNORECASE | re.DOTALL)
        if m:
            snippet = m.group(1).strip()
            if snippet:
                return snippet[:500]

        lines = [line.strip() for line in text.splitlines() if line.strip() and not line.startswith("[")]
        for line in lines:
            if len(line) > 30:
                return line[:500]
        return None

    def _extract_jd_skills(self, text: str) -> tuple[list[str], list[str]]:
        """Split skills into must-have and nice-to-have."""
        lowered = text.lower()
        must_keywords = ["требования", "обязательно", "must have", "ожидаем от вас", "требуется"]
        nice_keywords = ["будет плюсом", "желательно", "nice to have", "плюсом будет", "приветствуется"]

        # Split into blocks if keywords exist
        nice_split = -1
        for nk in nice_keywords:
            idx = lowered.find(nk)
            if idx != -1:
                nice_split = idx
                break

        if nice_split != -1:
            must_part = text[:nice_split]
            nice_part = text[nice_split:]
            must_matches, _ = extract_skills(must_part)
            nice_matches, _ = extract_skills(nice_part)
            must_names = [m.name for m in must_matches]
            nice_names = [m.name for m in nice_matches if m.name not in must_names]
            return must_names, nice_names
        else:
            all_matches, _ = extract_skills(text)
            return [m.name for m in all_matches], []

    def _extract_jd_title(self, text: str) -> str:
        """Extract job title from vacancy text."""
        for line in text.splitlines()[:3]:
            stripped = line.strip()
            if stripped and len(stripped) < 80:
                return stripped
        return "Software Engineer"

    def _extract_jd_grades(self, lowered: str) -> list[str]:
        """Extract applicable grades for the position."""
        grades: list[str] = []
        if any(w in lowered for w in ("senior", "сеньор", "ведущий")):
            grades.append("senior")
        if any(w in lowered for w in ("middle", "мидл")):
            grades.append("middle")
        if any(w in lowered for w in ("junior", "джун")):
            grades.append("junior")
        if any(w in lowered for w in ("intern", "стажер")):
            grades.append("intern")
        return grades or ["middle"]
