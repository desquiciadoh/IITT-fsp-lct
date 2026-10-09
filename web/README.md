# fsp-web

React SPA для FSP Draft (хакатон ЛКТ 2026). Скелет по спеке **FE1.md** (FE1-0): роуты,
гарды, API-слой, моки, дизайн-система «Arena (dark)».

## Стек

- Vite 7 + React 19 + TypeScript strict
- Tailwind CSS v4 (`@import 'tailwindcss'` + токены в `src/styles/tokens.css`)
- shadcn/ui-стиль компоненты (`src/components/ui/`, стиль new-york)
- TanStack Query v5, react-router-dom v7, sonner
- MSW v2 (моки), Vitest, ESLint flat + Prettier
- orval → типы моделей из OpenAPI бэка (хуки не генерируем, см. API-слой)

## Команды

```bash
pnpm install          # зависимости
pnpm dev              # dev-сервер http://localhost:5173
pnpm typecheck        # tsc --noEmit
pnpm lint             # eslint .
pnpm format           # prettier --write .
pnpm test             # vitest run
pnpm build            # typecheck + vite build
pnpm api:schema       # openapi/schema.json из живого бэка (или ../docs/openapi.json)
pnpm api:gen          # src/api/generated/ из openapi/schema.json
```

## Окружение

`.env.local` (см. `.env.example`):

| Переменная | Значения | Смысл |
| --- | --- | --- |
| `VITE_API_MOCKS` | `off` (default) / `missing` / `all` | `missing` — мокать только дыры бэка G1–G17, `all` — всё, бэк не нужен |

## Прокси

`vite.config.ts` проксирует `/api` и `/admin` на `http://127.0.0.1:8000`.
**Не включайте `changeOrigin: true`** — Django сверит `Origin` из CSRF-заголовка
и будет отклонять запросы (спека FE1.md §1).

## API-слой

- `src/api/client.ts` — общий fetch-mutator: куки, `X-CSRFToken` на небезопасных
  методах, нормализация ошибок в `ApiError` (обе формы бэка: problem+json и
  `{detail: ...}`), маппинг кодов → русский текст через `src/i18n/errors.ts`.
- `src/api/types.ts` — DTO. Типы, которые есть в схеме, выводятся из
  `src/api/generated/models` (один источник истины); руками остаются только
  формы, которые drf-spectacular отдаёт как `string`/`unknown`, и дыры G3/G5/G8.
- `src/api/keys.ts` — все ключи TanStack Query.
- `src/api/me.ts` — `useMe()` (текущий пользователь, 401 → редирект на `/login`).
- `src/api/<feature>.ts` — хуки фич (`profile.ts`, `assessments.ts`, `offers.ts`)
  поверх `customFetch`. Своих fetch не заводим.
- `src/api/events.ts` — `useLiveEvents(enabled)`: SSE `/api/events` → инвалидация
  запросов; при ошибке потока — фолбэк на polling 10 с (бэк сейчас ломает SSE,
  B14), повтор SSE каждые 60 с. `usePollingInterval()` для `refetchInterval`.
- `src/api/generated/` — orval (**не редактировать руками**): `models/` — схемы,
  `fSPDraftAPI.ts` — fetch-клиент «на будущее», приложение его не импортирует.

## Роуты и гарды

- `/` → редирект по роли; `/login` (форма + демо-персоны), `/register`, `/verify`.
- Кандидат: `/candidate`, `/candidate/onboarding/:step`, `/candidate/offers[/:id]`,
  `/candidate/settings`, `/candidate/qualification/*` (раннер — FE2).
- Работодатель: `/employer`, `/employer/company`, `/employer/positions/*`,
  `/employer/talent`, `/employer/offers` (всё FE2).
- Публичные (без логина, под `AppLayout`): `/jury` (FE-03), `/lab`, `/dev/ui`
  (UI-кит), `/dev/design` (палитры), `/home`; `/` для анонима → `/jury`.
- Гарды: `RequireAuth` → `RequireRole` → `OnboardingGate`
  (`src/app/guards.tsx`). Шаг `qualification` пускает раннер/результат
  (`/candidate/qualification/*`), остальное уводит на `/candidate/qualification/start`;
  `consent`/`profile` → `/candidate/onboarding/<step>`. Заглушки — `src/app/placeholder.tsx`.

## Моки (MSW v2)

- `src/mocks/browser.ts` — точка входа, стартует в `main.tsx` до рендера.
  `missing` = только дыры бэка, `all` = ещё демо/core/оценки/офферы/FSP/PDF.
- `src/mocks/handlers/gaps.ts` — дыры G1–G17 (csrf, verify-email, taxonomy,
  leagues, positions/parse, assessments/finish, lab/report).
- `src/mocks/handlers/demo.ts` — демо-персоны, time-travel (только `all`), reset.
- `src/mocks/handlers/core.ts` — `/api/me`, логаут, профиль кандидата.
- `src/mocks/handlers/assessments.ts` — оценки: list, eligibility, result, `card.pdf`.
- `src/mocks/handlers/offers.ts` — офферы: список, деталь, view/accept/decline с 409.
- `src/mocks/handlers/fsp.ts` — привязка FSP, sync (в т. ч. 409 на занятый id).
- Все мок-ответы несут заголовок `X-Stub: true`.

## Дизайн

- Токены: `src/styles/tokens.css` — направление **Arena (dark)** (акцент
  `#b8ff3c`, фон `#0b0f14`). Пока не утверждён брендбуком (PD-02): менять
  значения в токенах, не классы в компонентах.
- Доменные компоненты: `src/components/domain/` (лига, рейтинг, зарплата,
  статусы, чипы причин, скоринг, оффер, талант, FSP, доверие, состояния).
- Все видимые строки — русский, через `src/i18n/` и `src/lib/labels.ts`.

## Для FE2 (второй фронтендер)

1. Экраны-заглушки уже зароучены — заменяйте содержимое в `src/app/router.tsx`.
2. Данные — хук в `src/api/<feature>.ts` поверх `customFetch` + ключи из
   `src/api/keys.ts`; типы берите из `@/api/types` (не заводите второй fetch).
3. Строки — русские, общие лейблы уже в `src/lib/labels.ts`, ошибки в
   `src/i18n/errors.ts`.
4. Тест-раннер (FE-12): для обратного отсчёта берите `served_at` + локальное
   время получения ответа, не абсолютное время сервера (clock-skew);
   `useCountdown` — `src/lib/hooks/useCountdown.ts`.
5. Пул талантов: `ScoreBar` принимает и словарь, и список — нормализация в
   `src/components/domain/normalize.ts`.

## Структура

```
src/
  api/          client, keys, types, me, events, profile, assessments, offers, generated/
  app/          router, guards, providers, index-redirect, layouts/, placeholder
  components/   ui/ (shadcn-стиль), domain/ (фича-компоненты)
  features/     auth/, onboarding/, result/, candidate/, offers/, settings/, jury/
  i18n/         ru.ts, errors.ts
  lib/          labels, format, utils, personas, hooks/
  mocks/        browser, handlers/, fixtures/
  pages/        home, dev-ui, design-variants
  styles/       tokens.css
```
