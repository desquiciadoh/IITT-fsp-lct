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

_PLACEHOLDER_RE = re.compile(r"\[(?:NAME|PHONE|EMAIL|TG|URL)\]")

# "опыт работы: 3.5 года", "стаж: 4 года 6 месяцев", "опыт более 5 лет" (text is lower-cased)
_YEARS_RU_RE = re.compile(
    r"(?:опыт|стаж)[а-я]*(?:\s+работы)?(?:\s+составляет)?\s*[:—\-–]?\s*(?:более\s+|около\s+)?"
    r"(\d+(?:[.,]\d+)?)\s*\+?\s*(?:лет|года?|г\.)(?![а-я])"
    r"(?:\s*(?:и\s+)?(?P<months>\d{1,2})\s*мес)?"
)
_YEARS_EN_RE = re.compile(r"(\d+(?:\.\d+)?)\+?\s*years?\s+of\s+(?:commercial\s+)?experience")

# Salary: amounts count only in lines with a money cue (AI-R6)
_NET_RE = re.compile(r"(?<![.\w])net\b|на\s+руки|чистыми|после\s+(?:вычета|налогов)", re.IGNORECASE)
_GROSS_RE = re.compile(
    r"(?<![.\w])gross\b|до\s+(?:вычета|налогов)|грязными|с\s+уч[её]том\s+ндфл", re.IGNORECASE
)
_SALARY_CUE_RE = re.compile(
    r"зарплат|з/п|(?<![а-яё])зп(?![а-яё])|оклад|доход|вилк|компенсац|ожидани|salary|₽"
    r"|(?<![а-яё])руб|(?<![a-z])rub|\d\s*[kк](?![a-zа-яё])",
    re.IGNORECASE,
)
_AMOUNT = r"\d[\d \xa0]*(?:[.,]\d+)?\s*(?:тыс\.?|[kк](?![a-zа-яё]))?"
_NOT_YEARS = r"(?!\s*(?:лет|года?|years?|мес))"
_SALARY_RANGE_RE = re.compile(
    rf"({_AMOUNT}){_NOT_YEARS}\s*(?:до|-|–|—|\.\.\.|…)\s*({_AMOUNT}){_NOT_YEARS}", re.IGNORECASE
)
_SALARY_FROM_RE = re.compile(rf"(?<![а-яё])от\s*({_AMOUNT}){_NOT_YEARS}", re.IGNORECASE)
_SALARY_TO_RE = re.compile(rf"(?<![а-яё])до\s*({_AMOUNT}){_NOT_YEARS}", re.IGNORECASE)
_SALARY_AFTER_CUE_RE = re.compile(
    rf"(?:зарплат[а-я]*|з/п|зп|оклад|доход|ожидани[а-я]*(?:\s+по\s+зарплате)?|salary)\s*[:\-–—]?\s*({_AMOUNT})",
    re.IGNORECASE,
)
_SALARY_BEFORE_CURRENCY_RE = re.compile(rf"({_AMOUNT})\s*(?:₽|руб|rub)", re.IGNORECASE)

# Roles and sections
_ROLE_LABEL_RE = re.compile(
    r"^\s*(?:желаемая\s+должность|должность|позиция|position|title)\s*[:\-–—]\s*(\S.*)$",
    re.IGNORECASE | re.MULTILINE,
)
_ROLE_WORD_RE = re.compile(
    r"developer|engineer|разработчик|инженер|программист|специалист|analyst|аналитик|architect"
    r"|архитектор|scientist|\blead\b|тимлид|devops|\bqa\b|тестировщик",
    re.IGNORECASE,
)
_SECTION_HEADER_RE = re.compile(
    r"^\s*(?:опыт\s+работы|опыт|work\s+experience|experience|образование|education|ключевые\s+навыки"
    r"|навыки|skills|обо\s+мне|о\s+себе|about\s+me|about|summary|проекты|projects|курсы|courses"
    r"|сертификаты|certificates|языки|languages|контакты|contacts|дополнительная\s+информация"
    r"|достижения|хобби|желаемая\s+должность(?:\s+и\s+зарплата)?)\s*:?\s*$",
    re.IGNORECASE,
)
_FIELD_LINE_RE = re.compile(r"^\s*[А-ЯЁA-Z][А-ЯЁа-яёA-Za-z ]{1,30}:\s")
_ABOUT_HEADER_RE = re.compile(r"^\s*(?:обо\s+мне|о\s+себе|about\s+me|summary)\s*:?\s*(.*)$", re.IGNORECASE)
_EXPERIENCE_HEADER_RE = re.compile(r"^\s*(?:опыт\s+работы|work\s+experience|experience)\s*:?\s*()$", re.IGNORECASE)

# JD grades: the title and "ищем/уровень" lines only
_GRADE_CUE_RE = re.compile(r"грейд|уровень|level|grade|ищем|ищет|требуется|looking\s+for", re.IGNORECASE)
_JD_GRADE_PATTERNS = (
    ("senior", r"\b(?:senior|сеньор\w*|ведущ\w*|старш\w*|lead|тимлид\w*)\b"),
    ("middle", r"\b(?:middle|мидл\w*)\b"),
    ("junior", r"\b(?:junior|джун\w*|младш\w*)\b"),
    ("intern", r"\b(?:intern|стаж[её]р\w*)\b"),
)


_THOUSANDS_SUFFIXES = ("тыс.", "тыс", "k", "к")


def _thousands_suffix(raw: str) -> str:
    s = raw.strip().lower()
    return next((suffix for suffix in _THOUSANDS_SUFFIXES if s.endswith(suffix)), "")


def _parse_amount(raw: str) -> int | None:
    """"220 000", "150к", "250 тыс" -> RUB; amounts below 10 000 are not salaries."""
    s = raw.strip().lower().replace(" ", "").replace("\xa0", "")
    suffix = _thousands_suffix(s)
    if suffix:
        s = s[: -len(suffix)]
    try:
        value = int(float(s.replace(",", ".")) * (1000 if suffix else 1))
    except ValueError:
        return None
    return value if 10_000 <= value <= 10_000_000 else None


def _parse_range(raw_low: str, raw_high: str) -> tuple[int | None, int | None]:
    """"150-200 тыс": the suffix of the upper bound applies to the lower one too."""
    low, high = _parse_amount(raw_low), _parse_amount(raw_high)
    suffix = _thousands_suffix(raw_high)
    if low is None and high is not None and suffix and not _thousands_suffix(raw_low):
        low = _parse_amount(raw_low.strip() + suffix)
    return low, high


def _section_lines(text: str, header_re: re.Pattern[str], *, stop_at_fields: bool = False) -> list[str]:
    """Lines of the first section whose header matches, up to the next section header."""
    lines = text.splitlines()
    for i, line in enumerate(lines):
        m = header_re.match(line)
        if not m:
            continue
        out = [m.group(1)] if m.group(1) else []
        for nxt in lines[i + 1:]:
            if _SECTION_HEADER_RE.match(nxt) or (stop_at_fields and _FIELD_LINE_RE.match(nxt)):
                break
            out.append(nxt)
        return out
    return []


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
        """Experience in years: "опыт 3 года", "стаж: 4 года 6 месяцев", "5+ years of experience"."""
        m = _YEARS_RU_RE.search(lowered) or _YEARS_EN_RE.search(lowered)
        if not m:
            return None
        years = float(m.group(1).replace(",", "."))
        months = m.groupdict().get("months")
        if months:
            years += int(months) / 12
        return round(years, 1) if 0 <= years <= 50 else None

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
        """Salary bounds and type from lines with a salary cue only (AI-R6)."""
        sal_type: str | None = None
        if _GROSS_RE.search(text):
            sal_type = "gross"
        elif _NET_RE.search(text):
            sal_type = "net"

        for line in text.splitlines():
            if not _SALARY_CUE_RE.search(line):
                continue
            for m in _SALARY_RANGE_RE.finditer(line):  # "2019-2023" is skipped, a later range counts
                low, high = _parse_range(m.group(1), m.group(2))
                if low or high:
                    if low and high and high < low:
                        low, high = high, low
                    return low, high, sal_type
            low = _parse_amount(m.group(1)) if (m := _SALARY_FROM_RE.search(line)) else None
            high = _parse_amount(m.group(1)) if (m := _SALARY_TO_RE.search(line)) else None
            if low or high:
                return low, high, sal_type
            # "Зарплата: 200 000 руб", "Ожидания по зарплате 250k", "250 000 ₽"
            m = _SALARY_AFTER_CUE_RE.search(line) or _SALARY_BEFORE_CURRENCY_RE.search(line)
            if m and (amount := _parse_amount(m.group(1))):
                return amount, None, sal_type
        return None, None, sal_type

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
        """Target role from a "Желаемая должность:" line or a role line in the header; never invented."""
        m = _ROLE_LABEL_RE.search(text)
        if m:
            return [m.group(1).strip()[:100]]
        lines = [line.strip() for line in text.splitlines() if line.strip()][:10]
        for line in lines:
            role = re.split(r",|\s[—–-]\s", line, maxsplit=1)[0].strip()  # "Python developer, опыт 3 года"
            if (_ROLE_WORD_RE.search(role) and len(role) < 60
                    and not _PLACEHOLDER_RE.search(role) and ":" not in role):
                return [role]
        return []

    def _extract_about(self, text: str) -> str | None:
        """The "Обо мне" section (inline or below the header), <= 500 chars, no placeholders."""
        lines = _section_lines(text, _ABOUT_HEADER_RE, stop_at_fields=True)
        clean = " ".join(line.strip() for line in lines if line.strip() and not _PLACEHOLDER_RE.search(line))
        return clean[:500] or None

    def _extract_experience_text(self, text: str) -> str | None:
        """The "Опыт работы" section only, without placeholder lines, <= 1500 chars (AI-R1 item 6)."""
        lines = _section_lines(text, _EXPERIENCE_HEADER_RE)
        clean = "\n".join(line.rstrip() for line in lines if line.strip() and not _PLACEHOLDER_RE.search(line))
        return clean[:1500]

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
        """Grades from the title (first line) and "ищем/уровень" lines; never a default.

        A body line such as "работа с Team Lead и senior коллегами" is not a grade.
        """
        lines = [line for line in text.splitlines() if line.strip()]
        scope = " ".join(lines[:1] + [line for line in lines[1:] if _GRADE_CUE_RE.search(line)]).lower()
        scope = re.sub(r"под\s+руководством\s+\w+", "", scope)
        grades: list[str] = []
        for grade, pattern in _JD_GRADE_PATTERNS:
            if re.search(pattern, scope):
                grades.append(grade)
        return grades
