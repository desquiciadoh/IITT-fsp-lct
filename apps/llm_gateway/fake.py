"""Rule-based Fake LLM implementation.

Permanent fallback and CI default.
Extracts fields from resume and JD texts using regex heuristics and taxonomy rules.
Adheres strictly to AI.md AI-R6 requirements (scoring spec, header-only grades, bounded salary cues).
"""
from __future__ import annotations

import re
from typing import Any

from taxonomy import extract_skills, load_skills

from .types import JdDraft, ResumeDraft


class FakeLlm:
    """Rule-based LLM gateway implementation."""

    name: str = "fake"

    def __init__(self, fallback_reason: str = "provider_fake") -> None:
        # Why the rules answer: the configured provider, or "no_key" from get_gateway() (AI-R2)
        self.fallback_reason = fallback_reason

    def resume(self, redacted_text: str) -> ResumeDraft:
        """Extract resume draft using regex and taxonomy heuristics."""
        lowered = redacted_text.lower()

        # 1. Extract skills from taxonomy
        matches, _ = extract_skills(redacted_text)
        skills_raw = [m.name for m in matches]

        # 2. Infer specialization (scoring mechanism)
        specialization = self._infer_specialization(redacted_text, matches)

        # 3. Infer years of experience
        years_exp = self._extract_years_experience(lowered)

        # 4. Infer grade (header regex or derived from years)
        claimed_grade = self._infer_grade(redacted_text, years_exp)

        # 5. Infer salary and salary_type
        sal_min, sal_max, sal_type = self._extract_salary(redacted_text)

        # 6. Infer work formats (office, hybrid, remote)
        work_formats = self._extract_work_formats(lowered)

        # 7. Infer city
        city = self._extract_city(lowered)

        # 8. Infer roles
        roles = self._extract_roles(redacted_text, specialization)

        # 9. Clean about & experience_text
        about = self._extract_about(redacted_text)
        experience_text = self._extract_experience_text(redacted_text)

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
            experience_text=experience_text,
        )

    def jd(self, text: str) -> JdDraft:
        """Extract job description draft using regex heuristics."""
        if not text or not text.strip():
            return JdDraft(
                title=None,
                specialization=None,
                grades=[],
                must_skills_raw=[],
                nice_skills_raw=[],
                work_formats=[],
                location=None,
                salary_min=None,
                salary_max=None,
                salary_type=None,
                team_context=None,
                description=None,
            )

        lowered = text.lower()

        # 1. Split text into "must" and "nice" sections if present
        must_skills_raw, nice_skills_raw = self._extract_jd_skills(text)

        # 2. Extract title & specialization
        title = self._extract_jd_title(text)
        all_matches, _ = extract_skills(text)
        specialization = self._infer_specialization(text, all_matches)

        # 3. Extract grades
        grades = self._extract_jd_grades(text)

        # 4. Extract work formats & location
        work_formats = self._extract_work_formats(lowered)
        location = self._extract_city(lowered)

        # 5. Extract salary
        sal_min, sal_max, sal_type = self._extract_salary(text)

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
            description=text[:4000] if text else None,
        )

    def phrase(self, facts: list[str]) -> str:
        """Combine factual statements into Russian summary sentences."""
        if not facts:
            return "Кандидат соответствует ключевым требованиям позиции."

        clean_facts = [f.strip().rstrip(".") for f in facts if f.strip()]
        if not clean_facts:
            return "Кандидат соответствует ключевым требованиям позиции."

        if len(clean_facts) == 1:
            return f"Кандидат подходит на позицию: {clean_facts[0]}."

        joined = ", ".join(clean_facts[:-1]) + f" и {clean_facts[-1]}"
        return f"Сильные стороны кандидата: {joined}."

    # ── Helpers ──

    def _infer_specialization(self, text: str, matches: list[Any]) -> str | None:
        """Infer backend | frontend | ml_data using score-based weighting."""
        scores = {"backend": 0, "frontend": 0, "ml_data": 0}

        # Topics from matched skills
        catalog = load_skills()
        for m in matches:
            entry = catalog.get(m.skill_id)
            if not entry:
                continue
            t = entry.topic
            if t.startswith("backend") or t.startswith("infrastructure"):
                scores["backend"] += 1
            elif t.startswith("frontend"):
                scores["frontend"] += 1
            elif t.startswith("ml"):
                scores["ml_data"] += 1

        # Text keywords (Header lines count x3)
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        header_lines = lines[:3]
        for line in lines[3:]:
            if any(term in line.lower() for term in ("желаемая должность", "позиция", "должность")):
                header_lines.append(line)

        header_text = " ".join(header_lines).lower()
        body_text = text.lower()

        spec_keywords = {
            "backend": [
                r"\bbackend\b", r"\bбэкенд\b", r"\bбэкендер\b", r"\bdjango\b",
                r"\bfastapi\b", r"\bspring\b", r"\bgolang\b", r"\bgo developer\b",
                r"\bpython developer\b", r"\bjava developer\b", r"\bc# developer\b",
                r"\bphp developer\b", r"\bnodejs developer\b",
            ],
            "frontend": [
                r"\bfrontend\b", r"\bфронтенд\b", r"\bфронтендер\b", r"\breact\b",
                r"\bvue\b", r"\bangular\b", r"\bверстальщик\b", r"\bhtml/css\b",
                r"\bjavascript developer\b", r"\btypescript developer\b",
            ],
            "ml_data": [
                r"\bml\b", r"\bmachine learning\b", r"\bdata science\b", r"\bdata scientist\b",
                r"\bмашинное обучение\b", r"\bдата саентист\b", r"\bnlp\b", r"\bcomputer vision\b",
                r"\bdeep learning\b", r"\bнейросети\b", r"\bdata engineer\b", r"\bдата инженер\b",
            ],
        }

        for spec, pats in spec_keywords.items():
            for pat in pats:
                if re.search(pat, header_text):
                    scores[spec] += 3
                elif re.search(pat, body_text):
                    scores[spec] += 1

        best_score = max(scores.values())
        if best_score <= 0:
            return None

        # Check for tie among top scores
        top_specs = [s for s, sc in scores.items() if sc == best_score]
        if len(top_specs) > 1:
            return None

        return top_specs[0]

    def _extract_years_experience(self, lowered: str) -> float | None:
        """Extract experience in years from text."""
        # e.g. "опыт 3 года", "опыт работы: 5 лет", "4.5 года"
        m = re.search(r"опыт(?:а|\s+работы)?\s*(?:составляет)?\s*[:—\-]?\s*(\d+(?:[.,]\d+)?)\s*(?:лет|года|год|г\b)", lowered)
        if m:
            val = m.group(1).replace(",", ".")
            try:
                years = float(val)
                if 0 <= years <= 50:
                    return years
            except ValueError:
                pass
        return None

    def _infer_grade(self, text: str, years: float | None) -> str | None:
        """Extract grade from header lines, or derive from years of experience."""
        # Check header lines (first 5 lines) only
        lines = [line.strip() for line in text.splitlines() if line.strip()][:5]
        header_text = " ".join(lines)

        # Exclude "под руководством senior"
        sanitized_header = re.sub(r"под\s+руководством\s+\w+", "", header_text, flags=re.IGNORECASE)

        if re.search(r"\b(?:senior|lead|тимлид|ведущий)\b", sanitized_header, re.IGNORECASE):
            return "senior"
        if re.search(r"\b(?:middle|мидл)\b", sanitized_header, re.IGNORECASE):
            return "middle"
        if re.search(r"\b(?:junior|джун|младший)\b", sanitized_header, re.IGNORECASE):
            return "junior"
        if re.search(r"\b(?:intern|стаж[её]р)\b", sanitized_header, re.IGNORECASE):
            return "intern"

        # Otherwise derive from years
        if years is not None:
            if years >= 5.0:
                return "senior"
            if years >= 2.0:
                return "middle"
            if years >= 0.8:
                return "junior"
            if years > 0.0:
                return "intern"

        return None

    def _extract_salary(self, text: str) -> tuple[int | None, int | None, str | None]:
        """Extract salary bounds and type adhering strictly to AI-R6."""
        sal_cues = [
            "зарплат", "з/п", "зп", "оклад", "доход", "вилка", "компенсац",
            "salary", "₽", "руб", "rub", "тыс", "к", "k",
        ]

        # 1. Salary type: word-boundary only, guarded against dots and words
        p_net = re.compile(r"(?<![.\w])net\b|на руки|чистыми|после\s+(?:вычета|налогов)", re.I)
        p_gross = re.compile(r"(?<![.\w])gross\b|до\s+(?:вычета|налогов)|грязными|с уч[её]том ндфл", re.I)
        sal_type: str | None = None
        if p_gross.search(text):
            sal_type = "gross"
        elif p_net.search(text):
            sal_type = "net"

        # 2. Amounts in cue lines
        sal_min: int | None = None
        sal_max: int | None = None

        lines = text.splitlines()
        cue_lines = []
        for line in lines:
            l_low = line.lower()
            if any(c in l_low for c in sal_cues):
                cue_lines.append(line)

        search_texts = cue_lines if cue_lines else [text]

        def parse_num(s: str) -> int | None:
            s_clean = s.strip().lower().replace(" ", "").replace("\xa0", "")
            mult = 1
            if s_clean.endswith("тыс"):
                mult = 1000
                s_clean = s_clean[:-3]
            elif s_clean.endswith("k") or s_clean.endswith("к"):
                mult = 1000
                s_clean = s_clean[:-1]
            try:
                val = int(s_clean) * mult
                if val >= 10000:
                    return val
            except ValueError:
                pass
            return None

        num_pat = r"\d[\d\s\xa0]*(?:тыс|[kк])?"
        range_p = re.compile(
            rf"(?:от\s*)?({num_pat})\s*(?:до|-|–|—|\.\.\.)\s*({num_pat})(?!\s*(?:лет|года|год|years))",
            re.I,
        )
        single_from_p = re.compile(rf"от\s*({num_pat})(?!\s*(?:лет|года|год|years))", re.I)
        single_to_p = re.compile(rf"до\s*({num_pat})(?!\s*(?:лет|года|год|years))", re.I)

        for st in search_texts:
            m = range_p.search(st)
            if m:
                n1 = parse_num(m.group(1))
                n2 = parse_num(m.group(2))
                if n1 or n2:
                    sal_min = n1
                    sal_max = n2
                    break
            m_from = single_from_p.search(st)
            if m_from:
                sal_min = parse_num(m_from.group(1))
            m_to = single_to_p.search(st)
            if m_to:
                sal_max = parse_num(m_to.group(1))
            if sal_min or sal_max:
                break

        if sal_min is not None and sal_max is not None and sal_max < sal_min:
            sal_min, sal_max = sal_max, sal_min

        return sal_min, sal_max, sal_type

    def _extract_work_formats(self, lowered: str) -> list[str]:
        """Extract office, hybrid, remote formats."""
        formats: list[str] = []
        if re.search(r"\b(?:удаленка|удалёнка|удаленно|удалённо|удаленный|удалённый|remote)\b", lowered):
            formats.append("remote")
        if re.search(r"\b(?:гибрид|гибридный|hybrid)\b", lowered):
            formats.append("hybrid")
        if re.search(r"\b(?:офис|office)\b", lowered):
            formats.append("office")
        return formats

    def _extract_city(self, lowered: str) -> str | None:
        """Extract Russian cities using whole-word matches."""
        cities = [
            (r"\bмоскв[аеыу]\b", "Москва"),
            (r"\bсанкт-петербург\w*\b|\bпитер\w*\b|\bспб\b", "Санкт-Петербург"),
            (r"\bновосибирск\w*\b", "Новосибирск"),
            (r"\bекатеринбург\w*\b", "Екатеринбург"),
            (r"\bказан[ьиея]\b", "Казань"),
            (r"\bнижн(?:ий|ем|его)\s+новгород\w*\b", "Нижний Новгород"),
            (r"\bсамар[аеыу]\b", "Самара"),
            (r"\bкраснодар\w*\b", "Краснодар"),
            (r"\bсочи\b", "Сочи"),
            (r"\bростов-на-дону\b", "Ростов-на-Дону"),
            (r"\bминск\w*\b", "Минск"),
        ]
        for c_pat, c_name in cities:
            if re.search(c_pat, lowered):
                return c_name
        return None

    def _extract_roles(self, text: str, spec: str | None) -> list[str]:
        """Extract target roles from resume header/title."""
        for line in text.splitlines()[:5]:
            stripped = line.strip()
            if any(w in stripped.lower() for w in ("developer", "инженер", "разработчик", "специалист", "engineer")):
                if len(stripped) < 60 and not stripped.startswith("["):
                    return [stripped]
        fallback_role = {
            "backend": "Backend Developer",
            "frontend": "Frontend Developer",
            "ml_data": "ML Engineer",
        }.get(spec or "", "Software Engineer")
        return [fallback_role]

    def _extract_about(self, text: str) -> str | None:
        """Extract short <= 500 chars summary without PII placeholders."""
        m = re.search(r"(?:обо мне|about me)[:\s]+(.*?)(?=\n\s*\n|\n[А-ЯЁA-Z]|$)", text, re.IGNORECASE | re.DOTALL)
        if m:
            snippet = m.group(1).strip()
            # drop lines with placeholders
            clean_lines = [line_item for line_item in snippet.splitlines() if not re.search(r"\[(NAME|PHONE|EMAIL|TG|URL)\]", line_item)]
            clean_text = " ".join(clean_lines).strip()
            if clean_text:
                return clean_text[:500]

        return None

    def _extract_experience_text(self, text: str) -> str | None:
        """Extract only 'Опыт работы' section, dropping placeholder lines, capped at 1500 chars."""
        m = re.search(r"(?:опыт работы|experience)[:\s]+(.*?)(?=\n\s*(?:образование|обо мне|навыки|skills|education)|$)", text, re.IGNORECASE | re.DOTALL)
        if m:
            exp_raw = m.group(1).strip()
            clean_lines = [line_item for line_item in exp_raw.splitlines() if not re.search(r"\[(NAME|PHONE|EMAIL|TG|URL)\]", line_item)]
            clean_text = "\n".join(clean_lines).strip()
            if clean_text:
                return clean_text[:1500]
        return ""

    def _extract_jd_skills(self, text: str) -> tuple[list[str], list[str]]:
        """Split skills into must-have and nice-to-have."""
        lowered = text.lower()
        nice_keywords = ["будет плюсом", "желательно", "nice to have", "плюсом будет", "приветствуется"]

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

    def _extract_jd_title(self, text: str) -> str | None:
        """Extract job title from vacancy text if it contains a role word."""
        role_words = ("developer", "инженер", "разработчик", "lead", "architect", "специалист", "engineer", "аналитик", "тестировщик", "qa")
        for line in text.splitlines()[:3]:
            stripped = line.strip()
            if stripped and len(stripped) < 80:
                if any(w in stripped.lower() for w in role_words):
                    return stripped
        return None

    def _extract_jd_grades(self, text: str) -> list[str]:
        """Extract applicable grades for the position without inventing defaults."""
        lowered = text.lower()
        grades: list[str] = []
        if re.search(r"\b(?:senior|сеньор|ведущий|lead)\b", lowered):
            grades.append("senior")
        if re.search(r"\b(?:middle|мидл)\b", lowered):
            grades.append("middle")
        if re.search(r"\b(?:junior|джун)\b", lowered):
            grades.append("junior")
        if re.search(r"\b(?:intern|стаж[её]р)\b", lowered):
            grades.append("intern")
        return grades
