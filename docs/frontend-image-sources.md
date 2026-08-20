# SmartRetailX Frontend Image / Asset Sources

The public landing page was intentionally built **without external
photography**. Every visual element (hero, category cards, deals section,
benefits, "how it works", footer) is rendered from:

- CSS gradients derived from the existing design tokens in
  `frontend/src/styles.css` (colours, radii, shadows).
- Inline SVG icons authored directly in the JSX of
  `frontend/src/pages/LandingPage.tsx`. Every icon is a small,
  original stroke-only path drawn from scratch in the same visual
  family as the rest of the app.

## Why no external photography

- **Reliability.** The app must load under CloudFront + a strict CSP
  and must not rely on third-party image CDNs staying up.
- **Licensing safety.** No risk of accidentally using a copyrighted
  retailer image or a mis-attributed stock photo.
- **Performance.** Zero external network requests for the hero above
  the fold — best-case LCP.
- **Design coherence.** The rest of the app is a minimalist monochrome
  design system (Plus Jakarta Sans, Zinc palette, subtle shadows).
  Injecting stock photography would clash with that identity.

## Fonts (already loaded pre-existing)

- **Plus Jakarta Sans** — Google Fonts. Loaded via `<link>` in
  `frontend/index.html`. Open Font License (OFL). No change from prior state.
- **JetBrains Mono** — Google Fonts. OFL. No change from prior state.

## Icons

All SVG icons in `LandingPage.tsx` were authored in this repository for this
feature. No third-party icon set is imported; nothing needs attribution.

## If a photographic hero is added in the future

Use only sources that permit commercial reuse:

- Unsplash (Unsplash Licence, no attribution required — attribution
  encouraged as a courtesy)
- Pexels (Pexels Licence)
- Pixabay (Pixabay Content Licence)
- Wikimedia Commons (per-file check)

Do NOT:

- Copy images from live retailer sites (Amazon, Argos, Tesco, etc.).
- Use Google Image search `encrypted-tbn0.gstatic.com` thumbnail URLs.
- Embed images whose licence you cannot confirm.

Add every used image URL, source page, and licence to this file at the time
it is added to the code.
