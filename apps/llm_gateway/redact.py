"""Local PII redaction (152-FZ) with a safety net (AI-R1).

redact() runs locally and masks emails, Telegram handles, profile links and personal sites,
phone numbers and personal names with placeholders: [EMAIL], [TG], [URL], [PHONE], [NAME].
Every replacement is span-based (re.sub with a function), never str.replace.

assert_clean() re-checks the masked text with broader patterns and searches it for every value
in `found`; the orchestrators skip the LLM when anything is left ("pii_residual").
"""
from __future__ import annotations

import bisect
import re

from taxonomy import clean_key, get_skills_index, normalize_skill

from .pii_lexicon import (
    CITY_WORDS,
    CODE_ANNOTATIONS,
    COMPANY_WORDS,
    FIRST_NAME_ENDINGS,
    FIRST_NAMES_CYR,
    FIRST_NAMES_LAT,
    PATRONYMIC_RE,
    PROFILE_NON_HANDLES,
    ROLE_WORDS,
    SECTION_WORDS,
    SURNAME_SUFFIXES_CYR,
    SURNAME_SUFFIXES_LAT,
    TECH_DOMAIN_TOKENS,
)
from .types import Redacted

# ── patterns ────────────────────────────────────────────────────────────────

# Text is normalised first: invisible characters dropped, exotic spaces and hyphens made ASCII,
# full-width forms and ligatures folded, so "123‑45‑67" or "ivan​@mail.ru" cannot slip through.
_INVISIBLE_RE = re.compile("[­​-‍⁠﻿]")
_NORMALISE = str.maketrans(
    {" ": " ", " ": " ", " ": " ", " ": " ",
     "‐": "-", "‑": "-", "‒": "-", "–": "-", "−": "-",
     "ﬁ": "fi", "ﬂ": "fl"}
    | {chr(c): chr(c - 0xFEE0) for c in range(0xFF01, 0xFF5F)}
)

_TLDS = (
    r"ru|рф|su|com|net|org|io|dev|me|site|pro|tech|app|info|online|space|xyz|ai|co|by|kz|ua|uz|"
    r"so|to|cc|ee|ws|in|cv|website|social|page|link|blog|cloud|codes|design|studio"
)
_EMAIL_RE = re.compile(r"(?<![\w.+-])[\w.+-]+@[\w-]+(?:\.[\w-]+)*\.[A-Za-zА-Яа-яЁё]{2,}(?![A-Za-zА-Яа-яЁё])")
# "ivan @ mail.ru", "ivan [at] gmail [dot] com", "ivan(at)gmail.com", "ivan собака mail.ru",
# and an address wrapped across a line break by the PDF layout
_OBF_AT = r"(?:[ \t]*@[ \t]*\n?[ \t]*|[ \t]*[\[({][ \t]*(?:at|собака)[ \t]*[\])}][ \t]*|[ \t]+собака[ \t]+)"
_OBF_DOT = r"(?:[ \t]*[\[({][ \t]*(?:dot|точка)[ \t]*[\])}][ \t]*|[ \t]+точка[ \t]+|\.\n?)"
_OBF_EMAIL_RE = re.compile(
    rf"(?<![\w.+-])[\w+-][\w.+-]*(?:\.\n[\w.+-]+)?{_OBF_AT}[\w-]+(?:{_OBF_DOT}[\w-]+)*?{_OBF_DOT}(?:{_TLDS})"
    r"(?![A-Za-zА-Яа-яЁё])",
    re.IGNORECASE,
)

_TG_LINK_RE = re.compile(
    r"(?<![\w.])(?:(?:https?://)?(?:www\.)?(?:t|telegram)\.me/(?:joinchat/|\+)?|tg://resolve\?domain=)"
    r"([A-Za-z0-9_]{3,64})",
    re.IGNORECASE,
)

_URL_CHARS = r"[^\s<>()\"'{}|\\^`\[\]]"
# A link the PDF layout wrapped after "/" or "-" continues on the next line
_SCHEME_URL_RE = re.compile(
    rf"(?<![\w])(?:https?://|www\.){_URL_CHARS}+(?:(?<=[/\-])\n{_URL_CHARS}+)?", re.IGNORECASE
)
_BROKEN_SCHEME_RE = re.compile(r"(?i)\b(https?):[ \t]+//")
_DOMAIN_RE = re.compile(
    r"(?<![\w.@/\-])"
    r"((?:[a-zа-яё0-9](?:[a-zа-яё0-9\-]*[a-zа-яё0-9])?\.)+"
    rf"(?:{_TLDS}))"
    rf"(/{_URL_CHARS}*)?"
    r"(?![\w\-])",
    re.IGNORECASE,
)
_TRAILING_PUNCT = ".,;:!?»"

_PROFILE_LABEL_RE = re.compile(
    r"(?<![\w])((?i:github|gitlab|bitbucket|linked[ \t]?in|habr(?:[ \t]+career)?|хабр|гитхаб|гитлаб|"
    r"skype|скайп|vk|вк|vkontakte|вконтакте|instagram|инстаграм|facebook|twitter|kaggle|leetcode|"
    r"codewars|stackoverflow|discord|mastodon)(?i:[ \t]+(?:profile|account|профиль|аккаунт))?)"
    r"(\s*[:\-–—]\s*@?)([A-Za-z0-9/][\w.:/@\-]{2,60})"
)

# "Telegram", "Телеграме", "Телега", "TG/Viber/WhatsApp", "Telegram-ник", "Telegram (личный)"
_TG_LABEL = (
    r"(?i:telegram|телеграм\w*|телега|tg|тг)"
    r"(?:[ \t]*-?[ \t]*(?i:ник|nick|канал|channel|аккаунт|account)"
    r"|[ \t]*\([^)\n@]{1,20}\)"
    r"|[ \t]*/[ \t]*(?i:whatsapp|viber|signal|вотсап|ватсап|вайбер))*"
)
# "Telegram: ivan_petrov", "ТГ - @ivan", "tg @ivan", "Telegram (@ivan)", "Telegram: @ ivan"
_TG_LABELLED_RE = re.compile(
    rf"(?<![\w@])({_TG_LABEL})(\s*[:\-–—]\s*@?[ \t]*|\s+@[ \t]*|\s*\(\s*@)([A-Za-z][A-Za-z0-9_]{{4,31}})(?![\w])"
)
# "Телеграм ivan_petrov_dev": no separator, so the handle must contain "_" or a digit
_TG_SPACED_RE = re.compile(
    rf"(?<![\w@])({_TG_LABEL})(\s+)([A-Za-z][A-Za-z0-9_]*[_\d][A-Za-z0-9_]*)(?![\w])"
)
# "@reduxjs/toolkit" and "@transaction.atomic" are code, never a handle
_BARE_AT_RE = re.compile(r"(?<![\w@./])@([A-Za-z][A-Za-z0-9_]{2,31})(?![\w])(?![./][A-Za-z])")
_CAMEL_RE = re.compile(r"[a-z][A-Z]")
_CONTACT_CUE_RE = re.compile(
    r"telegram|телеграм|\btg\b|\bтг\b|контакт|связ|мессенджер|contact|\[(?:EMAIL|PHONE|URL|TG)\]",
    re.IGNORECASE,
)

# "+7..." may be glued to a label ("Тел+7916...") and any number to the next word ("...45-67Москва")
_PHONE_RE = re.compile(
    r"(?:(?<![\d+])\+\s?\d{1,3}[\s\-./]*(?:\(\s?\d{1,5}\s?\)|\d{1,5})(?:[\s\-./]*\d{1,4}){2,4}"
    r"|(?<![\w+])(?:"
    r"[78][\s\-./]*(?:\(\s?\d{3,5}\s?\)|\d{3,5})(?:[\s\-./]*\d{1,4}){2,4}"
    r"|\(\s?\d{3,5}\s?\)(?:[\s\-./]*\d{1,4}){2,4}"
    r"|\d{3}[\s\-.]\d{3}[\s\-.]\d{2}[\s\-.]\d{2}"
    r"|9\d{2}[\s\-.]?\d{3}[\s\-.]?\d{2}[\s\-.]?\d{2}"
    r"|9\d{2}[\s\-.]?\d{7}"
    r"))(?!\d)"
)
# Safety net: any long run of digits and separators on one line
_DIGIT_RUN_RE = re.compile(r"(?:(?<![\d+])\+|(?<![\w+]))\d[\d \t\-./()]{8,30}\d(?!\d)")
_YEAR_RE = re.compile(r"(?:19|20)\d\d")
_MONTH_YEAR_RE = re.compile(r"(?<!\d)\d{1,2}[./](?:19|20)\d\d(?!\d)")
_MONEY_RE = re.compile(r"\d{1,3}(?:[\s\xa0]\d{3})+(?:\s*[-–—]\s*\d{1,3}(?:[\s\xa0]\d{3})+)?")
_IPV4_RE = re.compile(r"\d{1,3}(?:\.\d{1,3}){3}")

# Russian plus the Ukrainian, Belarusian and Kazakh letters
_CU = "А-ЯЁЄІЇҐЎӘҒҚҢӨҰҮҺ"
_CL = "а-яёєіїґўәғқңөұүһ"
_CYR_WORD = rf"[{_CU}][{_CL}]+(?:-[{_CU}][{_CL}]+)?"
_CYR_CAPS = rf"[{_CU}]{{2,}}(?:-[{_CU}]{{2,}})?"
_LAT_WORD = r"[A-Z][a-z]+(?:-[A-Z][a-z]+)?"
_LAT_CAPS = r"[A-Z]{2,}(?:-[A-Z]{2,})?"
_NAME_TOKEN = rf"(?:{_CYR_WORD}|{_CYR_CAPS}|{_LAT_WORD}|{_LAT_CAPS})"

# The candidate's own name, labelled at the start of a line: "ФИО: Иванов Иван", "Имя: Дмитрий"
_OWN_LABEL_RE = re.compile(
    r"^[ \t•*\-]*(?i:ф\.?[ \t]?и\.?[ \t]?о\.?|имя\s+и\s+фамилия|фамилия\s+и\s+имя|имя|фамилия|отчество|"
    r"full\s+name|first\s+name|last\s+name|surname|name)"
    rf"[ \t]*[:\-–—][ \t]*({_NAME_TOKEN}(?:[ \t]+{_NAME_TOKEN}){{0,2}})",
    re.MULTILINE,
)
# "Меня зовут Тагир Алиханлы", "My name is Anna Smirnova"
_INTRO_RE = re.compile(
    rf"(?i:меня[ \t]+зовут|my[ \t]+name[ \t]+is)[ \t]+({_NAME_TOKEN}(?:[ \t]+{_NAME_TOKEN}){{0,2}})"
)
# Somebody else's name: referees and contact persons, or a manager/mentor that looks like a name
_OTHER_LABEL_RE = re.compile(
    r"(?<![\w])(?:((?i:рекомендации|рекомендатели|рекомендатель|рекомендует|контактное\s+лицо|"
    r"references?|referees?|hr-менеджер\w*|hr-специалист\w*|hr|рекрутер\w*|recruiter))|(?i:руководитель|ментор|mentor|manager))"
    rf"\s*[:\-–—]?\s*({_NAME_TOKEN}(?:[ \t]+{_NAME_TOKEN}){{1,2}})"
)
# Two or three capitalised words in the same script, anywhere in the text
_BODY_NAME_RE = re.compile(
    rf"(?<![\w\-])({_CYR_WORD}(?:[ \t]+{_CYR_WORD}){{1,2}}|{_LAT_WORD}(?:[ \t]+{_LAT_WORD}){{1,2}})(?![\w\-])"
)
# "Петров А.В.", "А. В. Петров": a surname with initials, usually a referee or a manager
_INITIALS_RE = re.compile(
    rf"(?<![\w.])(?:({_CYR_WORD})[ \t]+[{_CU}]\.[ \t]?[{_CU}]\.|[{_CU}]\.[ \t]?[{_CU}]\.[ \t]?({_CYR_WORD}))"
)
# "Petrov A.", "Kuznetsov D. A.", "A. Petrov" in publications; the surname ending must look Russian
_LAT_INITIALS_RE = re.compile(
    r"(?<![\w.])(?:([A-Z][a-z]+)[ \t]+[A-Z]\.(?:[ \t]?[A-Z]\.)?|[A-Z]\.[ \t]?(?:[A-Z]\.[ \t]?)?([A-Z][a-z]+))"
)
_HEADER_PREFIX_RE = re.compile(r"^(?i:резюме|cv|resume|curriculum\s+vitae)\s*[:\-–—]\s*")
_HEADER_SPLIT_RE = re.compile(r"\s*(?:[,|(:;•·/]|\s[-–—]\s|[–—])\s*")
_PATRONYMIC_TOKEN_RE = re.compile(rf"[а-яё]+{PATRONYMIC_RE}")
_PLACEHOLDER_RUN_RE = re.compile(r"\[NAME\](?:[ \t\-]+\[NAME\])+")

_HEADER_LINES = 10


# ── helpers ─────────────────────────────────────────────────────────────────

def _is_skill(token: str) -> bool:
    return clean_key(token) in get_skills_index()


def _is_tech_domain(host: str) -> bool:
    if host.lower() in TECH_DOMAIN_TOKENS or _is_skill(host):
        return True
    match = normalize_skill(host)  # canonical spellings: "asp.net core", ".net"
    return match is not None and match.method in ("exact", "alias")


def _is_non_name_word(token: str) -> bool:
    low = token.lower()
    if low in ROLE_WORDS or low in SECTION_WORDS or low in CITY_WORDS or low in COMPANY_WORDS:
        return True
    return any(part in ROLE_WORDS or part in CITY_WORDS for part in low.split("-")) or _is_skill(token)


def _is_cyrillic(token: str) -> bool:
    return bool(re.match(rf"[{_CU}{_CL}]", token))


def _is_first_name(token: str) -> bool:
    low = token.lower()
    names = FIRST_NAMES_CYR if _is_cyrillic(token) else FIRST_NAMES_LAT
    if low in names:
        return True
    if len(low) < 4:
        return False
    # inflected forms: drop up to 3 letters and look for a name whose stem matches
    for cut in (1, 2, 3):
        base, ending = low[:-cut], low[-cut:]
        if ending not in FIRST_NAME_ENDINGS:
            continue
        for tail in ("", "а", "я", "й", "ь"):
            if base + tail in names:
                return True
    return False


def _is_patronymic(token: str) -> bool:
    return bool(_PATRONYMIC_TOKEN_RE.fullmatch(token.lower()))


def _name_score(tokens: list[str]) -> int:
    score = 0
    if any(_is_first_name(t) for t in tokens):
        score += 3
    if any(_is_patronymic(t) for t in tokens):
        score += 3
    suffixes = SURNAME_SUFFIXES_CYR if _is_cyrillic(tokens[0]) else SURNAME_SUFFIXES_LAT
    if any(t.lower().endswith(suffixes) for t in tokens):
        score += 1
    return score


def _same_script(tokens: list[str]) -> bool:
    return len({_is_cyrillic(t) for t in tokens}) == 1


def _is_number_not_phone(raw: str) -> bool:
    """Years, month.year dates, money amounts and IPv4 addresses are long digit runs too."""
    if raw.lstrip().startswith("+"):
        return False
    stripped = raw.strip()
    return bool(
        all(_YEAR_RE.fullmatch(g) for g in re.findall(r"\d+", raw))  # "2018 2019 2020 2021"
        or _MONTH_YEAR_RE.search(raw)  # "03.2019 - 05.2023"
        or _MONEY_RE.fullmatch(stripped)  # "250 000 - 300 000"
        or _IPV4_RE.fullmatch(stripped)
    )


def _looks_like_phone(raw: str) -> bool:
    digits = re.sub(r"\D", "", raw)
    return 10 <= len(digits) <= 15 and not _is_number_not_phone(raw)


def _is_profile_handle(value: str) -> bool:
    """"Kaggle: Expert", "LeetCode — 500" and "VK — Senior" are not profile handles."""
    return value.lower() not in PROFILE_NON_HANDLES and not re.fullmatch(r"\d+\+?", value)


def _is_code_handle(handle: str, *, in_contacts: bool) -> bool:
    """A code annotation; outside the contact block also "@SpringBootTest", "@BotFather"."""
    if handle.lower() in CODE_ANNOTATIONS:
        return True
    return not in_contacts and bool(_CAMEL_RE.search(handle)) and not re.search(r"[_\d]", handle)


def _split_punct(value: str) -> tuple[str, str]:
    core = value.rstrip(_TRAILING_PUNCT)
    return core, value[len(core):]


def _token_pattern(token: str) -> re.Pattern[str] | None:
    """Whole-word pattern for a name token and its inflected forms (case-sensitive)."""
    if len(token) < 2:
        return None
    if len(token) <= 3:
        stem, tail = token, ""
    else:
        stem = token[:-2] if len(token) >= 6 else token[:-1] if len(token) == 5 else token
        tail = "{0,4}"
    title = stem[:1].upper() + stem[1:].lower()
    caps = stem.upper()
    letters_low, letters_up = f"[{_CL}a-z]", f"[{_CU}A-Z]"
    if tail:
        body = f"{re.escape(title)}{letters_low}{tail}|{re.escape(caps)}{letters_up}{tail}"
    else:
        body = f"{re.escape(title)}|{re.escape(caps)}"
    return re.compile(rf"(?<![\w])(?:{body})(?![\w])")


# ── redaction ───────────────────────────────────────────────────────────────

def redact(text: str, *, header_names: bool = True) -> Redacted:
    """Mask all PII in `text` locally (152-FZ).

    header_names: look for the candidate's name in the first lines (CVs). JD parsing turns it
    off so a company name in the title is not taken for a person.
    """
    found: dict[str, list[str]] = {"email": [], "phone": [], "telegram": [], "url": [], "name": []}
    if not text:
        return Redacted(text="", found=found)

    def add(kind: str, value: str) -> None:
        value = value.strip()
        if value and value not in found[kind]:
            found[kind].append(value)

    working = _BROKEN_SCHEME_RE.sub(r"\1://", _INVISIBLE_RE.sub("", text).translate(_NORMALISE))

    # 1. Emails, then the obfuscated or wrapped ones
    def _email(m: re.Match[str]) -> str:
        add("email", m.group(0))
        return "[EMAIL]"

    working = _EMAIL_RE.sub(_email, working)
    working = _OBF_EMAIL_RE.sub(_email, working)

    # 2. Telegram links
    def _tg_link(m: re.Match[str]) -> str:
        add("telegram", "@" + m.group(1))
        return "[TG]"

    working = _TG_LINK_RE.sub(_tg_link, working)

    # 3. Links and personal sites
    def _url(m: re.Match[str]) -> str:
        core, punct = _split_punct(m.group(0))
        add("url", core)
        return "[URL]" + punct

    working = _SCHEME_URL_RE.sub(_url, working)

    def _domain(m: re.Match[str]) -> str:
        if not m.group(2) and _is_tech_domain(m.group(1)):
            return m.group(0)  # ASP.NET, Socket.IO
        return _url(m)

    working = _DOMAIN_RE.sub(_domain, working)

    def _profile(m: re.Match[str]) -> str:
        core, punct = _split_punct(m.group(3))
        if not _is_profile_handle(core):
            return m.group(0)
        add("url", core)
        return m.group(1) + m.group(2).rstrip("@") + "[URL]" + punct

    working = _PROFILE_LABEL_RE.sub(_profile, working)

    # 4. Telegram handles: labelled ones are contacts; a bare @handle is masked everywhere but
    #    recorded only in the contact block, and code annotations are left alone.
    def _tg_labelled(m: re.Match[str]) -> str:
        handle = m.group(3)
        if len(handle) > 32 or handle.lower() in CODE_ANNOTATIONS:
            return m.group(0)
        add("telegram", "@" + handle)
        return m.group(1) + m.group(2).rstrip("@") + "[TG]"

    working = _TG_LABELLED_RE.sub(_tg_labelled, working)
    working = _TG_SPACED_RE.sub(_tg_labelled, working)

    line_starts, contact_lines = _contact_lines(working)

    def _bare_at(m: re.Match[str]) -> str:
        handle = m.group(1)
        line_no = bisect.bisect_right(line_starts, m.start()) - 1
        if _is_code_handle(handle, in_contacts=line_no in contact_lines):
            return m.group(0)
        if line_no in contact_lines and len(handle) >= 5:
            add("telegram", "@" + handle)
        return "[TG]"

    working = _BARE_AT_RE.sub(_bare_at, working)

    # 5. Phones
    def _phone(m: re.Match[str]) -> str:
        raw = m.group(0)
        if not _looks_like_phone(raw):
            return raw
        add("phone", raw)
        return "[PHONE]"

    working = _PHONE_RE.sub(_phone, working)

    # 6. Names
    own_name, other_names, working = _find_names(working, header_names=header_names)
    if own_name:
        add("name", own_name)
    for name in other_names:
        add("name", name)
    for name in found["name"]:
        for token in re.split(r"[\s\-]+", name):
            pattern = _token_pattern(token)
            if pattern is not None:
                working = pattern.sub("[NAME]", working)
    working = _PLACEHOLDER_RUN_RE.sub("[NAME]", working)

    return Redacted(text=working, found=found, full_name=own_name)


def _contact_lines(text: str) -> tuple[list[int], set[int]]:
    """Line start offsets, and the lines that form the contact block."""
    lines = text.split("\n")
    starts: list[int] = []
    offset = 0
    contact: set[int] = set()
    non_empty = 0
    for idx, line in enumerate(lines):
        starts.append(offset)
        offset += len(line) + 1
        if line.strip():
            non_empty += 1
            if non_empty <= _HEADER_LINES or _CONTACT_CUE_RE.search(line):
                contact.add(idx)
    return starts, contact


def _find_names(text: str, *, header_names: bool) -> tuple[str | None, list[str], str]:
    """Return (own name, other names, text with the header name masked)."""
    own: str | None = None
    others: list[str] = []

    def valid(tokens: list[str]) -> bool:
        return _same_script(tokens) and not any(_is_non_name_word(t) for t in tokens)

    # "Фамилия: Петров", "Имя: Иван", "Отчество: Сергеевич": the first is the name, the rest too
    for m in [*_OWN_LABEL_RE.finditer(text), *_INTRO_RE.finditer(text)]:
        tokens = m.group(1).split()
        if not valid(tokens) or not (len(tokens) > 1 or _name_score(tokens) > 0):
            continue
        if own is None:
            own = m.group(1)
        elif m.group(1) != own and m.group(1) not in others:
            others.append(m.group(1))

    for m in _OTHER_LABEL_RE.finditer(text):
        tokens = m.group(2).split()
        # "Рекомендации:" is followed by a name; "Руководитель Отдела Продаж" may be a heading
        if valid(tokens) and (m.group(1) or _name_score(tokens) > 0):
            others.append(m.group(2))

    lines = text.split("\n")
    if header_names:
        candidates: list[tuple[int, int, str]] = []  # (score, line index, name)
        seen = 0
        for idx, line in enumerate(lines):
            stripped = line.strip()
            if not stripped:
                continue
            seen += 1
            if seen > _HEADER_LINES:
                break
            parts = _HEADER_SPLIT_RE.split(_HEADER_PREFIX_RE.sub("", stripped))
            for pos, part in enumerate(p.strip() for p in parts):
                tokens = part.split()
                if not 2 <= len(tokens) <= 3 or not valid(tokens):
                    continue
                if not all(re.fullmatch(_NAME_TOKEN, t) for t in tokens):
                    continue
                score = _name_score(tokens)
                # Later parts ("Python-разработчик — Алиев Тагир") need some evidence. A Latin
                # pair needs a known first name ("Spring Boot", "Google Cloud") unless it opens
                # the CV ("Anastasiia Zhukovskaia").
                if pos > 0 and score == 0:
                    continue
                if not _is_cyrillic(tokens[0]) and score == 0 and seen > 1:
                    continue
                candidates.append((score, idx, part))

        # Lines with a first name or a patronymic are names. Otherwise take the single best line
        # ("Нурланов Айдар" scores on the surname, "Ли Мин" is the first two-word line).
        strong = [c for c in candidates if c[0] >= 3]
        accepted = strong or ([max(candidates, key=lambda c: (c[0], -c[1]))] if candidates else [])
        if accepted:
            best = max(accepted, key=lambda c: (c[0], -c[1]))
            if own is None:
                own = best[2]
            elif best[2] != own:
                others.append(best[2])
            for _score, idx, part in accepted:
                lines[idx] = lines[idx].replace(part, "[NAME]", 1)
                if part != own and part not in others:
                    others.append(part)
        text = "\n".join(lines)

    # Names anywhere: a first name or a patronymic next to other capitalised words
    for m in _BODY_NAME_RE.finditer(text):
        tokens = m.group(1).split()
        cores = [i for i, t in enumerate(tokens) if len(t) >= 3 and (_is_first_name(t) or _is_patronymic(t))]
        if not cores or _is_non_name_word(tokens[cores[0]]):
            continue
        lo = hi = cores[0]
        while lo > 0 and not _is_non_name_word(tokens[lo - 1]):
            lo -= 1
        while hi + 1 < len(tokens) and not _is_non_name_word(tokens[hi + 1]):
            hi += 1
        if hi == lo:
            continue  # a lone first name next to a company or a city
        name = " ".join(tokens[lo:hi + 1])
        if name != own and name not in others:
            others.append(name)

    for m in [*_INITIALS_RE.finditer(text), *_LAT_INITIALS_RE.finditer(text)]:
        surname = m.group(1) or m.group(2)
        if not _is_cyrillic(surname) and not surname.lower().endswith(SURNAME_SUFFIXES_LAT):
            continue
        if not _is_non_name_word(surname) and surname != own and surname not in others:
            others.append(surname)

    return own, others, text


# ── safety net ──────────────────────────────────────────────────────────────

def assert_clean(redacted: Redacted) -> tuple[bool, str | None]:
    """Re-check the masked text; (False, "pii_residual") if anything personal is left."""
    text = redacted.text
    if not text:
        return True, None
    if _has_residual(text, redacted.found):
        return False, "pii_residual"
    return True, None


def _has_residual(text: str, found: dict[str, list[str]]) -> bool:
    text = _INVISIBLE_RE.sub("", text).translate(_NORMALISE)
    if (
        _EMAIL_RE.search(text)
        or _OBF_EMAIL_RE.search(text)
        or _TG_LINK_RE.search(text)
        or _SCHEME_URL_RE.search(text)
    ):
        return True
    for m in _DOMAIN_RE.finditer(text):
        if m.group(2) or not _is_tech_domain(m.group(1)):
            return True
    for m in _PROFILE_LABEL_RE.finditer(text):
        if _is_profile_handle(_split_punct(m.group(3))[0]):
            return True
    for regex in (_TG_LABELLED_RE, _TG_SPACED_RE):
        for m in regex.finditer(text):
            if m.group(3).lower() not in CODE_ANNOTATIONS:
                return True
    line_starts, contact_lines = _contact_lines(text)
    for m in _BARE_AT_RE.finditer(text):
        line_no = bisect.bisect_right(line_starts, m.start()) - 1
        if not _is_code_handle(m.group(1), in_contacts=line_no in contact_lines):
            return True
    for m in _DIGIT_RUN_RE.finditer(text):
        raw = m.group(0)
        if len(re.sub(r"\D", "", raw)) >= 10 and not _is_number_not_phone(raw):
            return True

    lowered = text.lower()
    for kind in ("email", "phone", "telegram", "url"):
        for value in found.get(kind, []):
            value = value.lstrip("@").strip().lower()
            if len(value) >= 4 and value in lowered:
                return True
    for name in found.get("name", []):
        for token in re.split(r"[\s\-]+", name):
            if len(token) >= 3 and re.search(rf"(?<![\w]){re.escape(token)}(?![\w])", text, re.IGNORECASE):
                return True
    return False
