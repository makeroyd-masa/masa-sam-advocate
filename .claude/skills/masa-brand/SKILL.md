---
name: masa-brand
description: Apply MASA Global brand standards (colors, typography, logo) to any UI, React component, page, email, form, or visual artifact in this repo. Use whenever building or restyling frontend, generating a member-facing screen, or when asked to make something on-brand / apply MASA styling.
---

# MASA Brand

Brand decisions live in the repo — import them, don't hardcode hex values in components.

- **Tokens:** `src/styles/tokens.css` — import it and use the CSS variables.
- **Logo:** `public/logo.svg` (Horizon, light bg) · `public/logo-white.svg` (dark bg) · `public/mark-white.svg` (the "+" mark only).
- **Visual reference:** `docs/SAM_screens_v0_1.html` is the canonical look for SAM surfaces (cards, bottom-sheets, buttons, fields).

## Colors — roles, not just values
- `--masa-horizon` `#230871` — PRIMARY: headlines, CTAs, advocate actions, borders.
- `--masa-tide` `#0071CE` — SECONDARY: the ×-Medicare leverage signal, links/highlights.
- `--masa-flare` `#E64B38` — RESERVED for text links and the escalation action only. Never a primary fill or a decorative border.
- `--masa-shine` `#FFD040` — honesty / caution nodes only, sparingly.
- `--masa-harbor` `#968694` — dividers, captions, muted text.

## Typography
- Display / CTAs: **Poppins** (600/700). Body: **Open Sans** (400/600/700).
- Sentence case for everything, including headings. Left-align body copy.

## Logo rule
- In structural positions (app header/nav, sheet headers, footers) use the logo or mark SVG — never the typed word "MASA". Typed "MASA" is acceptable only inside running prose.
- The app header is Horizon `#230871`: use `logo-white.svg` or `mark-white.svg`. On white surfaces use `logo.svg`.
- Never recolor, distort, crowd, or reconstruct the logo; keep clear space around it.

## Quick check before shipping UI
1. Imported `tokens.css`; no raw hex in the component?
2. Flare used only for links/escalation?
3. Logo SVG (not typed "MASA") in any header/nav/footer?
4. Poppins for headings/CTAs, Open Sans for body, sentence case?
