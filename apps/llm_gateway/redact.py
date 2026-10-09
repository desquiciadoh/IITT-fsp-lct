"""Local PII redaction module (152-FZ compliance).

Redacts personal identifiable information (emails, phones, Telegram handles,
URLs, and full names) locally before sending text to any external LLM.
"""
from __future__ import annotations

import re
from .types import Redacted

# Common section headers that should NOT be considered names
_RESUME_SECTION_HEADERS = {
    "опыт работы", "обо мне", "ключевые навыки", "навыки", "образование",
    "высшее образование", "курсы", "сертификаты", "контакты", "контактная информация",
    "желаемая должность", "резюме", "профиль", "портфолио", "информация",
    "work experience", "experience", "education", "skills", "about me", "contacts",
}


def redact(text: str) -> Redacted:
    """Redact PII from input text and return Redacted object.

    Placeholders used: [EMAIL], [PHONE], [TG], [URL], [NAME].
    """
    if not text:
        return Redacted(text="", found={"email": [], "phone": [], "telegram": [], "url": [], "name": []})

    found_emails: list[str] = []
    found_phones: list[str] = []
    found_telegrams: list[str] = []
    found_urls: list[str] = []
    found_names: list[str] = []

    working_text = text

    # 1. Emails
    email_pattern = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b")
    for match in email_pattern.finditer(working_text):
        val = match.group()
        if val not in found_emails:
            found_emails.append(val)
    working_text = email_pattern.sub("[EMAIL]", working_text)

    # 2. Telegram (links and @handles)
    # Check t.me links first
    tg_link_pattern = re.compile(r"(?:https?://)?(?:www\.)?(?:t\.me|telegram\.me)/([A-Za-z0-9_]{3,32})", re.IGNORECASE)
    for match in tg_link_pattern.finditer(working_text):
        handle = match.group(1)
        full_match = match.group(0)
        found_telegrams.append(f"@{handle}")
    working_text = tg_link_pattern.sub("[TG]", working_text)

    # Check @handles (not inside email, which was already replaced with [EMAIL])
    tg_handle_pattern = re.compile(r"(?<!\w)@([A-Za-z0-9_]{3,32})\b")
    for match in tg_handle_pattern.finditer(working_text):
        val = match.group(0)
        if val not in found_telegrams:
            found_telegrams.append(val)
    working_text = tg_handle_pattern.sub("[TG]", working_text)

    # 3. URLs (profiles, portfolios, websites)
    url_pattern = re.compile(
        r"\b(?:https?://|www\.)[^\s<>()\"'{}|\\^`\[\]]+"
        r"|(?:github\.com|linkedin\.com|hh\.ru|habr\.com)/[^\s<>()\"'{}|\\^`\[\]]+"
    )
    for match in url_pattern.finditer(working_text):
        val = match.group()
        if val not in found_urls and val not in ("[EMAIL]", "[TG]"):
            found_urls.append(val)
    working_text = url_pattern.sub("[URL]", working_text)

    # 4. Phones (RU formats +7 / 8, spaces, parentheses, dashes)
    phone_pattern = re.compile(
        r"(?:\+7|8)[\s\-\(]*\d{3}[\s\-\)]*\d{3}[\s\-]*\d{2}[\s\-]*\d{2}"
        r"|(?:\+7|8)\d{10}"
        r"|\+?\d{1,3}[\s\-\(]{1,2}\d{2,4}[\s\-\)]{1,2}\d{2,4}[\s\-]?\d{2,4}"
    )
    for match in phone_pattern.finditer(working_text):
        val = match.group().strip()
        # Ensure it has at least 7 digits to avoid matching short numbers/dates
        digits = re.sub(r"\D", "", val)
        if len(digits) >= 10:
            if val not in found_phones:
                found_phones.append(val)
            working_text = working_text.replace(val, "[PHONE]")

    # 5. Names: Heuristic header detection (first 1-4 non-empty lines)
    lines = working_text.splitlines()
    name_extracted = False

    for i, line in enumerate(lines[:5]):
        stripped = line.strip()
        if not stripped:
            continue
        # Skip if contains placeholders or section names
        if any(h in stripped.lower() for h in _RESUME_SECTION_HEADERS):
            continue
        if any(ph in stripped for ph in ("[EMAIL]", "[PHONE]", "[TG]", "[URL]")):
            continue

        # Check Russian 2 or 3 capitalized words (e.g. Иванов Иван Иванович or Смирнов Алексей)
        ru_name_match = re.match(r"^([А-ЯЁ][а-яё]+)\s+([А-ЯЁ][а-яё]+)(?:\s+([А-ЯЁ][а-яё]+))?$", stripped)
        if ru_name_match:
            full_name = stripped
            found_names.append(full_name)
            lines[i] = "[NAME]"
            name_extracted = True
            break

        # Check Latin 2 words (e.g. Alexey Smirnov)
        en_name_match = re.match(r"^([A-Z][a-z]+)\s+([A-Z][a-z]+)$", stripped)
        if en_name_match:
            full_name = stripped
            found_names.append(full_name)
            lines[i] = "[NAME]"
            name_extracted = True
            break

    if name_extracted:
        working_text = "\n".join(lines)

    # Deduplicate and sort found items
    return Redacted(
        text=working_text,
        found={
            "email": list(dict.fromkeys(found_emails)),
            "phone": list(dict.fromkeys(found_phones)),
            "telegram": list(dict.fromkeys(found_telegrams)),
            "url": list(dict.fromkeys(found_urls)),
            "name": list(dict.fromkeys(found_names)),
        },
    )
