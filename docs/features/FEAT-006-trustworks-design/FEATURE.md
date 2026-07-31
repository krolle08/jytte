---
id: FEAT-006
slug: trustworks-design
title: Re-skin Jytte to the Trustworks visual identity
status: review
priority: medium
target: python
depends-on: []
created: 2026-07-31
---

# FEAT-006 - Trustworks design compliance

## Goal
Bring the Jytte dashboard in line with the Trustworks brand kit (`~/.claude/skills/trustworks-design/`): paper-first light theme, ink text, aqua + gul accents used sparingly, brand-blue hairlines, Inter/Neue Haas Grotesk type, square corners on chrome and 18px on cards, almost no shadows, no HUD glow.

## Approach (this pass)
The theme is fully driven by CSS custom properties in `app/static/styles.css`, so the re-skin remaps the semantic `:root` tokens to Trustworks values and the palette flips app-wide. Then the hard-coded dark chrome is fixed by hand.

Landed:
- `:root` remap: paper `#FAF8F4` bg, ink `#111114` text, brand-blue `#113274` hairlines, aqua/gul tints, `--accent` = brand blue, Inter/NHG fonts.
- Body flattened to paper; HUD removed (scanlines, glow pulses, gradient brand text, backdrop blur).
- Cards: white surface, 18px corners, soft hairline, subtle shadow (no glow).
- Drawer: paper panel, brand-blue left hairline, ink text (was dark).
- Tags: aqua/gul tints, no glow.
- Chat box + docs code block: paper surfaces (were dark).
- `.ado-body` color-normalize (also fixes BUG-001 unreadable pasted HTML).

## Out of scope (follow-up polish)
Per-widget internals still carrying hard-coded dark rgba (news rows, ADO tab sections, budget editor, geomap map + its dark tooltip, football, freshness banner, edit forms) - a second pass can tighten these. The map viz stays dark by design.

## Notes
- Trustworks copy convention favours em-dashes, but the user's global rule forbids em/en dash; plain hyphen is used throughout.
- Neue Haas Grotesk is bound via `local()` (licensed); Inter is the served fallback.

## Definition of done
- [x] App loads on the paper palette; chrome + cards + drawer on-brand
- [x] Boots; `/health` green; CSS balanced; no em/en dash
- [ ] Optional second pass for per-widget dark internals
