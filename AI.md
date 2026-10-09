# AI.md: LLM API & Language Tasks (owner: AI / LLM engineer)

> **Audience:** the AI/LLM engineer and their AI coding agent.
> **Scope:** the LLM gateway (GigaChat + rule-based fake), PDF text extraction, PII redaction, resume and job-description parsing, the skill taxonomy and `normalize_skill()`, grounded "why" sentences, and offline LLM-assisted drafting of item content.
> **Updated:** 2026-10-09, after the review of PR #6 (`feat/ai-llm-gateway`, commit `e84dddf`). Related files: [BE.md](BE.md) (endpoints and Celery wiring), [ML.md](ML.md) (grading, matching, blueprints), [FE1.md](FE1.md), [FE2.md](FE2.md).
> **Start here:** read §1 (review verdict), fix everything in §4 on the same branch, then finish §5. The contract in §3 is still authoritative.

---

## 0. Ownership Rules

| You own | You do **not** own |
|---|---|
| `apps/llm_gateway/`: gateway protocol, `FakeLlm`, `GigaChatLlm`, `redact`, `extract_text`, `parse_resume`, `parse_jd`, `phrase` | Endpoints, upload limits, Celery tasks and queues, persistence (BE) |
| `apps/taxonomy/` + `content/skills.yaml`: skill ids, aliases, topics, related skills, `normalize_skill()` | Syncing `skills.yaml` into the `Skill` table (`manage.py sync_taxonomy`, BE) |
| Prompts (versioned files), response schemas, caching keys, fallbacks | Grading and scoring math (ML). **An LLM never touches a grade** |
| `tools/draft_families/`: offline LLM drafting of item families and concept-MCQ pools for ML to review | Final item families, IRT parameters, verify harness (ML) |
| The model usage register `docs/MODELS.md` (QA requires every model and use case to be documented) | UI (FE1, FE2) |

**Hard invariants:**
1. **No LLM in grading or ranking.** Your output only pre-fills forms, extracts skills and rephrases facts that the scorer already computed.
2. **152-FZ: redact PII before every LLM call.** Names, emails, phones, Telegram handles and profile URLs are extracted **locally** and never sent. Use only domestic LLMs (GigaChat; a YandexGPT adapter is optional). No cross-border personal data. **If you are not sure the text is clean, don't send it**: use the rules.
3. **Everything degrades gracefully, and visibly.** Any exception, timeout or invalid JSON falls back to `FakeLlm` (rules) **in the orchestrator**, which reports `source="rules"`. The product must work with `LLM_PROVIDER=fake` and no network, and CI always runs that way.
4. **Determinism where it matters.** The same input with the same prompt version gives a cached output. Use temperature ≤ 0.2 for extraction.
5. **No PII in logs, test fixtures or the repo.** Use synthetic CVs only, and log input hashes instead of texts.
6. **Unknown means null.** Never invent a value (title, specialization, grade, format, salary type). The form asks the user.

---

## 1. Status: review of PR #6 (`feat/ai-llm-gateway` @ `e84dddf`, 2026-10-09)

**Verdict: changes requested. Do not merge PR #6** until every item in §4 "Blockers" and "Must fix" is done and checked. Push fixes to the same branch (one commit per AI-R item, titled with the ID), then ask for a re-review.

**What was checked:** `pytest tests/ai` 18/18 green; the full suite (135 tests) is green; `manage.py check` is clean; **`ruff` reports 21 errors** (the `verify` gate fails). Every bug below was reproduced with a probe script on the PR branch, not guessed.

**Good, keep it:**
- Package layout and the §3 dataclasses/protocols match the contract exactly.
- TLS verification is never disabled; the Russian Trusted Root CA bundle is shipped in `certs/`.
- Offline mode works: with no network everything runs on rules, and CI needs no key.
- The 10 seed skill ids are preserved; prompts are versioned files in Russian with an explicit null rule and enum lists.
- No LLM anywhere near grading.

**Completion estimate (against §5):**

| Task | Done | Main gaps |
|---|---|---|
| AI-0 Contract | 90% | Contract is right; imports and fallback placement need fixing (AI-R2, AI-R14) |
| AI-1 Taxonomy | 45% | 70 skills, not "100+" as the commit says (v1 target ~300); no 100-input messy set; fuzzy matching is dead code and wrong when enabled; no lookalike handling |
| AI-2 PDF + redaction | 55% | PII leaks to the LLM (AI-R1); `pdfplumber` fallback is dead code (not installed) |
| AI-3 FakeLlm rules | 65% | Salary, salary type, specialization and grade heuristics are wrong on common inputs; invented defaults |
| AI-4 GigaChat adapter | 55% | No schema validation or repair attempt; retry reuses a stale token; token cache never reused; timeout budget too long; no recorded responses; no evidence of a live run |
| AI-5 Resume/JD parsing | 45% | Cache poisoning and a false `source`; no fixtures (3 PDF CVs, 5 JDs), no recorded responses, no live test |
| AI-6 MODELS.md | 85% | Claims logging that does not exist |
| AI-7 "Why" sentence (P1) | 40% | Grounding checks numbers only, not skills |
| AI-8, AI-9, AI-10 (P1) | 0% | Not started |

**P0 ≈ 63% done; all of AI.md ≈ 52%. Code quality: 5/10.**

---

## 2. Target Layout

```text
apps/llm_gateway/                 # named llm_gateway (not llm) to avoid clashing with the PyPI "llm" package
  __init__.py     get_gateway(), parse_resume(), parse_jd(), phrase()
  types.py        ResumeDraft, JdDraft, ResumeParseResult, JdParseResult, Redacted
  schema.py       validate_resume_payload(), validate_jd_payload(), enum synonym maps   (AI-R3)
  base.py         LlmGateway protocol, Cache protocol, GatewayConfig, LlmError hierarchy
  fake.py         FakeLlm: regex + taxonomy rules (fallback, CI default)
  gigachat.py     GigaChatLlm: token cache, JSON output, timeout, retry
  redact.py       redact(): local PII extraction and masking; assert_clean() safety net (AI-R1)
  pdf_text.py     extract_text(): pypdf, then pdfplumber fallback; raises UnreadablePdf
  resume.py       parse_resume() orchestration
  jd.py           parse_jd() orchestration
  phrase.py       phrase() with template fallback and a grounding check (P1)
  logging.py      log_llm_call(): structured, text-free log line (AI-R12)
  prompts/        resume.v1.md  jd.v1.md  phrase.v1.md   (versioned; the version is part of the cache key)
apps/taxonomy/
  loader.py       load_skills(path="content/skills.yaml"); builds lookup indexes once
  normalize.py    normalize_skill(), normalize_many(), extract_skills()
content/skills.yaml
tools/draft_families/             # offline only; never imported by the app (AI-8, AI-9)
tests/ai/                         # no network; recorded GigaChat responses; synthetic CVs/JDs in fixtures/
  fixtures/cv/*.pdf  fixtures/jd/*.txt  fixtures/gigachat/*.json  fixtures/pii_cases.yaml  fixtures/skills_messy.yaml
docs/MODELS.md                    # model usage register
```

**Purity:** keep these packages free of the ORM and of views. Read configuration through `GatewayConfig`; BE builds it from Django settings and passes it, or `get_gateway()` builds it lazily from `django.conf.settings`. Caching goes through a `Cache` protocol (`get(key)`, `set(key, value, ttl)`), and BE passes Django's Redis cache.

**Imports:** `apps/` is on `sys.path` (CLAUDE.md, BE.md A9). Inside a package use relative imports (`from .types import ...`). Across packages use top-level names: `from taxonomy import normalize_many`, `from assessment.engine.blueprint import blueprint_for`. **Never `from apps.xxx import ...`**: it loads a second copy of the module (two taxonomy caches, two `UnreadablePdf` classes that don't match in `except`). Tests import the same way (`from llm_gateway import parse_resume`).

**Dependencies (add in your PRs; BE reviews):** `rapidfuzz`, `pdfplumber`, `PyYAML` (today it only arrives through drf-spectacular), optionally `natasha` for Russian name detection. Either keep `urllib` or switch to the official `gigachat` SDK / `httpx` (+ `respx` for tests).

---

## 3. The Contract (you publish it; BE wires it)

Unchanged from the original version, plus two **additive** fields (`fallback_reason`) and the error hierarchy. Enum values must match `core.enums`: specializations `backend|frontend|ml_data`, grades `intern|junior|middle|senior`, formats `office|hybrid|remote`, salary `gross|net`. Output keys must match the **flat** Django serializer fields (`salary_min`, `salary_max`, `salary_type`; see BE.md §2.3).

```python
# ── apps/llm_gateway/types.py ──
from dataclasses import dataclass, field
from typing import Literal

Source = Literal["llm", "rules"]

@dataclass(frozen=True)
class Redacted:
    text: str                              # PII replaced with placeholders: [EMAIL], [PHONE], [NAME], [URL], [TG]
    found: dict[str, list[str]]            # {"email": [...], "phone": [...], "telegram": [...], "url": [...], "name": [...]}

@dataclass(frozen=True)
class ResumeDraft:                         # what the LLM (or rules) extracts from REDACTED text; always schema-valid
    specialization: str | None
    claimed_grade: str | None
    years_experience: float | None
    roles: list[str]
    skills_raw: list[str]                  # as written in the CV
    work_formats: list[str]
    salary_min: int | None; salary_max: int | None; salary_type: str | None
    city: str | None
    about: str | None                      # ≤ 500 chars, no PII
    experience_text: str | None

@dataclass(frozen=True)
class ResumeParseResult:
    prefill: dict                          # keys = CandidateProfileUpdateSerializer fields; "skills" = list of skill ids
                                           # string fields use "" (not None) for unknown, lists use [], numbers use None
    contacts: dict                         # {"full_name", "email", "phone", "telegram"} from local redaction only;
                                           # BE stores them only after the candidate confirms the form
    unknown_terms: list[str]               # raw skills that normalize_skill() could not map
    source: Source                         # "llm" only if a validated LLM answer (fresh or cached) was used
    fallback_reason: str | None = None     # NEW: "provider_fake" | "timeout" | "http_error" | "invalid_json" |
                                           # "schema" | "pii_residual" | "no_key" | None. For logs and the Lab page

@dataclass(frozen=True)
class JdDraft:
    title: str | None; specialization: str | None; grades: list[str]
    must_skills_raw: list[str]; nice_skills_raw: list[str]
    work_formats: list[str]; location: str | None
    salary_min: int | None; salary_max: int | None; salary_type: str | None
    team_context: str | None; description: str | None

@dataclass(frozen=True)
class JdParseResult:
    draft: dict                            # keys = PositionSerializer writable fields; skills as ids; unknown → None / []
    unknown_terms: list[str]
    blueprint: list[dict]                  # [{"topic": str, "weight": float}] from ML's blueprint_for(); [] until available
    source: Source
    fallback_reason: str | None = None     # NEW, same values as above

class UnreadablePdf(Exception): ...        # BE maps it to 422 `unreadable_pdf`

# ── apps/llm_gateway/base.py ──
class LlmError(Exception): ...             # NEW: base for provider failures; carries .reason (one of the fallback reasons)
class LlmUnavailable(LlmError): ...        # auth, timeout, 5xx, 429, network
class LlmSchemaError(LlmError): ...        # invalid JSON or schema after the repair attempt

class LlmGateway(Protocol):
    name: str                                         # "fake" | "gigachat"
    def resume(self, redacted_text: str) -> ResumeDraft: ...   # GigaChat RAISES LlmError; it never falls back itself
    def jd(self, text: str) -> JdDraft: ...
    def phrase(self, facts: list[str]) -> str: ...    # P1

class Cache(Protocol):
    def get(self, key: str): ...
    def set(self, key: str, value, ttl: int): ...

# ── apps/llm_gateway/__init__.py ──  (sync functions; BE calls them inside Celery tasks)
def get_gateway(config: "GatewayConfig | None" = None) -> LlmGateway: ...   # process-wide cached instance per config
def redact(text: str) -> Redacted: ...
def extract_text(pdf_bytes: bytes) -> str: ...                       # raises UnreadablePdf
def parse_resume(pdf_bytes: bytes, *, gateway: LlmGateway | None = None,
                 cache: Cache | None = None) -> ResumeParseResult: ...
def parse_jd(text: str, *, gateway: LlmGateway | None = None,
             cache: Cache | None = None) -> JdParseResult: ...
def phrase(facts: list[str], *, gateway: LlmGateway | None = None) -> str: ...   # P1; template fallback

# ── apps/taxonomy/normalize.py ──
@dataclass(frozen=True)
class SkillMatch:
    skill_id: str; name: str; score: float
    method: Literal["exact", "alias", "fuzzy", "embedding"]

def normalize_skill(raw: str) -> SkillMatch | None: ...     # exact id/name → alias → guarded fuzzy (AI-R5)
def normalize_many(raws: list[str]) -> tuple[list[SkillMatch], list[str]]: ...   # (matches, unknown_terms)
def extract_skills(text: str) -> tuple[list[SkillMatch], list[str]]: ...         # used by the rules fallback
```

**Orchestration inside `parse_resume`** (the only place where fallback happens):
1. `extract_text` (raises `UnreadablePdf` for scanned or image-only PDFs).
2. `redact`, then `assert_clean(redacted)`. If residual PII is detected, skip the LLM: rules, `fallback_reason="pii_residual"`.
3. Check the cache, keyed by `sha256(kind + prompt_version + model + redacted_text)`. A hit is used only if it was stored by a validated LLM call; it returns `source="llm"`.
4. `gateway.resume()`. On **any** exception (`LlmError` or anything else), fall back to `FakeLlm`, set `source="rules"` and `fallback_reason`. Store in the cache **only** a validated LLM result.
5. `validate_resume_payload()` on whatever came back (LLM, cache or rules), then `normalize_many(skills_raw)`.
6. Map the draft onto serializer keys and fill `contacts` from `Redacted.found`.
7. Log one structured line (AI-R12).

`parse_jd` follows the same steps, then calls ML's `blueprint_for(spec, skill_ids)` (AI-R13).

**How BE uses it:**
- `POST /candidates/me/resume`: BE validates ≤ 5 MB and PDF MIME, runs a Celery task `llm.parse_resume` on queue `llm` (worker `--concurrency=1`), and waits ≤ 15 s. On timeout it calls `parse_resume(..., gateway=FakeLlm())` inline.
- `POST /positions/parse`: same pattern.
- Profile and position saves: BE calls `normalize_many()`.
- Offer creation (P1): BE calls `phrase()`.

---

## 4. Rework for PR #6 (do all of this before the merge)

Each item: **Problem** (what is wrong, with the reproducer), **Fix** (what to do), **Acceptance** (a test that must exist and pass). Write the failing test first. IDs `AI-R*` are stable; reference them in commit titles.

### Blockers

- [ ] **AI-R1 · PII leaks to GigaChat (152-FZ, invariant 2).**
  - **Problem.** `redact.py` only treats a line as a name if it is exactly 2–3 capitalised words, alone on a line, in the first 5 lines, and it replaces only that line. Reproduced leaks:
    - `ИВАНОВ ИВАН` (all caps), `Петров Иван, Python-разработчик` (name + title on one line), `Анна Римская-Корсакова` (hyphenated) are not redacted.
    - `Python Developer\n…\nРекомендации: Сидоров Петр Алексеевич, CTO`: the title line is taken as the name (`found["name"] = ["Python Developer"]`) and the real name is sent to the LLM. Any name below the header (references, "Я, Иван Петров, …") is sent too.
    - `Telegram: ivan_petrov` (no `@`), `vk.com/ivan.petrov`, `gitlab.com/ivanov`, `ivanov.dev` are not redacted.
    - `+375 29 123-45-67` becomes `[PHONE]-67` (partial match, the tail of the number leaks).
    - False positives that corrupt the text and `contacts`: `2018 2019 2020 2021` is masked as a phone; `@dataclass`, `@pytest` become Telegram handles and `contacts.telegram` is `"@dataclass"`.
    - `FakeLlm.resume()` copies `redacted_text[:1500]` into `experience_text`, so whatever redaction missed is saved into the profile that employers see.
  - **Fix.**
    1. **Names.** Combine three detectors and take the union:
       - header heuristic over the first 10 non-empty lines: 2–3 tokens, Title Case **or** ALL CAPS, hyphenated parts allowed (`[А-ЯЁ][а-яё]+(?:-[А-ЯЁ][а-яё]+)?`), the name may be followed by `,`/`—` and a title on the same line;
       - labelled names anywhere: `ФИО:`, `Имя:`, `Name:`, `Рекомендации:`, `Контактное лицо:`;
       - `natasha` NER (`NewsNERTagger`, `PER` spans) over the whole text, if you add the dependency (recommended).
       - Reject a candidate if any token is a taxonomy skill name/alias or a role word (`developer`, `engineer`, `разработчик`, `инженер`, `lead`, `senior`, …). This is what stops `Python Developer` being taken as the name.
       - After a name is found, mask **every occurrence of each of its tokens** (surname, first name, patronymic) across the whole text, including inflected forms (match the stem: the token minus its last 1–2 letters, for tokens ≥ 5 letters, followed by Cyrillic letters).
    2. **Telegram.** `t.me/…`, `telegram.me/…`; labelled handles with or without `@` (`(?:telegram|телеграм|tg|тг)\s*[:\-–]?\s*@?([A-Za-z0-9_]{5,32})`). Mask every bare `@handle` in the text (privacy first), but put it into `found["telegram"]` only when it is labelled or stands in the contact block, and never when it is in a stoplist of code annotations (`dataclass`, `pytest`, `property`, `staticmethod`, `classmethod`, `override`, `Override`, `Transactional`, `Component`, `Injectable`, `Input`, `Output`, `app`, `router`, …). `contacts.telegram` must never be a code annotation.
    3. **URLs.** Keep scheme/`www.` URLs. Add bare profile domains: `github.com`, `gitlab.com`, `bitbucket.org`, `linkedin.com`, `hh.ru`, `habr.com`, `career.habr.com`, `vk.com`, `ok.ru`, `kaggle.com`, `leetcode.com`, `stackoverflow.com`, `medium.com`, `dev.to`, `behance.net`, `dribbble.com`. Add personal domains: `[\w-]+(\.[\w-]+)*\.(ru|рф|com|dev|io|me|org|net|site|pro|tech|app)(/\S*)?` **unless** the token is a known skill (`ASP.NET`, `Node.js`, `Vue.js`, `Next.js`) — check with `normalize_skill()`.
    4. **Phones.** Use span-based replacement (`re.sub` with a function), not `str.replace`. Match the whole number: `\+\d{1,3}` country code + 8–12 more digits with separators, or `8`/`7` + 10 digits; total 10–15 digits. Reject a match where every digit group is a 4-digit year `19xx`/`20xx`.
    5. **Safety net `assert_clean(redacted)`.** After masking, re-run the email/phone/URL/Telegram regexes and search for every value in `found` (case-insensitive). Anything left → return a reason, and the orchestrator does **not** call the LLM (`fallback_reason="pii_residual"`).
    6. **`experience_text`.** `FakeLlm` takes only the "Опыт работы / Experience" section (up to the next section header), drops lines with placeholders, caps at 1500 chars; otherwise `""`. Same cap for `about` (500).
  - **Acceptance.**
    - `tests/ai/fixtures/pii_cases.yaml` with ≥ 30 synthetic cases: every case above, plus RU phone formats (`+7`, `8`, spaces, dashes, brackets, no separators), emails, `t.me`, labelled Telegram, profile URLs, personal domains, names in caps/hyphenated/inflected/inline/in references. Each case lists the expected `found` and asserts that **no original PII substring** is in `Redacted.text`.
    - Negative cases: years, salaries (`250 000`), versions (`Python 3.12`), `ASP.NET`, `Node.js`, `@dataclass` must not be reported as contacts.
    - The 3 hero CVs (AI-5) pass with zero leaks.
    - A test that `assert_clean` blocks the LLM call (the gateway mock is never called) when a name slipped through.

- [ ] **AI-R2 · Fallback is hidden inside `GigaChatLlm`: false `source` and cache poisoning.**
  - **Problem.** `GigaChatLlm.resume/jd/phrase` catch every exception and return `FakeLlm` output. The orchestrator never sees the failure, so `parse_resume` reports `source="llm"` and stores the **rules** result in the cache for 7 days under the LLM key. Reproduced: `provider=gigachat` with no key → `source="llm"`, 1 cache entry. Also every cache hit is forced to `source="llm"`. FE1's "LLM / rules" badge lies, and after an outage the rules answer is served for a week.
  - **Fix.**
    - `GigaChatLlm` methods **raise** `LlmUnavailable` / `LlmSchemaError` with a `.reason`. Delete the internal `FakeLlm` fallbacks.
    - Fallback lives only in `parse_resume`, `parse_jd` and `phrase` (§3, step 4): `source="rules"`, `fallback_reason=<reason>`.
    - Cache only a validated LLM result. Cache value: `{"v": 1, "source": "llm", "prompt": "resume.v1", "model": "...", "draft": {...}}`. On a hit, re-validate the draft with `schema.py`; if it fails, ignore the entry.
    - Cache key: `sha256(f"{kind}|{prompt_version}|{model}|{redacted_text}")`. The prompt version must come from the prompt file name (one constant per prompt, used by both the loader and the key), so renaming `resume.v1.md` → `resume.v2.md` invalidates the cache.
    - `get_gateway()` with `provider="gigachat"` and no `GIGACHAT_AUTH_KEY`: log an error once and return `FakeLlm` (the orchestrator then reports `fallback_reason="no_key"`), instead of a client that fails on every call.
  - **Acceptance.** With a mocked transport:
    - provider raises → `source="rules"`, the correct `fallback_reason`, cache empty;
    - provider succeeds → `source="llm"`, one cache entry; the second call returns `source="llm"` and the transport is **not called again** (assert the call count);
    - a cache entry with invalid enums is ignored;
    - the existing test "second call should hit cache" (which used `FakeLlm` and checked nothing) is replaced by this one.

### Must fix

- [ ] **AI-R3 · LLM output is not validated (AI-4 requirement).**
  - **Problem.** Whatever GigaChat returns goes into `prefill`. Reproduced: `specialization="fullstack"`, `claimed_grade="Senior"`, `work_formats=["удаленка"]`, `salary_type="руб"` all reach the API response. `int("250 000")` raises and silently drops the whole LLM result. There is no repair attempt.
  - **Fix.** New `schema.py`:
    - `validate_resume_payload(d: dict) -> ResumeDraft` and `validate_jd_payload(d: dict) -> JdDraft`, used for LLM output, cache hits **and** `FakeLlm` output.
    - Enums: lower-case, strip, map synonyms (`Senior`/`сеньор`/`ведущий` → `senior`, `удаленка`/`удалённо`/`remote` → `remote`, `на руки` → `net`, `ml`/`data science` → `ml_data`), otherwise `None` (scalars) or drop the element (lists). Deduplicate lists, keep order.
    - Numbers: `years_experience` float in [0, 50]; salaries parsed from int or string (`"250 000"`, `"250k"`, `"250 тыс"`), must be > 0 and ≤ 10 000 000; if `salary_max < salary_min`, swap; if only one bound, keep it.
    - Strings: strip, cap lengths (`title` 200, `city`/`location` 100, each role 100 and ≤ 5 roles, each raw skill 60 and ≤ 60 skills, `about` 500, `experience_text`/`description` 4000, `team_context` 1000). Ignore unknown keys.
    - Raise `LlmSchemaError` only if the payload is not a JSON object or has no usable field at all.
    - **One repair attempt** in `GigaChatLlm`: if `json.loads` fails or the result is not an object, send one more message: the model's previous answer + the parse error + "Верни только исправленный JSON по схеме". If that fails too, raise `LlmSchemaError`.
  - **Acceptance.** Recorded responses in `tests/ai/fixtures/gigachat/`: valid, markdown-fenced, invalid enums (normalised or dropped), string salaries, `salary_max < salary_min`, invalid JSON fixed by the repair call, invalid JSON twice (→ `source="rules"`, `fallback_reason="schema"`).

- [ ] **AI-R4 · Dependencies are missing, so features are silently off.**
  - **Problem.** `rapidfuzz` and `pdfplumber` are not in `requirements.txt`. `normalize.py` and `pdf_text.py` hide this behind `HAS_RAPIDFUZZ`/`HAS_PDFPLUMBER`, so fuzzy matching and the `pdfplumber` fallback never run (`Pyhton`, `Kuberntes` → unknown). `PyYAML` is used directly but only arrives through drf-spectacular.
  - **Fix.** Add `rapidfuzz>=3.9`, `pdfplumber>=0.11`, `PyYAML>=6.0` (and `natasha` if you use it for AI-R1) to `requirements.txt`; ask BE to review that line. Replace the `try/except ImportError` switches with plain imports: a missing dependency must fail at start-up, not silently degrade.
  - **Acceptance.** A clean `pip install -r requirements.txt` + `pytest tests/ai` passes; a test asserts that the `pdfplumber` path is used when `pypdf` returns no text (monkeypatch).

- [ ] **AI-R5 · Fuzzy matching produces wrong skills once `rapidfuzz` is installed.**
  - **Problem.** `fuzz.WRatio` uses partial matching, so short aliases (`go`, `c`) score ≥ 90 against almost anything. Reproduced with rapidfuzz installed: `Djnago → golang`, `R → django`, `Excel → c`, `1C → c`, `Си++ → c`, `Gin → nginx`. Wrong ids go into SkillFit and change match scores. In addition, every lookup scans the whole catalog linearly, and Cyrillic/Latin lookalikes are not handled.
  - **Fix.**
    - Build indexes once in `loader.py`: `by_key: dict[str, str]` for ids, names and aliases (after `_clean_str`). Exact/alias lookups become O(1).
    - Pre-normalise: Unicode NFKC, lower-case, collapse spaces, unify dashes; map Cyrillic lookalikes to Latin in tokens that are mostly Latin (`а е о р с у х к м т н в` → `a e o p c y x k m t h b`); canonical spellings for `c++`/`си++`/`с++`/`cpp`, `c#`/`c sharp`/`си шарп`, `.net`/`dotnet`/`dot net`, `node.js`/`nodejs`/`node js`, `vue.js`, `next.js`, `nuxt.js`. Strip version suffixes (`python 3.12` → `python`, `vue3` → `vue`).
    - Fuzzy step: only for inputs of length ≥ 4, only against keys of length ≥ 4, first letter must match, length ratio within 0.75–1.33. Use OSA (Damerau) distance from `rapidfuzz.distance.OSA`: allowed distance 1 for length 4–9, 2 for length ≥ 10. If the two best candidates map to different ids at the same distance → no match. `score = 1 − distance / max_len`.
    - Add the missing common aliases instead of relying on fuzz (`си++`, `плюсы`, `жс`, `js`, `го`, `голанг`, `постгря`, …).
  - **Acceptance.** `tests/ai/fixtures/skills_messy.yaml` with ≥ 100 inputs → expected id or `null`: typos (`Pyhton`, `Djnago`, `Postgress`, `Kuberntes`, `Javascrpt`), RU spellings, lookalikes (`Руthon` with a Cyrillic `Р`), versions, punctuation, and **negatives** (`R` while there is no `r` skill, `Excel`, `1C`, `Gin`, `Jira`, `Figma`, `Agile`). Target: ≥ 95% correct, **zero false positives** on the negative set. The test prints the accuracy.

- [ ] **AI-R6 · `FakeLlm` heuristics are wrong on common inputs; it invents defaults.**
  - **Problem** (reproduced):
    - JD `опыт от 3 до 5 лет … зарплата от 300 000 до 400 000` → `salary_min=3, salary_max=5`. The range branch has no minimum and matches the experience first.
    - `от 150к до 250к` → nothing (only Latin `k` is handled).
    - `от 300 000 руб gross … Kubernetes, .NET` → `salary_type="net"`: `"net"` is a substring of `kubernetes`, `.net`, `internet`. The fallback is also `net` when no word is found.
    - `Backend developer … немного React` → `frontend` (first keyword wins, frontend is checked first).
    - `Leading projects … под руководством senior … опыт 1 год` → `senior` (substring `lead`, `senior` anywhere).
    - Invented values: grade `middle`, format `remote`, specialization `backend` when nothing is found; `parse_jd` fills `title="Software Engineer"`, `specialization="backend"`, `grades=["middle"]`, `work_formats=["remote"]`, `salary_type="net"` for an empty JD. The resume prompt says "salary_type по умолчанию net", which contradicts the null rule.
  - **Fix.**
    - **Salary:** search only in lines that contain a salary cue (`зарплат`, `з/п`, `зп`, `оклад`, `доход`, `вилка`, `компенсац`, `salary`, `₽`, `руб`, `rub`, `тыс`, `k`/`к` after a number). Support `от X до Y`, `X–Y`, `X - Y`, `X…Y`, single `от X` / `до Y`, suffixes `k`/`к`/`тыс`/`000`. Every amount must be ≥ 10 000 after scaling; ignore anything followed by `лет`/`года`/`год`/`years`.
    - **Salary type:** word-boundary regexes only: net = `\bnet\b`, `на руки`, `чистыми`, `после (вычета|налогов)`; gross = `\bgross\b`, `до (вычета|налогов)`, `грязными`, `с учётом НДФЛ`. Neither → `None`.
    - **Specialization:** score, don't take the first hit. Keywords and matched skill topics each add points; lines in the title/header (first 3 lines, or the "Желаемая должность" line) count ×3. Highest score wins; a tie or zero → `None`.
    - **Grade:** word-boundary regexes, title/header lines only (`\bsenior\b`, `\blead\b`, `тимлид`, `ведущий`, `\bmiddle\b`, `\bjunior\b`, `стаж[её]р`, `\bintern\b`); ignore phrases like `под руководством`. Otherwise derive from years (≥ 5 senior, ≥ 2 middle, ≥ 0.8 junior, else intern); no years → `None`.
    - **Formats:** nothing found → `[]`. **City:** whole-word match.
    - **JD:** `title` = first non-empty line only if it contains a role word; otherwise `None`. No default spec/grades/formats/salary type in `parse_jd`; unknown → `None`/`[]`.
    - Remove "По умолчанию net" from `resume.v1.md` (that is a prompt change: bump to `resume.v2.md`).
  - **Acceptance.** Each reproducer above becomes a regression test with the correct expected value (300 000/400 000; 150 000/250 000; `gross`; `backend`; `junior`; `None`s for an empty JD).

- [ ] **AI-R7 · Resume endpoint: leaked exception text, masked bugs, blocking LLM call.**
  - **Problem.** In `apps/profiles/views.py` (a BE-owned file) the PR wraps everything in `except Exception as e` and returns 422 `unreadable_pdf` with `f"... {e}"` in `detail`. Internal error text reaches the client, and any bug in the gateway looks like a bad PDF. The LLM call runs synchronously inside the HTTP request: with `LLM_PROVIDER=gigachat` the worst case is about 41 s (2 × OAuth + 2 × completion at 10 s, plus sleeps), above gunicorn's default 30 s timeout, and parallel uploads break GigaChat's one-stream limit.
  - **Fix.** Agree with BIKHE (BE owns the view; BE.md N4 adds the Celery `llm` queue). Until N4 lands:
    - only `UnreadablePdf` maps to 422; its `detail` is a fixed Russian string, never `str(e)`;
    - any other exception: log it (type + input hash, no text), then retry inline with `parse_resume(..., gateway=FakeLlm())`; if that also fails, let it propagate (500 problem+json from `core/errors.py`);
    - the view calls `parse_resume(..., gateway=FakeLlm())` inline; the GigaChat path runs only in the Celery task once N4 exists.
  - **Acceptance.** API tests (BE can host them in `tests/`): anonymous 401; non-PDF 422; corrupt PDF 422 with no exception text in the body; a gateway that raises `RuntimeError` still returns 200 with `source="rules"`.

- [ ] **AI-R8 · GigaChat adapter: stale-token retry, no token reuse, timeout budget.**
  - **Problem.**
    - `_chat_completion` builds the `Authorization` header once. After a 401 it clears the token and retries **with the same old header**, so the retry cannot succeed. It also retries 400/403/422, which will never succeed.
    - `get_gateway()` creates a new `GigaChatLlm` on every call, so the cached OAuth token is never reused: every parse makes an extra OAuth request.
    - The worst case is ~41 s, above BE's 15 s wait.
    - If `GIGACHAT_CA_BUNDLE` points to a missing file, the code silently uses the bundled certificate.
  - **Fix.**
    - Rebuild headers on every attempt. On 401: refresh the token once and retry. Retry only timeouts, connection errors, 429 (honour `Retry-After` up to 2 s) and 5xx. Never retry other 4xx.
    - One gateway per process: `get_gateway()` caches instances by `GatewayConfig` (frozen dataclass, hashable) and guards the token refresh with a `threading.Lock`.
    - One deadline per call: `LLM_TIMEOUT_S` (default 10) covers OAuth + completion + retry; each attempt uses `timeout=min(remaining, 8)`; no `sleep` that exceeds the remaining budget. The total stays under BE's 15 s.
    - Configured CA bundle path missing → raise at construction (config error), never fall back quietly. Never disable verification.
    - Send `max_tokens` (e.g. 1500 for extraction, 200 for phrase). Optionally use GigaChat function calling for structured output; the strict-JSON prompt is acceptable if AI-R3 is in place.
  - **Acceptance.** Transport-level tests (patch `urlopen` or use `respx`): 401 → token refresh → success, with the second request carrying the **new** token; 500, 500 → `LlmUnavailable`; 400 → no retry; timeout budget respected (fake clock); two `parse_*` calls → one OAuth request.

- [ ] **AI-R9 · `phrase()` grounding checks numbers only.**
  - **Problem.** AI-7 requires that every number **and named skill** in the output appears in the facts. Reproduced: facts `["Python 4 года"]`, model output `"Кандидат отлично знает Kubernetes и Rust."` is accepted. There is no length limit.
  - **Fix.** Normalise numbers before comparing (`250 000` = `250000`, `4,5` = `4.5`, `%`). Run `extract_skills()` on the output and on the facts; any skill id in the output that is not in the facts → template. Reject output longer than 300 characters or more than 2 sentences, or with `[NAME]`-style placeholders. `GigaChatLlm.phrase` raises on failure (AI-R2); `phrase()` falls back to the template.
  - **Acceptance.** Tests: hallucinated skill → template; hallucinated number → template; reformatted number (`250 000` vs `250000`) → accepted; 3 sentences → template.

- [ ] **AI-R10 · Tests that pass without testing anything; missing fixtures.**
  - **Problem.** `test_parse_jd_orchestration` claims "second call should hit cache", but `FakeLlm` never caches. `test_phrase_grounding_rejects_hallucinated_numbers` never feeds a hallucinated number. `_create_test_pdf` is unused, so `extract_text` is never tested on a PDF that has text. There is no API test for the resume endpoint, no recorded GigaChat responses and no live test.
  - **Fix.** Replace those tests (AI-R2, AI-R9). Add `tests/ai/fixtures/`: 3 synthetic hero CVs as **real PDFs with a text layer** (commit the PDFs and the generator script, e.g. `tools/make_fixture_pdfs.py` with `fpdf2` as a dev-only dependency; Cyrillic needs a bundled TTF such as DejaVu Sans), 1 image-only PDF, 5 JDs as `.txt`, recorded GigaChat responses as `.json`. Register the `live` marker in `pytest.ini` and skip it unless `GIGACHAT_AUTH_KEY` is set.
  - **Acceptance.** `extract_text` returns the expected text for each hero PDF; the image-only PDF raises `UnreadablePdf`; line coverage of `apps/llm_gateway` and `apps/taxonomy` ≥ 85% (`pytest --cov`).

- [ ] **AI-R11 · `prefill` shape does not fit the serializer.**
  - **Problem.** `city`, `about`, `experience_text` are `None` when unknown, but the model fields are `blank=True, default=''` without `null=True`. If FE submits the prefill as is, `CandidateProfileUpdateSerializer` rejects it with "This field may not be null."
  - **Fix.** In the mapping step: string fields → `""` when unknown, list fields → `[]`, numeric fields → `None` (they are nullable). Same rule for `parse_jd` against `PositionSerializer` (check which fields are nullable in `apps/matching/models.py`).
  - **Acceptance.** For each hero CV, `CandidateProfileUpdateSerializer(instance=profile, data=prefill, partial=True).is_valid()` is `True`, except for `salary_*` when the CV has no salary (the form asks for it). Same for 5 JDs with `PositionSerializer`. (These tests need the DB: mark them `django_db`, keep them in `tests/ai/test_serializer_fit.py`.)

- [ ] **AI-R12 · Observability promised in MODELS.md does not exist.**
  - **Problem.** `docs/MODELS.md` says the gateway logs the sha256 of the input, the provider, cache status and latency. The code logs only free-form warnings such as `f"GigaChat resume parsing failed: {e}"`, and §6 requires the fallback reason.
  - **Fix.** `log_llm_call(kind, provider, model, prompt_version, input_sha12, latency_ms, cache_hit, source, fallback_reason)` writes one structured line (`logger.info("llm_call", extra={...})`) per `parse_*`/`phrase` call. No text, no exception messages that may contain model output (log `type(e).__name__` only). Update MODELS.md to describe exactly what is logged.
  - **Acceptance.** A `caplog` test parses a hero CV and asserts that one `llm_call` record has all fields and that no line of the CV text and no PII value appears in any log record.

- [ ] **AI-R13 · `blueprint_for` errors are swallowed; wrong import path.**
  - **Problem.** `parse_jd` imports `apps.assessment.engine.blueprint` (wrong root, see §2) inside `except (ImportError, Exception)`, so any bug in ML's function is silently turned into `[]`. It also passes `specialization=None` when it is unknown.
  - **Fix.** `from assessment.engine.blueprint import blueprint_for` guarded by `except ModuleNotFoundError` only. Call it only when the specialization is known. Other exceptions: log an error with the exception type, return `[]`, and add `"blueprint"` to the log line. Convert ML's `list[tuple[str, float]]` to `[{"topic", "weight"}]` (ML.md §3).
  - **Acceptance.** Tests with a monkeypatched `blueprint_for`: returns tuples → converted; raises `ValueError` → `[]` and an error log; module missing → `[]` and no error log.

### Cleanup

- [ ] **AI-R14 · Hygiene.**
  - Fix all 21 `ruff` errors (unused imports and variables such as `must_keywords`, `full_match`, unsorted imports). `python .claude/skills/verify/scripts/verify.py` must pass.
  - Imports per §2: `from taxonomy import …` inside `llm_gateway`, tests import `llm_gateway`/`taxonomy` (not `apps.…`).
  - Remove `load_dotenv()` from `get_gateway()`: `config/settings.py` already loads `.env`; a library must not mutate the environment.
  - Revert unrelated changes: `.gitignore` (`.git_bin/`) and the `conftest.py` import move, unless BE asks for them.
  - Commit messages must state facts: the PR said "100+ skills", the file has 70.
  - Process: one commit per AI-R item, PRs under ~400 lines titled with task IDs. After the rework, split further work into separate PRs (AI-1 v1, AI-5 fixtures, AI-7, AI-8, …).

---

## 5. Task Checklist (full scope; what is left after the rework)

IDs in parentheses refer to `docs/TASKS.md`. A box is ticked when the work is merged into `main`.

### P0

- [ ] **AI-0 · Publish the contract with stubs** (F-07, MK5). *~90%.*
  - **Left:** §3 additions (`fallback_reason`, `LlmError` hierarchy), import rules (AI-R14), fallback only in the orchestrator (AI-R2).
  - *Done:* BE can wire both endpoints, and `pytest tests/ai` is green with no network.

- [ ] **AI-1 · Skill taxonomy v0 → v1** (AI-01, skills part). *~45%.*
  - **Left:**
    - AI-R4 and AI-R5 (dependencies, safe fuzzy matching, indexes, lookalikes).
    - **v0 → 100 skills now, v1 → ~300.** Cover all three specializations evenly. Missing today (examples): Swift, Jira, Figma, Airflow, Grafana, Prometheus, Hadoop, Spark, Tableau, Svelte, Unity, Kafka Streams, dbt, MLflow, Optuna, LightGBM/XGBoost/CatBoost, OpenCV, HuggingFace, LangChain, Playwright, Cypress, Webpack/Vite, Storybook, Tailwind, Sass, Jest/Vitest, Selenium, Linux, Bash, Git, CI/CD, GitLab CI, GitHub Actions, Nginx, RabbitMQ, ClickHouse variants, Elasticsearch, gRPC, REST, OAuth, microservices, DDD, design patterns, data structures.
    - Each entry: `{id, name, aliases[], topic, related[]}`; aliases cover RU/EN spellings, abbreviations and typos ("Postgress", "постгрес", "k8s", "реакт", "TS", "py").
    - `related` ids must exist; add a test for that and for alias uniqueness (one alias → one id).
    - **Topics:** agree topic ids with ML. ML's `content/specializations.yaml` does not exist yet (ML-2), so send ML your current topic list (`backend.python`, `frontend.react`, `ml.nlp`, …) and adopt theirs when it lands. Add a CI test that every `topic` in `skills.yaml` exists in `specializations.yaml` (skip while the file is missing).
    - Review questionable aliases: `DRF` is a separate skill (`drf`, related to `django`), not an alias of `django`.
  - *Done:* ≥ 95% correct ids and zero false positives on the committed `skills_messy.yaml` (≥ 100 inputs); ~300 skills.

- [ ] **AI-2 · PDF text and redaction.** *~55%.*
  - **Left:** AI-R1 (redaction), AI-R4 (`pdfplumber`), AI-R10 (real PDF fixtures).
  - `extract_text`: `pypdf`, then `pdfplumber`. Scanned or empty PDFs raise `UnreadablePdf`. Also raise on encrypted PDFs that can't be opened with an empty password, and cap the work: at most 20 pages and 200 000 characters (BE already limits the upload to 5 MB). OCR is out of scope; the UI falls back to the manual form.
  - *Done:* unit tests on synthetic CVs show zero PII in `Redacted.text`, and `found` contains everything (`pii_cases.yaml`).

- [ ] **AI-3 · `FakeLlm` rules** (MK5, the permanent fallback). *~65%.*
  - **Left:** AI-R6. Years from date ranges must merge overlapping periods (two parallel jobs 2020–2023 are 3 years, not 6) and understand `мм.гггг`, `янв 2020 — н.в.`, `по настоящее время`.
  - *Done:* sensible drafts on the 3 CVs and 5 JDs with no network; every AI-R6 reproducer is a passing regression test.

- [ ] **AI-4 · GigaChat adapter** (AI-06). *~55%.*
  - **Left:** AI-R2, AI-R3, AI-R8.
  - **Live check:** get the key now (since 1 Sep 2026 new clients buy packages through cloud.ru). Verify the endpoints, auth flow and model names against developers.sber.ru. Run the live smoke test (`pytest -m live tests/ai`) with a real key and paste the output (no CV text) into the PR. Record the real responses (redacted inputs only) into `tests/ai/fixtures/gigachat/`.
  - Concurrency: the free tier serves one stream at a time; BE runs the `llm` queue with concurrency 1, so don't parallelise inside the adapter.
  - *Done:* `LLM_PROVIDER=gigachat` parses a JD end to end; with the network off, the rules take over transparently and the result says `source="rules"`.

- [ ] **AI-5 · Resume and JD parsing** (AI-07). *~45%.*
  - **Left:** AI-R2, AI-R3, AI-R10, AI-R11, AI-R13.
  - **Fixtures:** 3 synthetic hero CVs (Russian, PDF) matching the demo personas (one per specialization: backend middle, frontend junior, ML senior) and 5 JDs (including one with must/nice sections, one with `опыт от 3 до 5 лет`, one in English, one with no salary, one with gross).
  - **Manual checklist** in `tests/ai/fixtures/README.md`: for each fixture, the expected spec, grade, skills, salary and type, formats, and the actual output from both rules and GigaChat. Fill it from real runs.
  - *Done:* the checklist passes; `unknown_terms` is populated for non-taxonomy skills; "Postgress" and "k8s" map correctly; `source` is truthful.

- [ ] **AI-6 · Model usage register** (`docs/MODELS.md`). *~85%.*
  - **Left:** make the logging section match the code (AI-R12); add the prompt version per use case as it changes (`resume.v2.md` after AI-R6); add the `natasha` entry if you use it (local, rules-based NER, sees raw text locally only); keep the USER-bge-m3 row in sync with ML-9; state again that grading and ranking use no model.
  - The env vars (`LLM_PROVIDER`, `GIGACHAT_AUTH_KEY`, `GIGACHAT_SCOPE`, `GIGACHAT_MODEL`, `GIGACHAT_CA_BUNDLE`, `LLM_TIMEOUT_S`) are documented; BE adds them to `config/settings.py` and `.env.example` (BE.md §2.2).

### P1

- [ ] **AI-7 · Grounded "why" sentence** (AI-12, LLM part). *~40%.*
  - `phrase(facts)` turns the scorer's reason chips into one or two Russian sentences. The prompt contains facts only.
  - **Left:** AI-R9 (skill grounding, number normalisation, length limit). Define the input with ML: facts come from `Scored.reasons` (ML.md §3); agree on the text format of a fact (e.g. `"Python: подтверждено тестом"`, `"Зарплатные ожидания в вилке"`). Cache phrases by `sha256(prompt_version + facts)`.
  - BE stores the sentence with the offer, and FE shows it under "why you".
  - *Done:* 20 recorded fact sets → every output passes grounding or falls back to the template; tests for each rejection rule.

- [ ] **AI-8 · AI-DRAFT: LLM-assisted family drafting** (offline, `tools/draft_families/`). *0%.*
  - **How:**
    - CLI: `python -m tools.draft_families.draft --spec backend --topic backend.sql --n 5 --model GigaChat-2-Max`.
    - Input: a topic spec (topic id, skills, target grade band, item format from ML.md §3 `ItemFormat`).
    - Prompt (`tools/draft_families/prompts/family.v1.md`) includes the `ItemFamily` protocol and `FamilyMeta` from ML.md §3, one good existing family as an example, and the rules: the key must depend on drawn parameters; `oracle()` must recompute the answer independently of `generate()`; exactly one correct option; `view()` never exposes the key; no global `random`, only the passed `rng`.
    - Output: `tools/draft_families/out/<family_id>/` with `family.py` (generator + oracle skeleton), `meta.yaml` (suggested `a`, `b`, `c`, `time_limit_s`, `skills` as taxonomy ids), `prompt.md` and `response.json` (provenance).
    - Pre-check before handing to ML: the file parses, imports nothing outside the stdlib, and runs ML's harness `python -m assessment.families.verify` on it (once ML-1 ships). Only drafts that pass go to ML.
  - **Rules:** nothing in `apps/` imports `tools/` (add a test); no personal data in prompts; `tools/draft_families/out/` is committed only for drafts ML accepted.
  - *Done:* ML accepts at least 10 drafted families toward the ≥ 15 per spec target.

- [ ] **AI-9 · Concept-MCQ pools** (PD-06). *0%.*
  - Agree the data format with ML first (the `concept_mcq` family consumes it). Proposal: `content/concept_mcq/<topic>.yaml`, one entry per concept: `id`, `topic`, `skills`, `stems` (≥ 3 paraphrases), `correct` (≥ 2 paraphrases), `distractors` (≥ 6, each plausible and unambiguously wrong), `grade_band`, `source` (`llm-draft`), `reviewed_by` (two names), `review_notes`.
  - Draft with GigaChat-2-Pro/Max offline, then **two people review** every entry; an entry without two reviewers is not loaded (ML's loader checks it).
  - *Done:* ≥ 20 concept families reviewed and passing ML's verify harness.

- [ ] **AI-10 · Embedding-based alias resolution** (optional). *0%.*
  - Once ML ships the USER-bge-m3 embedding helper (ML-9), add `method="embedding"` as the last fallback in `normalize_skill()`: embed skill names + aliases once (cached on disk by taxonomy hash), cosine similarity ≥ 0.85 (tune on `skills_messy.yaml`), and the same "no ambiguous winner" rule as AI-R5.
  - *Done:* accuracy on `skills_messy.yaml` improves and the negative set still has zero false positives.

---

## 6. Interfaces With Other Streams

| With | You give | You need |
|---|---|---|
| **BE** | The §3 contract; `content/skills.yaml`; the env var list; `UnreadablePdf`; the dependency lines for `requirements.txt` (AI-R4) | Endpoints `/candidates/me/resume` and `/positions/parse`; the Celery `llm` queue (concurrency 1) with the 15 s wait and inline rules fallback (N4); the view fix in AI-R7; `sync_taxonomy`; settings and Redis cache; calls to `normalize_many()` on profile and position save |
| **ML** | Skill ids for `FamilyMeta.skills`; your topic list; drafted families and MCQ pools for review | `blueprint_for(spec, skill_ids)`; topic ids in `content/specializations.yaml`; the verify harness (ML-1); the fact format for `phrase()`; the embedding helper (P1) |
| **FE1** | Semantics of `prefill`, `unknown_terms`, `source` (the onboarding resume step highlights unknown terms and shows an "LLM" vs "rules" badge) | — |
| **FE2** | Semantics of `JdParseResult` (editable must/nice chips, blueprint bars; `None` fields stay empty in the form) | — |

## 7. Working Agreements

- CI never calls the network. `LLM_PROVIDER=fake` is the default everywhere except staging.
- Prompts are files with a version in the name. Changing a prompt bumps the version, which invalidates the cache.
- Log the provider, latency, cache hit and fallback reason. Never log the text.
- Run `python .claude/skills/verify/scripts/verify.py` before every push; it must pass (ruff included).
- Small PRs titled with the task ID (`AI-4 GigaChat adapter`, `AI-R1 Redaction`). Model or endpoint changes go into BE.md §2 as requests. Don't edit BE-owned files (views, serializers, settings, migrations) without agreeing with BIKHE in the PR description.
