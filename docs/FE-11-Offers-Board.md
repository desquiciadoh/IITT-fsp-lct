# FE-11 · Send Offer & Offers Board (employer)

Task source: `FE2.md` § FE-11. Branch: `fe-11-offers-board` (based on FE-05 HEAD; the
FE-10 pool branch is integrated later through a stub — see “Integration”).

## Scope

Two employer screens built on `POST /api/offers`, `GET /api/offers?status=` and
`POST /api/offers/{id}/withdraw`:

1. **Send Offer modal** — `src/features/employer/send-offer-modal.tsx`
   (+ pure logic in `send-offer-schema.ts`).
2. **Offers board** (`/employer/offers`) — `src/features/employer/offers-board-page.tsx`:
   flat array from the API grouped into 9 status columns
   (`sent, viewed, accepted, declined, withdrawn, expired, interview, hired, closed`).

## Flow

1. Employer picks a candidate (currently `<CandidateSelectorStub />`) and opens
   “Отправить оффер”.
2. The modal prefills title/description/salary range/type from the position when a
   position object is passed (`prefillFromPosition`).
3. Zod validation runs client-side (`sendOfferSchema`): positive bounds,
   `min <= max`, explicit `salary_type`, contact value required unless the channel is
   `platform`.
4. `useCreateOffer` posts the payload; on success the board + pool caches are
   invalidated, so the new offer appears in the `sent` column.
5. Candidate accepts (FE-07 flow) → within ≤10 s (polling fallback) or instantly via
   SSE the card moves to `accepted` and the **contacts panel** appears on the card.
6. Employer can **withdraw** while `sent`/`viewed`; on 409
   (`version_conflict` / `invalid_transition`) the board refetches.

## API layer (`src/api/offers.ts`, `src/api/keys.ts`)

- `CreateOfferPayload` type + `useCreateOffer()` mutation — always sends
  `salary_type` explicitly (**B15**) and defensively strips `why_you` (**B9**,
  server-computed).
- `useWithdrawOffer()` — optimistic-lock `{version}` body, writes the returned offer
  into `keys.offer(id)` and invalidates `['offers']`.
- `useOffers(status, view)` — `view: 'employer'` adds the `X-FSP-View: employer`
  header and its own query key (`keys.offersBoard`); default remains the candidate
  inbox (backwards compatible with FE-07 pages).

## Live updates (B14)

The board mounts `useLiveEvents` (shared SSE client from FE-05). While the backend
SSE misbehaves (**B14**), the stream error switches the shared polling flag on and
every offers query refetches every 10 s (`POLLING_INTERVAL_MS`), retrying SSE each
60 s. No feature-level duplication of this logic.

## Backend bugs/gaps worked around

| ID | Workaround |
|----|------------|
| B9  | `why_you` is never sent; `useCreateOffer` deletes it from the body as a guard. |
| B14 | 10 s polling fallback via the shared `usePollingInterval` (see above). |
| B15 | `salary_type` is a required zod enum field and always serialized in the payload — the UI never relies on the silent gross default. |
| B16 | Contacts panel renders only while `status === 'accepted'` (`contactsVisible`); once BE bases it on the grant, only that predicate changes. |
| G10 | Employer payload has no candidate identity. Mock returns `talent: {public_id, display_name}`; `candidateNameOf` falls back to `«Кандидат скрыт (G10)»` plus title/salary/status/dates. |

## Error mapping (modal)

`mapSendOfferError` (`send-offer-schema.ts`) turns `ApiError` codes into Russian:
`422 salary_invalid`, `403 candidate_not_reachable`, `404 not_found`,
serializer `errors.{field}` objects land under the matching form fields.

## Mocks (`src/mocks/handlers/offers.ts`)

- Separate `employerStore` behind `X-FSP-View: employer` (one `sent` + one `accepted`
  offer with contacts for the B16 demo).
- `POST /api/offers`: DRF-style 422 field errors, `422 salary_invalid`,
  `403 candidate_not_reachable` for the reserved id `pub-unreachable`, honours
  `expires_in_days`.
- `withdraw` added to `TRANSITIONS` (`sent/viewed → withdrawn`); the action handler
  now resolves ids across both stores, so withdraw works against employer offers.

## Integration note (FE-10)

`<CandidateSelectorStub />` exports from the board page and will be replaced by the
real pool row/drawer trigger from FE-10 (`pool` invalidation is already wired in
`useCreateOffer`). No other coupling.

## Tests

`src/features/employer/send-offer.test.ts` — 16 pure-logic tests (node env): schema
bounds/explicit salary_type/contact rules, prefill, payload shape (no `why_you`),
error-code mapping, `canWithdraw`/`contactsVisible`/`groupByStatus`.

Run: `npm run typecheck && npx vitest run` (the two pre-existing failures in
`qualification.test.ts` reproduce on the base commit — unrelated to FE-11).
