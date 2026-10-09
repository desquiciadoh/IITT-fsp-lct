"""Local PII redaction module (152-FZ compliance) with safety net (AI-R1).

Extracts and replaces sensitive personal identifiable information (emails, phones,
Telegram handles, URLs, and personal names) with non-leaking placeholders.
Provides assert_clean() verification to block LLM transmission on any residual leak.
"""
from __future__ import annotations

import re

from .types import Redacted

_CODE_ANNOTATION_STOPLIST = {
    "dataclass", "pytest", "property", "staticmethod", "classmethod", "override",
    "transactional", "component", "injectable", "input", "output", "app", "router",
    "fixture", "abstractmethod", "validator", "field", "root_validator",
    "get", "post", "put", "delete", "patch", "route", "test", "describe",
}

_ROLE_AND_SKILL_WORDS = {
    "developer", "engineer", "разработчик", "инженер", "lead", "senior", "middle",
    "junior", "intern", "стажер", "стажёр", "тимлид", "архитектор", "architect",
    "devops", "qa", "tester", "frontend", "backend", "fullstack", "scientist",
    "python", "java", "golang", "react", "docker", "postgres", "sql", "linux",
}

_SECTION_HEADERS = {
    "опыт работы", "обо мне", "ключевые навыки", "навыки", "образование",
    "высшее образование", "курсы", "сертификаты", "контакты", "контактная информация",
    "желаемая должность", "резюме", "профиль", "портфолио", "информация",
    "work experience", "experience", "education", "skills", "about me", "contacts",
}

_KNOWN_SKILL_DOMAINS = {"asp.net", "node.js", "vue.js", "next.js", "nuxt.js"}


def _is_name_token_valid(token: str) -> bool:
    cleaned = token.strip(" ,.-–:;").lower()
    if not cleaned or len(cleaned) < 2:
        return False
    if cleaned in _ROLE_AND_SKILL_WORDS or cleaned in _CODE_ANNOTATION_STOPLIST:
        return False
    # Check Cyrillic or Latin letters (hyphen allowed e.g. Римская-Корсакова)
    return bool(re.match(r"^[А-Яа-яЁёA-Za-z]+(?:-[А-Яа-яЁёA-Za-z]+)?$", cleaned))


def _clean_phone_span(match: re.Match) -> str:
    raw = match.group(0)
    digits = re.sub(r"\D", "", raw)
    # Reject sequence of years like "2018 2019 2020 2021"
    year_parts = re.findall(r"\b(19\d\d|20\d\d)\b", raw)
    if year_parts and len("".join(year_parts)) == len(digits):
        return raw  # keep original text, it's just years
    if 10 <= len(digits) <= 15:
        return "[PHONE]"
    return raw


def redact(text: str) -> Redacted:
    """Extract and mask all PII from input text according to 152-FZ."""
    if not text:
        return Redacted(text="", found={"email": [], "phone": [], "telegram": [], "url": [], "name": []})

    working = text
    found_emails: list[str] = []
    found_phones: list[str] = []
    found_telegrams: list[str] = []
    found_urls: list[str] = []
    found_names: list[str] = []

    # 1. Emails
    email_re = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
    for m in email_re.finditer(working):
        em = m.group(0)
        if em not in found_emails:
            found_emails.append(em)
    working = email_re.sub("[EMAIL]", working)

    # 2. Telegram:
    # 2a. t.me / telegram.me links
    tg_url_re = re.compile(r"(?:https?://)?(?:www\.)?(?:t\.me|telegram\.me)/([A-Za-z0-9_]{4,32})", re.IGNORECASE)
    for m in tg_url_re.finditer(working):
        h = m.group(1)
        found_telegrams.append(f"@{h}")
    working = tg_url_re.sub("[TG]", working)

    # 2b. Labelled telegram handles: e.g. "Telegram: ivan_petrov" or "тг: @ivan_dev"
    tg_labelled_re = re.compile(
        r"(?<![A-Za-zА-Яа-я0-9_])(?:telegram|телеграм|tg|тг)(?![A-Za-zА-Яа-я0-9_])\s*[:\-–]?\s*@?([A-Za-z0-9_]{4,32})\b",
        re.IGNORECASE,
    )
    for m in tg_labelled_re.finditer(working):
        h = m.group(1)
        if h.lower() not in _CODE_ANNOTATION_STOPLIST:
            found_telegrams.append(f"@{h}")
    working = tg_labelled_re.sub("[TG]", working)

    # 2c. Mask bare @handles in text (prevent any handle leak)
    bare_tg_re = re.compile(r"(?<![\w/])@([A-Za-z0-9_]{3,32})\b")
    for m in bare_tg_re.finditer(working):
        h = m.group(1)
        if h.lower() not in _CODE_ANNOTATION_STOPLIST:
            # If not in stoplist, record in found only if looks like username
            if f"@{h}" not in found_telegrams and len(h) >= 4:
                found_telegrams.append(f"@{h}")
        # Always mask bare @handle if not code annotation
        if h.lower() not in _CODE_ANNOTATION_STOPLIST:
            working = working.replace(m.group(0), "[TG]")

    # 3. URLs and Domains
    # 3a. Schemes & web links
    url_re = re.compile(r"\bhttps?://[^\s<>()\"'{}|\\^`\[\]]+", re.IGNORECASE)
    for m in url_re.finditer(working):
        u = m.group(0)
        found_urls.append(u)
    working = url_re.sub("[URL]", working)

    # 3b. Profile domains and personal sites
    prof_domain_re = re.compile(
        r"\b(?:github\.com|gitlab\.com|bitbucket\.org|linkedin\.com|hh\.ru|"
        r"habr\.com|career\.habr\.com|vk\.com|ok\.ru|kaggle\.com|leetcode\.com|"
        r"stackoverflow\.com|medium\.com|dev\.to|behance\.net|dribbble\.com)/[^\s<>()\"'{}|\\^`\[\]]+",
        re.IGNORECASE,
    )
    for m in prof_domain_re.finditer(working):
        u = m.group(0)
        found_urls.append(u)
    working = prof_domain_re.sub("[URL]", working)

    # 3c. Personal domain names (e.g. ivanov.dev, my-site.ru) excluding tech skills
    pers_domain_re = re.compile(
        r"\b[A-Za-z0-9][A-Za-z0-9-_]*\.(?:ru|рф|com|dev|io|me|org|net|site|pro|tech|app)(?:/\S*)?\b",
        re.IGNORECASE,
    )
    for m in pers_domain_re.finditer(working):
        dom = m.group(0)
        if dom.lower() not in _KNOWN_SKILL_DOMAINS and "[URL]" not in dom:
            found_urls.append(dom)
            working = working.replace(dom, "[URL]")

    # 4. Phones (RU and International: +7, 8, +375, etc.)
    # Match full number string with brackets, spaces, dashes
    phone_re = re.compile(
        r"(?:(?:\+\d{1,3}|[78])[\s\-\.]*)?(?:\(\d{2,4}\)|\d{2,4})[\s\-\.]*\d{2,4}[\s\-\.]*\d{1,4}(?:[\s\-\.]*\d{1,4})?"
    )

    def _replace_phone(m: re.Match) -> str:
        raw_val = m.group(0).strip()
        digits = re.sub(r"\D", "", raw_val)
        year_parts = re.findall(r"\b(19\d\d|20\d\d)\b", raw_val)
        if year_parts and len("".join(year_parts)) == len(digits):
            return raw_val
        if 10 <= len(digits) <= 15:
            found_phones.append(raw_val)
            return "[PHONE]"
        return raw_val

    working = phone_re.sub(_replace_phone, working)

    # 5. Names:
    # 5a. Labelled names: "ФИО: Иванов Иван Иванович", "Рекомендации: Сидоров Петр Алексеевич"
    labelled_name_re = re.compile(
        r"(?:ФИО|Имя|Name|Рекомендации|Контактное лицо)\s*[:\-–]\s*([А-ЯЁA-Z][а-яёa-zА-ЯЁA-Z\-]+(?:\s+[А-ЯЁA-Z][а-яёa-zА-ЯЁA-Z\-]+){1,2})",
        re.IGNORECASE,
    )
    for m in labelled_name_re.finditer(working):
        name_cand = m.group(1).strip()
        tokens = name_cand.split()
        if all(_is_name_token_valid(t) for t in tokens):
            found_names.append(name_cand)

    # 5b. Header heuristic across first 10 non-empty lines
    lines = working.splitlines()
    non_empty_count = 0
    for idx, line in enumerate(lines[:15]):
        stripped = line.strip()
        if not stripped:
            continue
        non_empty_count += 1
        if non_empty_count > 10:
            break

        if any(h in stripped.lower() for h in _SECTION_HEADERS):
            continue
        if any(ph in stripped for ph in ("[EMAIL]", "[PHONE]", "[TG]", "[URL]")):
            continue

        # Extract name part before comma or dash (e.g. "Петров Иван, Python-разработчик")
        name_part = re.split(r"[,—–\-]\s*(?:python|разработчик|developer|инженер|lead|junior|middle|senior)", stripped, flags=re.IGNORECASE)[0].strip()
        tokens = name_part.split()

        # Check 2 or 3 tokens: Title Case OR ALL CAPS
        if 2 <= len(tokens) <= 3 and all(_is_name_token_valid(t) for t in tokens):
            # Check Title Case or ALL CAPS
            valid_case = all(t.isupper() or t.istitle() for t in tokens)
            if valid_case:
                found_names.append(name_part)
                # Mask in the line
                lines[idx] = line.replace(name_part, "[NAME]")
                break

    working = "\n".join(lines)

    # 5c. Mask all occurrences of found name tokens across the entire text (including inflections)
    for full_name in list(found_names):
        tokens = full_name.split()
        for tok in tokens:
            cleaned_tok = tok.strip(" ,.-–:;")
            if len(cleaned_tok) >= 3 and _is_name_token_valid(cleaned_tok):
                # Build stem: token minus last 1-2 letters for words >= 5 chars
                stem = cleaned_tok[:-2] if len(cleaned_tok) >= 6 else (cleaned_tok[:-1] if len(cleaned_tok) >= 5 else cleaned_tok)
                pattern = rf"\b{re.escape(stem)}[а-яёa-zА-ЯЁA-Z]*\b"
                working = re.sub(pattern, "[NAME]", working, flags=re.IGNORECASE)

    # Clean duplicates in found collections
    return Redacted(
        text=working,
        found={
            "email": list(dict.fromkeys(found_emails)),
            "phone": list(dict.fromkeys(found_phones)),
            "telegram": list(dict.fromkeys(found_telegrams)),
            "url": list(dict.fromkeys(found_urls)),
            "name": list(dict.fromkeys(found_names)),
        },
    )


def assert_clean(redacted: Redacted) -> tuple[bool, str | None]:
    """Safety net: verify that redacted text contains zero residual PII leaks.

    Returns:
        (True, None) if clean, or (False, "pii_residual") if leaked.
    """
    text = redacted.text
    if not text:
        return True, None

    # Check for residual raw emails
    if re.search(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b", text):
        return False, "pii_residual"

    # Check for residual phones
    phone_matches = re.findall(r"(?:\+\d{1,3}[\s\-\(]{0,2}\d{1,4}[\s\-\)]{0,2})?[\s\-\d]{7,18}\d", text)
    for raw in phone_matches:
        digits = re.sub(r"\D", "", raw)
        year_parts = re.findall(r"\b(19\d\d|20\d\d)\b", raw)
        if not (year_parts and len("".join(year_parts)) == len(digits)) and len(digits) >= 10:
            return False, "pii_residual"

    # Check for residual found values
    for _kind, vals in redacted.found.items():
        for val in vals:
            v_clean = val.strip("@").strip()
            if len(v_clean) >= 4 and v_clean.lower() in text.lower():
                return False, "pii_residual"

    return True, None
