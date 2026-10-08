# AI.md: LLM API & Language Tasks (owner: AI / LLM engineer)

> **Audience:** the AI/LLM engineer and their AI coding agent.
> **Scope:** the LLM gateway (GigaChat + rule-based fake), PDF text extraction, PII redaction, resume and job-description parsing, the skill taxonomy and `normalize_skill()`, grounded "why" sentences, and offline LLM-assisted drafting of item content.
> **Date:** 2026-10-08. Related files: [BE.md](BE.md) (endpoints and Celery wiring), [ML.md](ML.md) (grading, matching, blueprints), [FE1.md](FE1.md), [FE2.md](FE2.md).

---

## 0. Ownership Rules

| You own | You do **not** own |
|---|---|
| `apps/llm_gateway/`: gateway protocol, `FakeLlm`, `GigaChatLlm`, `redact`, `extract_text`, `parse_resume`, `parse_jd`, `phrase` | Endpoints, upload limits, Celery tasks and queues, persistence (BE) |
| `apps/taxonomy/` + `content/skills.yaml`: skill ids, aliases, topics, related skills, `normalize_skill()` | Syncing `skills.yaml` into the `Skill` table (`manage.py sync_taxonomy`, BE) |
| Prompts (versioned files), response schemas, caching keys, fallbacks | Grading and scoring math (ML). **An LLM never touches a grade** |
| `tools/draft_families/`: offline LLM drafting of item families and concept-MCQ pools for ML to review | Final item families, IRT parameters, verify harness (ML) |
| The model usage register doc (QA requires every model and use case to be documented) | UI (FE1, FE2) |

**Hard invariants:**
1. **No LLM in grading or ranking.** Your output only pre-fills forms, extracts skills and rephrases facts that the scorer already computed.
2. **152-FZ: redact PII before every LLM call.** Names, emails, phones, Telegram handles and profile URLs are extracted **locally** and never sent. Use only domestic LLMs (GigaChat; a YandexGPT adapter is optional). No cross-border personal data.
3. **Everything degrades gracefully.** Any exception, timeout or invalid JSON falls back to `FakeLlm` (rules). The product must work with `LLM_PROVIDER=fake` and no network, and CI always runs that way.
4. **Determinism where it matters.** The same input with the same prompt version gives a cached output. Use temperature ≤ 0.2 for extraction.
5. **No PII in logs, test fixtures or the repo.** Use synthetic CVs only, and log input hashes instead of texts.

---

## 1. Current State (audit of merge `3cf4044`)

- **AI-F1 🔴 Resume parsing is fake.** `POST /api/candidates/me/resume` (`apps/profiles/views.py:133-167`) always returns `skills: ['Python','Django','PostgreSQL','Docker']`. It guesses the specialization from the substring "python", and on any exception it substitutes hardcoded text. `unknown_terms` is always `[]`. BE is fixing the endpoint (limits, Celery); you replace the logic.
- **AI-F2 🔴 There is no JD parsing.** `POST /api/positions/parse` doesn't exist yet. BE adds it, and you provide `parse_jd()`.
- **AI-F3 🟠 There is no taxonomy.** There's no `content/skills.yaml`. The seed creates 10 skills with ids `python, django, fastapi, postgresql, docker, react, typescript, sql, algorithms, pytorch` (keep these ids). The profile update turns free text into new `Skill` rows by lower-casing (`profiles/serializers.py:179-181`; `"C++"` → `c++`), which pollutes the taxonomy. BE stops that and calls your `normalize_skill()`.
- **AI-F4 🟡 There is no gateway.** `config/settings.py` has `LLM_PROVIDER = 'fake'` and nothing reads it. There's no `GIGACHAT_*` config. `pypdf` is installed; `pdfplumber`, `rapidfuzz` and a GigaChat client are not.

---

## 2. Target Layout

```text
apps/llm_gateway/                 # named llm_gateway (not llm) to avoid clashing with the PyPI "llm" package
  __init__.py     get_gateway(), parse_resume(), parse_jd(), phrase()
  types.py        ResumeDraft, JdDraft, ResumeParseResult, JdParseResult, Redacted
  base.py         LlmGateway protocol, Cache protocol, GatewayConfig
  fake.py         FakeLlm: regex + taxonomy rules (fallback, CI default)
  gigachat.py     GigaChatLlm: token cache, JSON output, timeout, retry
  redact.py       redact(): local PII extraction and masking
  pdf_text.py     extract_text(): pypdf, then pdfplumber fallback; raises UnreadablePdf
  resume.py       parse_resume() orchestration
  jd.py           parse_jd() orchestration
  phrase.py       phrase() with template fallback and a number-grounding check (P1)
  prompts/        resume.v1.md  jd.v1.md  phrase.v1.md   (versioned; the version is part of the cache key)
apps/taxonomy/
  loader.py       load_skills(path="content/skills.yaml")
  normalize.py    normalize_skill(), normalize_many(), extract_skills()
content/skills.yaml
tools/draft_families/             # offline only; never imported by the app
tests/ai/                         # no network; recorded GigaChat responses; synthetic CVs/JDs in fixtures/
docs/MODELS.md                    # model usage register
```

**Purity:** keep these packages free of the ORM and of views. Read configuration through `GatewayConfig`; BE builds it from Django settings and passes it, or `get_gateway()` builds it lazily from `django.conf.settings`. Caching goes through a `Cache` protocol (`get(key)`, `set(key, value, ttl)`), and BE passes Django's Redis cache. Keep imports relative inside your packages; BE may later switch to `apps.<name>` imports (BE.md A9).

**Dependencies (add in your PRs; BE reviews):** `pdfplumber`, `rapidfuzz`, and either the official `gigachat` SDK or `httpx` (+ `respx` for tests). `natasha` is optional, for Russian name detection in redaction.

---

## 3. The Contract (you publish it; BE wires it)

**Publish this first, as stubs backed by `FakeLlm`.** BE builds the endpoints against it, and FE mocks the shapes. Enum values must match `core.enums`: specializations `backend|frontend|ml_data`, grades `intern|junior|middle|senior`, formats `office|hybrid|remote`, salary `gross|net`. Output keys must match the **flat** Django serializer fields (`salary_min`, `salary_max`, `salary_type`; see BE.md §2.3).

```python
# ── apps/llm_gateway/types.py ──
from dataclasses import dataclass, field
from typing import Literal, Protocol

Source = Literal["llm", "rules"]

@dataclass(frozen=True)
class Redacted:
    text: str                              # PII replaced with placeholders: [EMAIL], [PHONE], [NAME], [URL], [TG]
    found: dict[str, list[str]]            # {"email": [...], "phone": [...], "telegram": [...], "url": [...], "name": [...]}

@dataclass(frozen=True)
class ResumeDraft:                         # what the LLM (or rules) extracts from REDACTED text
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
    contacts: dict                         # {"full_name", "email", "phone", "telegram"} from local redaction only;
                                           # BE stores them only after the candidate confirms the form
    unknown_terms: list[str]               # raw skills that normalize_skill() could not map
    source: Source

@dataclass(frozen=True)
class JdDraft:
    title: str | None; specialization: str | None; grades: list[str]
    must_skills_raw: list[str]; nice_skills_raw: list[str]
    work_formats: list[str]; location: str | None
    salary_min: int | None; salary_max: int | None; salary_type: str | None
    team_context: str | None; description: str | None

@dataclass(frozen=True)
class JdParseResult:
    draft: dict                            # keys = PositionSerializer writable fields; skills as ids
    unknown_terms: list[str]
    blueprint: list[dict]                  # [{"topic": str, "weight": float}] from ML's blueprint_for(); [] until available
    source: Source

class UnreadablePdf(Exception): ...        # BE maps it to 422 `unreadable_pdf`

# ── apps/llm_gateway/base.py ──
class LlmGateway(Protocol):
    name: str                                         # "fake" | "gigachat"
    def resume(self, redacted_text: str) -> ResumeDraft: ...
    def jd(self, text: str) -> JdDraft: ...           # JDs are company text; still run redact() for contact details
    def phrase(self, facts: list[str]) -> str: ...    # P1

class Cache(Protocol):
    def get(self, key: str): ...
    def set(self, key: str, value, ttl: int): ...

# ── apps/llm_gateway/__init__.py ──  (sync functions; BE calls them inside Celery tasks)
def get_gateway(config: "GatewayConfig | None" = None) -> LlmGateway: ...
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

def normalize_skill(raw: str) -> SkillMatch | None: ...     # exact id/name → alias → rapidfuzz ≥ 90
def normalize_many(raws: list[str]) -> tuple[list[SkillMatch], list[str]]: ...   # (matches, unknown_terms)
def extract_skills(text: str) -> tuple[list[SkillMatch], list[str]]: ...         # used by the rules fallback
```

**Orchestration inside `parse_resume`:**
1. `extract_text` (raises `UnreadablePdf` for scanned or image-only PDFs).
2. `redact`.
3. Check the cache, keyed by `sha256(prompt_version + redacted_text)`.
4. `gateway.resume()`. On **any** exception or schema violation, fall back to `FakeLlm` and set `source="rules"`.
5. `normalize_many(skills_raw)`.
6. Map the draft onto serializer keys and fill `contacts` from `Redacted.found`.

`parse_jd` follows the same steps, then calls ML's `blueprint_for(spec, skill_ids)` (wrap the import in `try/except ImportError` until ML ships it).

**How BE uses it:**
- `POST /candidates/me/resume`: BE validates ≤ 5 MB and PDF MIME, runs a Celery task `llm.parse_resume` on queue `llm` (worker `--concurrency=1`), and waits ≤ 15 s. On timeout it calls `parse_resume(..., gateway=FakeLlm())` inline.
- `POST /positions/parse`: same pattern.
- Profile and position saves: BE calls `normalize_many()`.
- Offer creation (P1): BE calls `phrase()`.

---

## 4. Task Checklist

IDs in parentheses refer to `docs/TASKS.md`.

### P0: in this order

- [ ] **AI-0 · Publish the contract with stubs** (F-07, MK5). Create the packages from §2 with the §3 types. `FakeLlm` can start trivial, as long as the shapes are final. *Done:* BE can wire both endpoints, and `pytest tests/ai` is green with no network.
- [ ] **AI-1 · Skill taxonomy v0 → v1** (AI-01, skills part).
  - **File:** `content/skills.yaml` with entries `{id, name, aliases[], topic, related[]}`. Aliases cover RU/EN spellings, abbreviations and common typos ("Postgress", "постгрес", "k8s", "реакт", "TS", "py").
  - **Size:** v0 with ~100 skills as soon as possible; v1 with ~300.
  - **Ids:** keep the 10 seed ids from AI-F3.
  - **Topics:** agree topic ids with ML's `content/specializations.yaml`.
  - **`normalize_skill()`:** exact match, then alias, then rapidfuzz `WRatio ≥ 90`. Handle case, Cyrillic/Latin lookalikes and punctuation (`C++`, `C#`, `.NET`, `Node.js`).
  - *Done:* ≥ 95% correct ids on a committed set of 100 messy inputs.
- [ ] **AI-2 · PDF text and redaction.**
  - **`extract_text`:** `pypdf`, with a `pdfplumber` fallback. Scanned or empty PDFs raise `UnreadablePdf`. OCR is out of scope; the UI falls back to the manual form.
  - **`redact`:** emails; phones in RU formats (`+7`, `8`, spaced, dashed, bracketed); Telegram `@handles` and `t.me` links; URLs (GitHub, LinkedIn, hh.ru); and names (a header-line heuristic, plus `natasha` NER if added).
  - *Done:* unit tests on synthetic CVs show zero PII in `Redacted.text`, and `found` contains everything.
- [ ] **AI-3 · `FakeLlm` rules** (MK5, the permanent fallback).
  - **Resume:** keyword and regex extraction with `extract_skills`. Infer the specialization from skill topics, years from date ranges, the grade from years and title words, and the salary from currency patterns ("от 250 000 ₽", "250k", "на руки" means net, "gross/до вычета" means gross), plus formats and city.
  - **JD:** the same, plus must/nice split heuristics ("обязательно", "будет плюсом").
  - *Done:* sensible drafts on the fixture set with no network.
- [ ] **AI-4 · GigaChat adapter** (AI-06).
  - **Auth:** OAuth token with `GIGACHAT_AUTH_KEY` and scope `GIGACHAT_API_PERS`, cached and refreshed before its ~30-minute expiry.
  - **Calls:** chat completions with `GIGACHAT_MODEL` (default `GigaChat-2`).
  - **Output:** structured JSON via function calling or a strict JSON prompt. Validate against the draft schema, allow one repair attempt, then fall back.
  - **Limits:** 10 s timeout and 1 retry; the cache TTL is 7 days.
  - **TLS:** install the Russian Trusted Root CA (НУЦ Минцифры) bundle via `GIGACHAT_CA_BUNDLE`; **never disable TLS verification**.
  - **Concurrency:** the free tier serves **one stream at a time**. BE runs the `llm` queue with concurrency 1, so don't parallelize inside the adapter.
  - Verify the endpoint URLs, auth flow and model names against the current docs at developers.sber.ru before coding (the official `gigachat` Python SDK wraps most of this). Since 1 Sep 2026, new clients buy packages through cloud.ru, so **get the key early**.
  - *Done:* `LLM_PROVIDER=gigachat` parses a JD end to end; with the network off, the rules take over transparently.
- [ ] **AI-5 · Resume and JD parsing** (AI-07).
  - Implement the orchestration from §3 and map onto the real Django serializer fields (`CandidateProfileUpdateSerializer`, `PositionSerializer` in `apps/profiles/serializers.py` and `apps/matching/serializers.py`).
  - Write versioned prompts in Russian that ask for JSON only, include an explicit "unknown → null" rule, and contain no PII.
  - **Fixtures:** 3 synthetic hero CVs (Russian, PDF) and 5 JDs in `tests/ai/fixtures/`. Use recorded GigaChat responses for provider tests, and add an optional live smoke test under `@pytest.mark.live`, skipped by default.
  - *Done:* the fixtures pass a manual checklist (spec, grade, skills, salary and type, formats); `unknown_terms` is populated for non-taxonomy skills; and the "Postgress" and "k8s" cases map correctly.
- [ ] **AI-6 · Model usage register** (`docs/MODELS.md`). For every model (GigaChat-2 runtime; GigaChat-2-Pro/Max offline drafting; USER-bge-m3, with an entry provided by ML): use case, where it runs, what data it sees (redacted only), fallback, prompt version, and the fact that **grading uses no model**. Also document the env vars (`LLM_PROVIDER`, `GIGACHAT_AUTH_KEY`, `GIGACHAT_SCOPE`, `GIGACHAT_MODEL`, `GIGACHAT_CA_BUNDLE`, `LLM_TIMEOUT_S`) so BE can add them to settings and `.env.example`.

### P1

- [ ] **AI-7 · Grounded "why" sentence** (AI-12, LLM part).
  - `phrase(facts)` turns the scorer's reason chips into one or two Russian sentences.
  - The prompt contains facts only.
  - **Grounding check:** every number and named skill in the output must appear in `facts`; otherwise use the template fallback.
  - BE stores the sentence with the offer, and FE shows it under "why you".
- [ ] **AI-8 · AI-DRAFT: LLM-assisted family drafting** (offline, `tools/draft_families/`).
  - From a topic spec, generate *candidate* family modules: a parametric generator skeleton, an oracle skeleton and YAML meta with a suggested `b`. Use GigaChat-2-Pro/Max.
  - Write output to `tools/draft_families/out/` for **ML review**. Nothing is imported at runtime, and ML's verify harness gates everything.
  - No personal data in prompts.
  - *Done:* ML accepts at least 10 drafted families toward the ≥15 per spec target.
- [ ] **AI-9 · Concept-MCQ pools** (PD-06). Draft paraphrase and distractor pools with an LLM. Two people review them. Deliver them as data files that ML's `concept_mcq` families consume. *Done:* ≥ 20 concept families reviewed.
- [ ] **AI-10 · Embedding-based alias resolution** (optional). Once ML ships the USER-bge-m3 embedding helper (ML-9), add `method="embedding"` as the last fallback in `normalize_skill()`, behind a threshold.

---

## 5. Interfaces With Other Streams

| With | You give | You need |
|---|---|---|
| **BE** | The §3 contract (stub first); `content/skills.yaml`; the env var list; `UnreadablePdf` | Endpoints `/candidates/me/resume` and `/positions/parse`; the Celery `llm` queue (concurrency 1) with the 15 s wait and inline rules fallback; `sync_taxonomy`; settings and Redis cache; calls to `normalize_many()` on profile and position save |
| **ML** | Skill ids for `FamilyMeta.skills`; drafted families and MCQ pools for review | `blueprint_for(spec, skill_ids)`; topic ids in `content/specializations.yaml`; the embedding helper (P1) |
| **FE1** | Semantics of `prefill`, `unknown_terms` and `source` (the onboarding resume step highlights unknown terms and shows an "LLM" vs "rules" badge) | — |
| **FE2** | Semantics of `JdParseResult` (editable must/nice chips, blueprint bars) | — |

## 6. Working Agreements

- CI never calls the network. `LLM_PROVIDER=fake` is the default everywhere except staging.
- Prompts are files with a version in the name. Changing a prompt bumps the version, which invalidates the cache.
- Log the provider, latency, cache hit and fallback reason. Never log the text.
- Small PRs titled with the task ID (`AI-4 GigaChat adapter`). Model or endpoint changes go into BE.md §2 as requests.
