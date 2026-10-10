# FE-05 · Test Runner — Stage 3: Item Screen (Test Runner)

Component: `web/src/features/qualification-runner/test-runner-page.tsx` (`TestRunnerPage`)
Route: `/candidate/qualification/:id` (react-router, lazy-loaded; start screen lives at `/candidate/qualification/start`, results are owned by FE-06 at `/candidate/qualification/:id/result`)
All UI copy is Russian; this doc is English per hackathon DoD ("document briefly in English in docs").

## 1. Session-driven rendering

The runner renders **one served item at a time**. State comes exclusively from the session query:

| Source | Endpoint | Role |
|---|---|---|
| `useSession(id)` | `GET /api/assessments/{id}` | authoritative `current` item + progress; cache primed by `useCreateAssessment`, kept fresh in place by `usePostAnswer` |
| `usePostAnswer(id)` | `POST /api/assessments/{id}/answers` | submits the draft answer + integrity counters |

Because the cursor lives server-side (stateful MSW mock keeps it in a module-level store), a browser refresh mid-test resumes at the exact same item with zero extra wiring.

Render states:
- `isLoading` → `CardSkeleton`.
- `isError` with code `not_found` → `ErrorState` ("Сессия теста не найдена") redirecting to the start screen; any other error → `ErrorState` with retry (`refetch`) — progress is safe on the server.
- Session loaded but `current === null` (finished elsewhere / globally expired) → neutral card with «К результатам» button → `resultPath(id)`.
- Otherwise the item card below.

### Item card layout (Russian UI)
- Header: **«Задание {seq} из {max_items}»** (total hidden when backend omits `max_items` — gap G5), optional «Сложность: {level}», and the countdown chip (§2).
- Stem: `MarkdownText` (`react-markdown`, raw HTML never survives; fenced blocks delegate to the highlighter).
- Code snippet: `CodeBlock` (§3).
- Answer control depends on `input_type`:
  - `choice` → radio `<fieldset>` («Варианты ответа»), each label rendered as markdown; selected option highlighted via `has-[:checked]` styles.
  - `number` → numeric `<Input inputMode="numeric">` («Ответ (число)»).
  - `text` → `<textarea>` («Ответ»).
- Footer hint (neutral): «Выберите ответ, чтобы продолжить.» / «Отправляем…» / «Ответ будет засчитан сразу после отправки.»; submit button «Следующее задание» is disabled until the draft is non-empty (empty auto-submits on timeout still go through — an empty answer counts as incorrect, BE.md H5).

Draft state (`choice` / `textValue`) resets automatically whenever `item_id` changes.

## 2. Timer with clock-skew correction

Server deadlines are authoritative, but the candidate's device clock may be wrong. The client therefore trusts the **duration**, not absolute timestamps:

```
remaining = (deadline_at − served_at) − elapsed_local_since_receive
```

- `receivedAtMs` is captured once per item in a `Map<item_id, wall-clock>` ref inside `TestRunnerPage`, so re-renders never drift the anchor.
- Pure helper `skewAdjustedDeadline(item, receivedAtMs)` converts the payload into a local-clock deadline ISO string; falls back to the raw `deadline_at` when timestamps are missing/unparseable.
- `useCountdown(adjustedDeadline)` (shared hook, 1 s tick) yields `{ remainingMs, expired }`.
- Display: monospace `MM:SS` chip, `role="timer"`, `aria-label="Осталось N секунд"`, `data-expiring="true"` in the last 10 s (styling hook only — no scary UX).
- **Auto-submit on expiry**: exactly one fire per item, guarded by `autoFiredFor` ref keyed by `item_id` (prevents double POST across re-renders). The effect calls `submitRef.current(true)` — a ref holding the freshest submit closure — which keeps the `useEffect` dependency array honest (`[expired, item]`) with no `eslint-disable`.
- If an *automatic* submit fails for transient reasons, it retries once after 2 s (the candidate is never trapped on a dead timer). Error codes handled explicitly:
  - `item_not_current` (409, another tab answered) → silent `refetch()` of the session; UI flips to the authoritative next item.
  - `assessment_expired` (409) → Russian toast + redirect to results.

## 3. Rendering internals (`render.tsx`)

- **Shiki is lazy-loaded**: `import('shiki')` runs only on first `CodeBlock` mount, so Vite code-splits the grammar set out of the critical chunk. Theme `github-dark`; unknown languages fall back to `lang: 'text'`; if Shiki itself fails, a plain `<pre>` renders the code (never blank).
- Highlighted output is inserted via `dangerouslySetInnerHTML` — safe because Shiki emits fully escaped, self-contained HTML.
- `MarkdownText` wraps react-markdown with `disallowedElements={['script','iframe','object','embed']}` + `disallowedElements` fallback styling; inline/fenced code inside stems reuses the same lazy highlighter when a language fence is present.
- Languages in the 8-item mock bank: `python`, `javascript`, `sql`.

## 4. Integrity metadata (silent capture)

Implemented in `web/src/features/qualification-runner/integrity.ts` per BE.md §H5:

- `useIntegrity(itemId)` returns `{ read, bumpPaste }`:
  - `focus_loss` — incremented on `document.visibilitychange` → `hidden` (tab switch / minimize). Listener attached once per screen; counters reset to zero whenever `item_id` changes (integrity is per item).
  - `paste` — incremented by `bumpPaste` wired to `onPaste` on the radio fieldset, number input, and textarea.
- Counters live in refs (deliberately non-reactive) and are snapshotted by `read()` at submit time, normalized by `toWireIntegrity`, and sent inside the answer body: `integrity: { focus_loss, paste }`.
- **Neutral UX is a product requirement**: the candidate sees no warnings, badges, or hints about monitoring. The data flows to scoring/jury only (FE-06 shows topic evidence, not raw counters).
- Security invariant preserved: the client never learns per-item correctness — only `next`/`result` come back from the API.

## 5. Back-navigation lock

While an item is live, the runner pushes a sentinel history entry (`{ qaGuard: true }`):
- `popstate` → immediately re-pushes the sentinel, so the browser "back" button cannot leave the test mid-item (the candidate stays on the same question; nothing is lost).
- `beforeunload` → standard native "Leave site?" prompt guards closing/reloading the tab (progress is server-persisted anyway; resume works via the start screen).
- Listeners are attached/removed based on `hasItem` only, and torn down when the session completes (no item → guard off, navigation to results proceeds freely).

## 6. Testing

Unit tests: `web/src/features/qualification-runner/test-runner-page.test.ts` (node env, pure helpers):
- `skewAdjustedDeadline` — duration anchoring under a skewed local clock, fallback on missing/unparseable timestamps, clamp at zero duration.
- `buildAnswerInput` — choice vs number/text shapes, trimming, empty-answer wire values.
- `resultPath` — FE-06 route contract.

Manual run against the stateful MSW mock (8 items, three sample families):

```bash
cd web
VITE_API_MOCKS=all pnpm dev
# /qualification/start → «Начать тест» → runner at /candidate/qualification/{id}
```

Scenarios to verify:
1. **Full pass**: answer all 8 (radio/number/text variants) → final answer lands `done:true` → redirect to results route (FE-06 stub).
2. **Refresh mid-test**: reload the tab at item 3 → resumes at item 3 with a freshly served deadline.
3. **Timeout auto-submit**: the mock gives short `time_limit_s`; let one item expire with no selection → empty answer is posted, next item appears; DevTools Network shows exactly one POST per expired item.
4. **Skew**: set OS clock +5 min before starting → countdown still matches the server budget (duration-based anchoring).
5. **Back button**: press browser back mid-item → you stay on the same question.
6. **Integrity**: switch tabs twice and paste into the textarea → inspect the POST body: `integrity.focus_loss >= 2`, `integrity.paste >= 1`; UI shows nothing about it.
7. **Two-tab race**: open the same session in two tabs, answer in A, then answer in B → B gets 409 `item_not_current`, silently refetches and shows the next item.

## 7. Known gaps

- `mode: express/full` currently doesn't change item count on the mock (planned with backend G5); runner reads `max_items`/`level` optionally.
- Results screen (`resultPath`) is FE-05 → FE-06 handoff; runner only navigates there.
