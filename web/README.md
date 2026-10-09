# fsp-web

Frontend for the FSP Draft platform (React + TypeScript + Vite).

## API client layout (why the generated client is dead code)

- `openapi/` and `src/api/generated/{fSPDraftAPI.ts,models/}` are produced by
  `pnpm api:schema && pnpm api:gen` (orval, `orval.config.ts`).
- `client: 'fetch'` makes orval emit `src/api/generated/fSPDraftAPI.ts`, but
  that client is **not importable from app code**:
  `no-restricted-imports` in `eslint.config.js` rejects
  `@/api/generated/fSPDraftAPI` (R28). The app talks to the backend through
  the hand-written hooks in `src/api/*.ts`, which use `customFetch`
  (CSRF token + problem+json error translation). Only `models/` types are
  re-exported through `src/api/types.ts`.

## Commands

- `pnpm dev` — Vite dev server
- `pnpm typecheck && pnpm lint && pnpm test && pnpm build` — quality gates
- `pnpm api:schema` then `pnpm api:gen` — regenerate the typed client after
  the backend schema changes