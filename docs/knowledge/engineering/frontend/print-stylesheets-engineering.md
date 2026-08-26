# print-stylesheets-engineering

**Issue:** Users still print web pages — invoices, receipts, tickets, recipes, reports, boarding passes — and by default they get a broken artifact: sliced tables, dark-mode backgrounds that waste ink or vanish entirely, truncated URLs behind links, navbars printing as a black bar, and content that spills one line onto a second page. Print is a distinct output medium with its own layout model (paged media), unit system (pt/mm vs px), and constraints (you cannot fully control it — users choose paper size, margins, and scale, as the frontend community keeps re-learning). A print stylesheet is cheap insurance that almost no team writes until a customer prints a mangled invoice.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Foundation

1. **Start with a dedicated `@media print` block, not a separate stylesheet.** A separate print.css requires an extra request and drifts out of sync; a media block colocated with component styles gets maintained. Strip everything non-essential first: `display: none` on nav, sidebars, footers, ads, cookie banners, floating buttons.
2. **Invert dark themes to print colors.** Dark-mode UIs print as solid-ink black pages or, worse, as white text that disappears when printers drop backgrounds. In the print block, force `color: #000` on body text, `background: transparent`/`#fff` on surfaces, and borders back to visible grays. Never rely on `background-color` to convey meaning in print — user print settings commonly suppress backgrounds (`print-color-adjust: exact` can request exact rendering but is a request, not a guarantee).
3. **Switch to print-appropriate units and type.** Points (pt) and millimeters are physical; a 16px body font prints at ~12pt which is small on paper. Target 11-12pt body, generous line-height, and serif or the system default if branding allows — the screen font stack loaded as a webfont may not even be available to the print renderer.
4. **Set page geometry with `@page`.** `@page { size: A4; margin: 15mm; }` (or letter per audience) declares intent; users can override everything, so treat margins as a baseline, not a contract. `@page :first` allows a different first-page layout for letterheads.
5. **Linearize layouts.** Multi-column grids and flex rows should collapse to a single column with logical reading order: the DOM order becomes the print order, so verify that visual order via CSS grid/flex matches source order or the printed sequence reads wrong.

## Page breaks

1. **Use the modern `break-*` properties over legacy `page-break-*`.** `break-before`, `break-after`, `break-inside` are the current standard; the `page-break-*` aliases still work but the modern set composes with fragmentation logic and covers rows/columns too. `break-before: page` on each major section gives invoice-style sectioning.
2. **Protect atomic elements with `break-inside: avoid`.** Cards, table rows, figures, list items, and code blocks should not straddle pages — `break-inside: avoid` keeps them whole (Raymond Camden's 2025 print-cleanup writeup singles out tables and images as the classic victims). Apply it to rows, not giant containers: `break-inside: avoid` on a whole multi-page table is ignored and can cause worse breaks.
3. **Avoid widow/orphan lines.** `widows: 2; orphans: 2` keeps at least two lines of a paragraph on each side of a break — supported in print contexts and near-free to add.
4. **Prevent blank pages.** Stray margins, min-heights sized in viewport units (100vh sections become one printed page each plus overflow), and `<br>` spacers create mystery blank pages. Hunt these specifically: a `100vh` hero is the number-one cause of a blank page after page one.
5. **Let long tables break well.** For tables that must span pages, `thead { display: table-header-group }` repeats the header row on every page; avoid `break-inside: avoid` on the table itself and instead protect individual rows.

## Print-specific content transforms

1. **Expand link URLs inline.** Links are invisible on paper: append the href after the text (`a[href^="http"]::after { content: " (" attr(href) ")" }`), scoped to content areas only — printing every nav link's URL is noise. Abbreviate or omit for obviously-readable URLs if the design allows.
2. **Provide print-only content sparingly, via a `.print-only` utility.** Things that exist only on paper: full URLs, contact blocks, a "printed on [date]" footer (`@media screen { .print-only { display: none } }`). Do not hide large screen content with a `screen-only` class as the primary strategy — hiding-by-allowlist (only content prints) beats hiding-by-denylist (everything prints unless removed), so structure the document so the main content region can be isolated.
3. **Print QR codes for actionable artifacts.** Tickets, payment references, and return instructions become actionable again when a QR is rendered (generated server-side or canvas-to-img — canvas content does print, but draw it before the print event).
4. **Handle images for grayscale and ink.** High-contrast charts survive grayscale printing; color-coded charts do not. Add patterns/labels that do not depend on hue, and prefer `max-width: 100%` on images so they never overflow the printable width.
5. **Test the beforeprint path in JS when state matters.** If the app must expand accordions or render hidden sections before printing, listen for `beforeprint`/`matchMedia('print')` and revert on `afterprint` — but prefer pure CSS solutions first; JS print handlers race the print dialog in some browsers.

## Testing (the part everyone skips)

1. **Test in the browser print preview, not by eyeballing CSS.** Chrome/Safari/Firefox print previews render with real pagination; DevTools "Emulate CSS media: print" shows styles but not page breaks — both are needed.
2. **Test the user-override failure modes.** Print with "background graphics" off, headers/footers on, portrait instead of landscape, and A4 instead of Letter: the design must degrade rather than break, because these settings are outside your control.
3. **Save-as-PDF is the same pipeline.** Most "print" output is now PDF; the same stylesheet governs it, so a tested print path doubles as the app's PDF export for invoices and reports — no server rendering needed for simple cases.
4. **Add print styles in the same PR as the feature.** Retrofitting print support onto five years of accumulated UI is a multi-day chore; ten lines per component at birth is nearly free. Route-level check: any page a user could reasonably want on paper (order confirmations, articles, dashboards-for-export) gets its print block when it is built.
