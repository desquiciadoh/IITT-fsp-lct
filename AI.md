# AI.md: LLM API & Language Tasks (owner: AI / LLM engineer)

> **Audience:** the AI/LLM engineer and their AI coding agent.
> **Scope:** the LLM gateway (GigaChat + rule-based fake), PDF text extraction, PII redaction, resume and job-description parsing, the skill taxonomy and `normalize_skill()`, grounded "why" sentences, and offline LLM-assisted drafting of item content.
> **Updated:** 2026-10-10, after the re-review of PR #7 (`feat/ai-llm-gateway-fixes`). Related files: [BE.md](BE.md) (endpoints and Celery wiring), [ML.md](ML.md) (grading, matching, blueprints), [FE1.md](FE1.md), [FE2.md](FE2.md), [docs/MODELS.md](docs/MODELS.md).
> **Start here:** §1 says what is done. **Your next job is §4, testing** (live GigaChat run, recorded answers, manual checklist, red-team). §5 lists the development that is left; none of it blocks the LLM API integration.

---

## 0. Ownership Rules

| You own | You do **not** own |
|---|---|
| `apps/llm_gateway/`: gateway protocol, `FakeLlm`, `GigaChatLlm`, `redact`, `extract_text`, `parse_resume`, `parse_jd`, `phrase` | Endpoints, upload limits, Celery tasks and queues, persistence (BE) |
| `apps/taxonomy/` + `content/skills.yaml`: skill ids, aliases, topics, related skills, `normalize_skill()` | Syncing `skills.yaml` into the `Skill` table (`manage.py sync_taxonomy`, BE) |
| Prompts (versioned files), response schemas, caching keys, fallbacks | Grading and scoring math (ML). **An LLM never touches a grade** |
| `tools/draft_families/`: offline LLM drafting of item families and concept-MCQ pools for ML to review | Final item families, IRT parameters, verify harness (ML) |
| The model usage register `docs/MODELS.md` | UI (FE1, FE2) |

**Hard invariants:**
1. **No LLM in grading or ranking.** Your output only pre-fills forms, extracts skills and rephrases facts that the scorer already computed.
2. **152-FZ: redact PII before every LLM call.** Names, emails, phones, Telegram handles and profile URLs are extracted **locally** and never sent. Domestic LLMs only (GigaChat). **If you are not sure the text is clean, don't send it**: `assert_clean()` fails → rules, `fallback_reason="pii_residual"`.
3. **Everything degrades gracefully, and visibly.** Any exception, timeout or invalid JSON falls back to `FakeLlm` **in the orchestrator** (`pipeline.run`), which reports `source="rules"` and a `fallback_reason`. CI always runs with `LLM_PROVIDER=fake` and no network.
4. **Determinism where it matters.** Same input + same prompt version + same model → cached output. Temperature ≤ 0.2 for extraction.
5. **No PII in logs, test fixtures or the repo.** Synthetic CVs only; logs carry `input_sha12`, never text or exception messages.
6. **Unknown means empty.** Never invent a title, specialization, grade, format or salary type: strings `""`, lists `[]`, numbers `None`.

---

## 1. Status (2026-10-10): the LLM API integration is done

**Verdict: PR #7 is ready to merge.** The AI engineer's commit `8fe870d` closed the PR #6 review on paper, but probe scripts reproduced a PII leak to GigaChat and a dozen must-fix bugs that the tests did not catch. The reviewer fixed everything on the same branch, one commit per AI-R item, and then ran a red-team pass on redaction (about 120 adversarial inputs).

**Numbers at branch head:** `tests/ai` 249 passed + 1 live test skipped without a key; 5 API tests in `tests/test_resume_parse_api.py`; full suite green on PostgreSQL; coverage of `apps/llm_gateway` + `apps/taxonomy` 94%; `verify.py --full` READY (2 WARNs outside AI, see §4.6). `pii_cases.yaml` 87 cases, `skills_messy.yaml` 160 cases at 100% with 0 false positives, 105 skills.

### What was done and how

| Item | What | How |
|---|---|---|
| **AI-R1 Redaction** (blocker) | PII no longer reaches the LLM | `redact.py` rewritten: span-based replacement (never `str.replace`), Unicode normalisation (zero-width, NBSP, dash variants, full-width digits, ligatures), obfuscated and wrapped emails (`[at]`, `собака`, line breaks), structural phone patterns with filters for years, `мм.гггг`, money and IPv4, labelled Telegram/profile handles, bare `@handle` only in the contact block, code annotations and npm scopes kept. Names: header scoring with a first-name/patronymic lexicon (`pii_lexicon.py`), `ФИО:`/`Фамилия:`/`Имя:`/`Отчество:` labels, `Меня зовут …`, referees and recruiters, initials (`Петров А.В.`, `Petrov A.`). `assert_clean()` re-checks with broader patterns and searches for every found value; if anything is left, the LLM is skipped and `about`/`experience_text` are not pre-filled. |
| **AI-R2 Fallback** | One fallback path, truthful reasons | `pipeline.run()` is the only place that falls back: `provider_fake`, `provider_unknown`, `no_key`, `pii_residual`, `timeout`, `http_error`, `schema`, `error`. Only validated LLM answers are cached, re-validated on read. `get_gateway()` reads settings then env, normalises the provider name, logs a bad `LLM_TIMEOUT_S` once. |
| **AI-R3 Schema** | Model output is always schema-valid | `schema.py`: enum synonyms, salary strings (`"250к"`, `"200-250 тыс"`, no `"на руки"` → ×1000 bug), inverted ranges, JSON in fences or prose (`extract_json_object`). |
| **AI-R4 PDF** | Real PDFs, logged failures | `pypdf` page by page (a broken page keeps the others), then `pdfplumber`; scanned and encrypted PDFs raise `UnreadablePdf`; failures logged as type + sha only. |
| **AI-R5 Taxonomy** | Unambiguous keys | Each alias maps to one id (test over names, ids and aliases); short keys are case-sensitive in free text (`C#` is not C, `ready to go` is not Go, `TF-IDF` is not TensorFlow); `MS SQL` → `mssql`. |
| **AI-R6 / AI-3 FakeLlm** | Sensible rules, no inventions | Salary only on lines with a money cue, linear regexes (no ReDoS, no `OverflowError`); roles never invented; `about`/`experience` from their sections; years from `опыт N лет`, `N лет M мес`, and from date ranges in the work section with overlapping jobs merged (`2020–2023` twice = 3 years; `янв 2020 — н.в.`, `03.2019 – 05.2023`). |
| **AI-R7 API** | Problem+json, no duplicate work | Resume view: `UnreadablePdf` → 422, other parser errors → logged (type, sha, frames without source lines) and 500 problem+json; no second rules call. |
| **AI-R8 GigaChat** | Bounded, retried, reusable token | One transient retry (not three); `LLM_TIMEOUT_S` is a total budget counted after OAuth; chunked reads with a per-read deadline (slow-drip server test); 401 refreshes the token once; `Retry-After` clamped to [0, 2] s; token reused until expiry (lock). |
| **AI-R9 / AI-7 phrase()** | Grounded "why" sentence | Rejects unknown numbers (`250 000` = `250000`), unknown skills, > 300 chars, > 2 sentences, placeholders; `"4.5 года"`/`"Node.js"` are not sentence ends. No facts → `""`. Facts with PII never reach the provider (`pii_residual`). Accepted sentences cached by `sha256(kind, prompt version, model, facts)`. |
| **AI-R10–R13** | Fixtures, serializer fit, logging, blueprint | 3 hero CV PDFs + 1 scanned, 5 JDs (`tools/make_fixture_pdfs.py`); prefill keys fit `CandidateProfileUpdateSerializer`/`PositionSerializer` (DB test); one `llm_call` log line per call with no text; `blueprint_for` failures logged and reported as `+blueprint`. |
| **AI-R14 / AI-6** | Hygiene, docs | `.gitignore`/`conftest.py` reverted; `docs/MODELS.md` matches the code (fields, reasons, prompt versions `resume.v2`, `jd.v1`, `phrase.v1`). |

**Not done by design (needs a key or other streams):** a live GigaChat run, recorded real answers, the manual checklist (§4); taxonomy v1 and topic ids (ML); AI-8/9/10 (§5).

---

## 2. Layout

```text
apps/llm_gateway/
  __init__.py     get_gateway(), public API, __all__
  types.py        Redacted, ResumeDraft, JdDraft, ResumeParseResult, JdParseResult, UnreadablePdf
  base.py         LlmGateway/Cache protocols, GatewayConfig, LlmError hierarchy, prompt versions, load_prompt()
  pipeline.py     run(): PII gate, cache, call, validation, fallback with reason (the only fallback place)
  schema.py       validate_resume_payload(), validate_jd_payload(), enum synonyms, salary parsing
  fake.py         FakeLlm: regex + taxonomy rules (fallback and CI default)
  gigachat.py     GigaChatLlm: OAuth token cache, JSON extraction, budget, one retry
  redact.py       redact(), assert_clean()          pii_lexicon.py  names, patronymics, stop words
  pdf_text.py     extract_text()                    obs_logging.py  log_llm_call()
  resume.py       parse_resume()   jd.py  parse_jd()   phrase.py  phrase()
  prompts/        resume.v2.md  jd.v1.md  phrase.v1.md   (the version is part of the cache key)
apps/taxonomy/    loader.py (load_skills, indexes), normalize.py (normalize_skill/many, extract_skills)
content/skills.yaml
tests/ai/         no network; fixtures/{cv,jd,gigachat}/, pii_cases.yaml, skills_messy.yaml
tools/make_fixture_pdfs.py
```

Imports: `apps/` is on `sys.path`; use `from llm_gateway import ...`, `from taxonomy import ...`, never `from apps.xxx`.

---

## 3. The Contract (BE wires it)

Enum values match `core.enums`: specializations `backend|frontend|ml_data`, grades `intern|junior|middle|senior`, formats `office|hybrid|remote`, salary `gross|net`. Output keys match the flat serializer fields.

```python
# types.py
Source = Literal["llm", "rules"]

@dataclass(frozen=True)
class Redacted:
    text: str                              # placeholders: [EMAIL] [PHONE] [NAME] [URL] [TG]
    found: dict[str, list[str]]            # email, phone, telegram, url, name
    full_name: str | None = None           # the candidate's own name (not referees)

@dataclass(frozen=True)
class ResumeParseResult:
    prefill: dict             # CandidateProfileUpdateSerializer keys; skills as ids; "" / [] / None for unknown;
                              # about and experience_text are "" when PII survived redaction
    contacts: dict            # full_name, email, phone, telegram from local redaction only
    unknown_terms: list[str]
    source: Source            # "llm" only for a validated LLM answer (fresh or cached)
    fallback_reason: str | None = None

@dataclass(frozen=True)
class JdParseResult:
    draft: dict               # PositionSerializer writable keys; skills as ids
    unknown_terms: list[str]
    blueprint: list[dict]     # [{"topic", "weight"}] from ML's blueprint_for(); [] until ML-2
    source: Source
    fallback_reason: str | None = None

class UnreadablePdf(Exception): ...        # BE maps it to 422 `unreadable_pdf`

# base.py
class LlmError(Exception): reason: str     # LlmUnavailable (auth, timeout, 5xx, 429, network), LlmSchemaError
class LlmGateway(Protocol):
    name: str                              # "fake" | "gigachat"
    def resume(self, redacted_text: str) -> ResumeDraft: ...   # GigaChat RAISES; it never falls back itself
    def jd(self, text: str) -> JdDraft: ...
    def phrase(self, facts: list[str]) -> str: ...
class Cache(Protocol):                     # Django's cache fits: set(key, value, timeout) positional
    def get(self, key: str): ...
    def set(self, key: str, value, ttl: int): ...

# __init__.py (sync; BE calls them inside Celery tasks)
def get_gateway(config: GatewayConfig | None = None) -> LlmGateway: ...
def redact(text: str, *, header_names: bool = True) -> Redacted: ...   # parse_jd passes header_names=False
def extract_text(pdf_bytes: bytes) -> str: ...                         # raises UnreadablePdf
def parse_resume(pdf_bytes: bytes, *, gateway=None, cache=None) -> ResumeParseResult: ...
def parse_jd(text: str, *, gateway=None, cache=None) -> JdParseResult: ...
def phrase(facts: list[str], *, gateway=None, cache=None) -> str: ...  # "" without facts; template on any doubt

# taxonomy
def normalize_skill(raw: str) -> SkillMatch | None: ...   # exact → alias → guarded fuzzy
def normalize_many(raws: list[str]) -> tuple[list[SkillMatch], list[str]]: ...
def extract_skills(text: str) -> tuple[list[SkillMatch], list[str]]: ...
```

**`fallback_reason` values:** `provider_fake`, `provider_unknown`, `no_key`, `pii_residual`, `timeout`, `http_error`, `schema` (invalid JSON or schema after repair), `error`; `phrase` also `grounding_{length,sentences,placeholder,numbers,skills}`; `jd` adds `+blueprint` when ML's function failed; `None` when the LLM answered.

**Env/settings:** `LLM_PROVIDER` (`fake`|`gigachat`), `GIGACHAT_AUTH_KEY`, `GIGACHAT_SCOPE`, `GIGACHAT_MODEL`, `GIGACHAT_CA_BUNDLE`, `LLM_TIMEOUT_S` (total budget per call, default 10).

**How BE uses it:** `POST /candidates/me/resume` and `POST /positions/parse` run `parse_resume`/`parse_jd` on the Celery `llm` queue (concurrency 1) and wait ≤ 15 s, then call them inline with `gateway=FakeLlm()`; profile and position saves call `normalize_many()`; offer creation calls `phrase(facts, cache=django_cache)`. Requests to BE are in [BE.md](BE.md) §2.4.

---

## 4. Testing tasks (your next PR: `AI-T tests`)

Everything here is testing; the code is in place. Put results into the PR description (no CV text, no keys). A box is ticked when the work is merged into `main`.

### P0

- [ ] **AI-T1 · Live GigaChat smoke run** (AI-4).
  - Get a key (since 1 Sep 2026 new clients buy packages through cloud.ru). Check the endpoints, OAuth flow, scope and model names against developers.sber.ru and fix `GIGACHAT_*` defaults if they differ.
  - Run `GIGACHAT_AUTH_KEY=... LLM_PROVIDER=gigachat pytest -m live tests/ai -q` and paste the output.
  - Then run `parse_resume` on the 3 hero PDFs and `parse_jd` on the 5 JDs with `LLM_PROVIDER=gigachat`; record `source`, `fallback_reason`, latency for each. Expected: `source="llm"`, `fallback_reason=None`, latency < `LLM_TIMEOUT_S`.
  - Network off (or a wrong key): the same calls must give `source="rules"` with `http_error` / `timeout`, and the API still answers.
  - *Done:* live test green, a table of 8 runs in the PR.

- [ ] **AI-T2 · Recorded GigaChat answers.**
  - `tests/ai/fixtures/gigachat/` holds synthetic answers today. Record the real JSON answers from AI-T1 (redacted inputs only, check them for PII by eye) as `resume_<cv>.json`, `jd_<name>.json`, `phrase_<n>.json`.
  - Add replay tests: each recorded answer goes through `validate_*_payload` and the orchestrator with a stub gateway, and the result is compared with the expected fields from AI-T3.
  - Add at least one recorded malformed answer if you see one (prose around JSON, unknown enum, salary as text).
  - *Done:* ≥ 8 recorded answers, replay tests green with no network.

- [ ] **AI-T3 · Manual checklist** `tests/ai/fixtures/README.md` (AI-5).
  - For each of the 3 CVs and 5 JDs: expected specialization, grade, years, skills, salary min/max/type, formats, city; then the actual output from rules and from GigaChat side by side. Mark every mismatch and either fix the rule/prompt (a separate PR) or write down why it is acceptable.
  - Check `unknown_terms` is populated for non-taxonomy skills, `"Postgress"` and `"k8s"` map correctly, and `source` is truthful.
  - *Done:* the table is committed; no unexplained mismatch.

- [ ] **AI-T4 · PII red-team, round 2** (AI-2).
  - Start from `pii_cases.yaml` (87 cases). Known gaps the reviewer left on purpose (each is either masked partly or blocked by `assert_clean`, but check they never reach the LLM): names on two separate lines (`ИВАН\nПЕТРОВ`), non-dictionary names deep in prose (`с Шамилем Гасановым`), `оглы`/`кызы` names, homoglyphs (Latin `а` inside a Cyrillic name, `github.соm`), `Telegram ivanpetrov` without a separator, `GitHub ivanpetrov · LeetCode ivanpetrov`, a translit of the own name in the body (`Sasha Petrov`), an email wrapped inside the local part.
  - Over-masking to watch (loses information, no privacy risk): `@SpringBootTest`/`@BotFather` in the first 10 lines, `Telegram: Telethon, Pyrogram`, `Руководитель Группы Тестировщиков`.
  - For each new leak: add a case to `pii_cases.yaml` first (forbidden + must_preserve), then fix `redact.py`/`pii_lexicon.py`. Every case must also pass `assert_clean`.
  - Run the hero CVs and 20 real-looking synthetic CVs (different layouts: hh.ru export, LinkedIn export, two-column PDF) through `redact` and read the output by eye.
  - *Done:* ≥ 120 cases, zero leaks that reach the LLM, no regression in `skills_messy.yaml`.

### P1

- [ ] **AI-T5 · Robustness and load.**
  - 50 consecutive `parse_resume` calls with GigaChat on the `llm` queue (concurrency 1): no token refresh storm, no 429 loop, cache hits on repeats (`cache_hit=True` in logs).
  - Fuzz `redact`, `FakeLlm.resume/jd`, `validate_*_payload` with random/huge input (Hypothesis or a loop over random bytes decoded as text): no exception, < 1 s per 200 KB.
  - Corrupt PDFs (truncated, wrong header, 20+ pages, 5 MB): `UnreadablePdf` or text, never a 500.

- [ ] **AI-T6 · End-to-end through the API** (with BE).
  - Upload the 3 hero PDFs via `POST /candidates/me/resume` with `LLM_PROVIDER=gigachat` and with `fake`; check the response shape, 422 for the scanned PDF, 401/403 boundaries, and that the onboarding form (FE1) shows the prefill and the LLM/rules badge.
  - Check the `llm_call` log lines in the worker log: one per call, no text.
  - Known WARNs from `verify` that are not AI's: `CandidateContact` in Django admin (BE), bare `timezone.now()` in `assessment` (ML/BE).

- [ ] **AI-T7 · phrase() acceptance** (AI-7, after ML fixes the fact format from `Scored.reasons`).
  - 20 recorded fact sets → every GigaChat output passes grounding or falls back to the template; record the rejection rate per rule.

---

## 5. Development left (not part of the LLM API integration)

- [ ] **AI-1 · Taxonomy v1** (~300 skills from 105). Cover the three specializations evenly; RU/EN spellings, typos, abbreviations; `related` ids must exist. Agree topic ids with ML (`content/specializations.yaml`, ML-2) and add a CI test that every `topic` exists there (skip while the file is missing). *Done:* ≥ 95% on `skills_messy.yaml` (grow it to ≥ 300 inputs) with 0 false positives.
- [ ] **AI-8 · Offline family drafting** (`tools/draft_families/`): CLI, prompt with the `ItemFamily` protocol (ML.md §3), output with provenance, pre-check with ML's verify harness; nothing in `apps/` imports `tools/`. *Done:* ML accepts ≥ 10 families.
- [ ] **AI-9 · Concept-MCQ pools** in the format agreed with ML; two human reviewers per entry. *Done:* ≥ 20 reviewed concepts.
- [ ] **AI-10 · Embedding alias resolution** (optional, after ML-9): cosine ≥ 0.85, no ambiguous winner.
- [ ] Optional: `natasha` NER on top of the name lexicon (local only; add it to MODELS.md); masking birth dates and passport numbers (today a passport number only blocks the LLM call).

---

## 6. Interfaces With Other Streams

| With | You give | You need |
|---|---|---|
| **BE** | The §3 contract, `content/skills.yaml`, the env list, `UnreadablePdf` | The Celery `llm` queue (concurrency 1) with the 15 s wait and inline rules fallback; `IsCandidate` + throttle on `/candidates/me/resume`; `sync_taxonomy`; Redis cache passed as `cache=`; `phrase()` on offer creation (BE.md §2.4) |
| **ML** | Skill ids; your topic list; drafted families and MCQ pools | `blueprint_for(spec, skill_ids)`; topic ids; the verify harness (ML-1); the fact format for `phrase()`; the embedding helper |
| **FE1** | Semantics of `prefill`, `unknown_terms`, `source`, `fallback_reason` | — |
| **FE2** | Semantics of `JdParseResult` (must/nice chips, blueprint bars, empty fields stay empty) | — |

## 7. Working Agreements

- CI never calls the network. `LLM_PROVIDER=fake` is the default everywhere except staging.
- Prompts are files with a version in the name; changing a prompt bumps the version (and the cache key).
- Log provider, model, prompt, input hash, latency, cache hit, source and fallback reason. Never text, never exception messages.
- Run `python .claude/skills/verify/scripts/verify.py` before every push; it must pass.
- A regression test first for every bug (`pii_cases.yaml`, `skills_messy.yaml`, `test_*`), then the fix.
- Small PRs (< ~400 lines) titled with the task ID (`AI-T1 live GigaChat run`). Don't edit BE-owned files without agreeing with BIKHE in the PR description.
