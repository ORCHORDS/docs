# multilingual-font-loading-subsetting

**Issue:** A product that ships a dozen locales cannot treat web fonts as a solved problem. A full CJK font runs 5-20 MB, Arabic and Indic scripts need shaping-capable families that dwarf a Latin subset, and a naive font setup either forces every user to download every script's typeface or lets glyphs fall through to tofu boxes when no loaded face covers them. Current best practice — validated by web.dev guidance and multiple 2024-2025 performance case studies — combines per-script subsetting with unicode-range descriptors so the browser lazily downloads only the slices a page actually renders, plus metric-matched fallbacks to keep layout stable while fonts arrive. This is an i18n concern as much as a performance one: the wrong font strategy makes non-Latin locales measurably slower and visually broken.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Why fonts dominate multilingual performance

1. **Non-Latin fonts are orders of magnitude larger.** A Latin text face with a few hundred glyphs compresses to 20-60 KB; a single weight of a pan-CJK font contains tens of thousands of glyphs. Loading the full family for a Japanese locale can outweigh the entire JavaScript bundle, directly damaging LCP on mid-range phones and slow networks — the typical device for several high-growth locales.
2. **Every extra script multiplies the family count.** A multilingual UI often needs body, heading, and mono faces per script. Without subsetting, locale count scales font payload linearly even though each user reads one script. Subsetting decouples shipped bytes from supported locales.
3. **Fallback tofu is a correctness bug, not a cosmetic one.** When a character has no glyph in any loaded or system face, users see empty boxes (tofu) — often in proper nouns, numbers entered in native digits, or user-generated content that mixes scripts. A font strategy must assume mixed-script pages, because user content is never monolingual.

## Subsetting and unicode-range strategy

1. **Split fonts by script with unicode-range.** Declare multiple @font-face rules for one family, each with a unicode-range covering a script block (Latin, Cyrillic, Greek, Arabic, Devanagari, CJK subsets). The browser downloads a slice only when the page actually renders a character inside its range. This is the pattern Google Fonts serves by default, and web.dev's font best-practices guide treats it as the baseline technique.
2. **Subset with fonttools at build time.** pyftsubset (from the Python fonttools package) produces the slices: give it a code-point set (a script range from the Unicode data files, or — better when the locale set is fixed — the actual characters harvested from your translation catalogs) and it emits a minimized font with hinting and layout tables pruned. The CSS-Tricks pyftsubset workflow and the loveholidays engineering writeup both document measurable LCP wins from exactly this pipeline.
3. **Prefer content-driven subsets for fixed locale bundles.** When the server already knows the locale, harvest every character from the compiled translation JSON at build time and generate one subset per locale per family. This is strictly smaller than script-range splitting and avoids ever downloading glyphs for languages the current user cannot see.
4. **Beware over-fragmentation.** Splitting into too many tiny unicode-range slices causes many small requests, repeated decompression, and worse behavior on high-latency links; the modern-fonts deep-dive literature flags this failure mode explicitly. In practice 4-12 slices per family is the sweet spot; do not slice per code-point block.
5. **Keep variable fonts for Latin, not for CJK.** A variable Latin font collapses several weights into one file and pairs well with a unicode-range strategy. Variable CJK fonts are enormous and rarely worth it; serve CJK weights as separate subsets instead.

## Fallback stacks and tofu prevention

1. **Build per-script fallback stacks, not one global list.** Order fonts per script family so a missing glyph rolls to the next face covering that script before hitting a generic: font-family: BrandLatin, BrandCyrillic, BrandArabic, then system CJK stacks like Hiragino, NanumGothic, Microsoft YaHei, Noto. The last-resort entries should be system fonts that ship with the OS, which is what keeps user-generated mixed-script content tofu-free.
2. **Use lang-aware font selection.** Set the lang attribute on document and locale containers. Browsers and CSS font matching can then pick per-language faces, and you can scope fonts with :lang(ja) so Japanese gets a Japanese-optimized face while Chinese gets Han-specific glyphs — critical because Han unification means one code point should render with different regional forms.
3. **Verify Noto coverage as the safety net.** For any script your brand faces do not cover, confirm a Noto family exists for it and either load it lazily via unicode-range or rely on the OS stack. Maintain a checklist mapping each supported locale to its shipped faces and the fallback for the rest.

## Metric-matched fallbacks and layout stability

1. **Use size-adjust and ascent-override on fallback faces.** An oversized system fallback swapping to the brand font shifts every line and wrecks CLS on slow connections. Define a fallback @font-face with size-adjust, ascent-override, and descent-override tuned so its metrics approximate the web font; this is standard practice in current performance guidance and cuts font-swap layout shift dramatically.
2. **Choose font-display per role and script.** font-display: swap is fine for Latin text that renders acceptably in system fonts; font-display: optional avoids the swap flash entirely for below-the-fold CJK where a 5 MB late swap would reflow the page. Make the choice per script and per viewport role, not globally.
3. **Preload only the primary locale subset.** Preload the one or two slices the initial viewport needs (the Latin-or-primary-script body face). Preloading all slices reintroduces the megabyte problem on every navigation and competes with LCP resources.

## Operational checks

1. **Measure per locale, not aggregate.** Track font bytes, LCP, and CLS broken down by locale in the field (web-vitals attribution). A font regression that only affects fa-IR or ja-JP users is invisible in global dashboards.
2. **Add a tofu detector to visual testing.** In Playwright smoke tests per locale, render a mixed-script sample page and assert no .notdef glyph boxes appear — checking that every supported script resolves through the shipped or fallback stack. Screenshot evidence per script is the acceptance criterion, per the workspace testing rules.
3. **Audit subsets when translation catalogs change.** New strings can introduce code points outside the harvested subset, silently producing tofu in production. Regenerate content-driven subsets in CI whenever translation files change, and fail the build if a catalog character falls outside every declared unicode-range.
4. **License and hash the subsets.** Record the source font version and subsetting command per emitted file so slices are reproducible; OFL-licensed faces allow subsetting, but some commercial licenses restrict modification — verify before slicing brand type.
