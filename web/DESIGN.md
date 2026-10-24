# Reachwise design system

Reachwise is one mailing platform with modules for different audiences. *Academic*, for students
writing to professors, is the first. Every surface (this website, a mobile web view, and a future
iOS/Android app) uses the same tokens, so they look like one product.

## Source of truth

- `src/design/tokens.json`: colours, fonts, sizes, radii, spacing, shadows, layout sizes. A React Native
  or Flutter app imports this file directly.
- `src/design/tokens.css`: the same values as CSS variables for the web. Change both together.
- `src/brand.js`: product name, module name and tagline. Rename the product here (and in `index.html`).
- `public/icon.svg`: the app icon, a rounded square, works from 16 px to 1024 px. Export PNGs from it
  for app stores.

## Colour roles

| Token | Use |
|---|---|
| `primary` #2F3BA2 | Main actions, active navigation, links |
| `accent` #E8A33D | Highlights only: the logo dot and the step that's live now. Never use it for text on white. |
| `ink` / `inkSoft` / `muted` | Text, from headings to hints |
| `background` / `surface` / `line` | Page, cards, dividers |
| `success` / `warning` / `danger` (+ `Wash`) | Status only, each with a pale background version |

Text on `primary` is white. Every text and background pair meets WCAG AA contrast.

## Type

- **Manrope** for the interface (500 body, 700 labels and buttons, 800 headings).
- **Source Serif 4** for anything that is an email: the editor, previews and received replies. This keeps
  "what the professor reads" visibly separate from the app around it.

## Layout rules that carry over to mobile

- Touch targets are at least 44 px (`layout.touchTarget`).
- Under 760 px wide: the sidebar becomes a drawer, and a 5-item bottom bar appears (Professors, Emails,
  Send, Replies, More). Use the same bar in the native app.
- Cards use `radius.lg` (18), inputs and buttons `radius.sm` (8), pills `radius.pill`.
- One primary button per screen section.

## A new module (for example, job applications)

Keep the tokens and components. Change only `BRAND.module` and the wording. A module may add its own accent
colour, but `primary` stays the same across the platform.
