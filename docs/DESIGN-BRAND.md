# Design: Brand-Book Alignment (FE2 scope)

Status: implemented. Applies to all FE2 surfaces (test runner, employer
master, scouting, offers, talent search).

## Theme switch: dark "Arena" → light brand book

All raw colour values live in `web/src/styles/tokens.css` only (rule R7b);
components consume `--fsp-*` variables or the Tailwind `@theme` mapping, so
the whole app re-skinned without touching component markup.

### Palette (from the event brand book)

| Token | Hex | Role |
|---|---|---|
| `--fsp-bg` / `--fsp-panel` | `#FFFFFF` | main background, cards |
| `--fsp-fg` | `#1C1D22` | body text |
| `--fsp-heading` | `#310F53` | headings, logo, navigation text |
| `--fsp-accent` | `#FF0053` | CTA fills, active elements, rings |
| `--fsp-accent-hover` | `#FC3777` | button hover (crimson) |
| `--fsp-accent-strong` | `#D10044` | AA-safe accent **text** on white |
| `--fsp-brand` | `#520978` | primary brand elements, score segments |
| `--fsp-secondary` | `#8A83D1` | secondary accents, icons |
| `--fsp-surface-soft` | `#FFD6E4` | light-pink block underlays |
| `--fsp-line` | `#E5E0EE` | borders (violet-tinted hairline) |
| `--fsp-panel-hover` | `#F6F2FA` | muted/hover surfaces |
| `--fsp-gradient-brand` | `#310F53 → #520978 → #FF0053` | hero/banner gradient (`--color-*` mapped for Tailwind) |

Semantic status colours were re-derived for WCAG AA on white (see the ratio
table in the token file): plus `#15803D`, minus `#DC2626`, info `#1D4ED8`,
warn `#92400E`; offer/league/score tokens reuse these AA-safe tones and the
brand violet family.

Note: `#FF0053` on white is 4.44:1 — fine as a fill with a white label
(4.89:1) and for large/decorative text, but small accent copy must use
`--fsp-accent-strong`. Applied in `talent-row`, `filter-panel`,
`position-detail-page`, `shortlist-tray`.

## Typography

Montserrat via self-hosted variable woff2 (`@fontsource-variable/montserrat`,
imported in `web/src/index.css`; cyrillic subsets bundled). Token:
`--fsp-font-sans: 'Montserrat Variable', 'Montserrat', system-ui, …`.

## Component touchpoints (minimal, token-driven)

- `button.tsx` — default variant now has crimson hover / strong-active states.
- `card.tsx` — flat/minimal look: hairline border + `--shadow-card`
  (soft violet-tinted shadow), replacing the dark-theme `shadow-sm`.
- `app-layout.tsx` — header wordmark in dark violet (`text-heading`).
- Global `h1–h4` → `--fsp-heading`; helper classes `.fsp-hero` (brand
  gradient banner) and `.fsp-card` in `index.css`.
- `color-scheme: light` pinned to prevent UA dark-mode form controls.

## Dev preview

`/dev/design` (`design-variants.tsx`) now shows **"Brand book (light)"**
(`.dv-brand`) first, alongside the archived Arena/FSP-Red/Corporate variants.

## Verification

`tsc --noEmit` ✓ · `eslint .` ✓ · `vitest run` 114/114 ✓ · `vite build` ✓
(Montserrat woff2 assets emitted to `dist/assets`).
