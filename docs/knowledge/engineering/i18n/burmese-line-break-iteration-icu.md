# Burmese Line Break Iteration ICU

Myanmar script (Burmese) defeats naive line breaking. The script is an abugida written with no spaces between words; word boundaries are carried by segmentation that Unicode's default line breaking (UAX 14) does not perform, because UAX 14 class-based rules allow breaks between syllable-like units but the meaningful unit in Burmese is the syllable cluster, and the dictionary-based segmentation that finds real word boundaries is a locale-specific resource in ICU. On top of that, Burmese text stacks combining marks (vowels above and below, tone marks, the killer dot) and uses U+200B ZERO WIDTH SPACE and other ZW characters as explicit break hints that users and input methods insert idiosyncratically. Any pipeline that truncates by code units, breaks on ASCII spaces, or applies a Latin-centric hyphenation heuristic will produce Burmese output that is either one unbreakable ribbon or severed in the middle of a stacked consonant cluster.

## Scope

Covers line break and word segmentation for Myanmar-script text using ICU, the interaction of UAX 14 classes with Burmese combining sequences, dictionary-based segmentation in `icu::BreakIterator`, the role of zero-width space in user-authored break hints, and safe truncation or ellipsis insertion for Burmese strings in feeds, cards, and log previews. Applies to server-side ICU (ICU4C, ICU4J), the `Intl.Segmenter` API where a line-break granularity with locale data is available, and CSS line wrapping policy for Myanmar text. Out of scope: Burmese numeral formatting and locale data (`my` number and date patterns), font shaping of Myanmar stacked clusters (a harfbuzz concern), and non-Burmese minority scripts of Myanmar beyond noting their distinct segmentation needs.

## Workflow or implementation guidance

Choose the iterator by what you actually need. For line wrapping, use a line break iterator (`BreakIterator.createLineInstance` in ICU4J, `ubrk_open(UBRK_LINE, ...)` in ICU4C) with the `my` locale, and let ICU's tailoring decide where Myanmar breaks are legal. For extracting words (search indexing, keyword highlighting, spell-adjacent features), use a word iterator with the `my` locale; ICU's dictionary segmentation for Myanmar identifies word boundaries using dictionary data shipped with the ICU build, and the results differ substantially from the line iterator's output. Do not substitute grapheme segmentation for word segmentation; grapheme clusters in Burmese are roughly consonant-plus-stack units and are finer than words.

Second, treat combining marks as unbreakable cargo. Myanmar vowel signs (U+102C and following), anusvara, dot below, and the visarga carry combining class information; a break placed between a base consonant and its dependent vowel sign destroys rendering, because the mark can no longer attach. When post-processing ICU's break positions, always re-verify that the position after a proposed break is not a combining mark, a virama, or an asat sequence. A defensive rule: never break before any code point with a non-zero canonical combining class, and never break inside a grapheme cluster produced by UAX 29 rules for the same string.

Third, honor and sanitize zero-width space. Burmese users and IMEs insert U+200B to mark word boundaries. It is invisible, it influences where lines can wrap, and it silently breaks string equality and search: two visually identical strings can differ by a zero-width space. Decide per field whether ZWSP is allowed. For storage-backed search keys, strip U+200B (and U+200C, U+200D where Myanmar joining behavior is not needed) into a normalized comparison key while keeping the original for display. For display, leave it alone; it is doing work.

Fourth, truncate safely. For preview strings, run the line or word iterator, collect break offsets, and cut at the last offset before the budget; then append the locale-appropriate ellipsis. Cutting at a raw index into a Burmese string is the single most common way to ship a dangling combining mark or a torn stack. If the budget is in display columns rather than characters, measure the shaped text, not the code point count, since Myanmar stacked clusters often occupy one column while consuming several code points.

Fifth, verify ICU data coverage before shipping. Dictionary-based Myanmar segmentation is present in standard full ICU builds, but stripped-down or custom data builds (common in constrained runtimes) may lack the dictionary; detect this by checking that a known Burmese sentence segments into multiple words rather than one token, and fail loudly at startup rather than serving unsegmented output.

## Controls

- Instantiate the break iterator with locale `my` (and `my_MM` where region tailoring matters) rather than root, for both line and word granularity.
- Never emit a break immediately before a code point with a non-zero combining class; validate every candidate offset against the grapheme boundary set for the same text.
- Strip U+200B, U+200C, U+200D from search and comparison keys; retain the original string for display.
- Truncate only at iterator-supplied offsets, never raw indices; re-run the iterator after appending an ellipsis if further wrapping occurs.
- Add a startup probe asserting Myanmar dictionary segmentation loads (a fixed sentence yields more than one word).
- Pin the ICU version and record it in the deployment; re-run the Burmese break corpus on ICU upgrades because dictionary and rule data evolve.

## Validation evidence

Verified by iterating a fixed Myanmar corpus through ICU break iterators and asserting offsets. A sentence containing multiple Burmese words with no ASCII spaces produced multiple word-boundary offsets under `my` word granularity and none under root where the dictionary was unavailable, confirming locale dependence. Break offsets were cross-checked against grapheme cluster boundaries computed per UAX 29 for the same string; no line break offset fell strictly inside a cluster. Truncation at various budgets never left a trailing combining mark, verified by asserting the code point after each cut position has combining class zero. Zero-width space handling was verified by showing that a string containing U+200B equals its stripped form only after stripping and differs before, and that wrapping still respects the user's ZWSP in the display copy. All behavior was observed on the ICU build recorded in the runtime environment.

## Failure modes and correction

Burmese paragraphs rendering as a single overflowing line: line iterator was built with root locale or dictionary data missing; rebuild with `my` and add the startup probe. Squared-off tofu or detached vowel signs after truncation: raw index truncation; switch to iterator offsets plus combining-class guard. Search returning no results for exact matches: ZWSP differences between stored and query text; normalize keys by stripping zero-width characters on both sides. Word highlight offsets misaligned with rendering: word segmentation computed on a normalized copy while rendering used the original; compute segmentation on the exact string being rendered. Ellipsis landing inside a stacked cluster: ellipsis appended after cutting at a non-boundary; only ever cut at boundary offsets and append the terminus after.

## Limitations

ICU's Myanmar dictionary segmentation quality varies by release and does not achieve linguistic gold-standard word segmentation on all text genres; accept it as an engineering approximation and prefer native review for user-facing truncation quality. Minority scripts of Myanmar (Shan, Mon, Karen) have thinner tailoring and may fall back to generic behavior. `Intl.Segmenter` line-break granularity availability and locale coverage differ across JavaScript engines, so engine-specific verification is required.

## Canonical sources

- Unicode Standard Annex 14, Unicode Line Breaking Algorithm, tailorable classes and rules: https://unicode.org/reports/tr14/
- ICU User Guide, boundary analysis including dictionary-based segmentation: https://unicode-org.github.io/icu/userguide/boundaryanalysis/
- Unicode Standard Annex 29, Unicode Text Segmentation, grapheme cluster boundaries used to guard break offsets: https://unicode.org/reports/tr29/
