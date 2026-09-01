# Grapheme Cluster Boundary Detection with UAX 29

Users think in characters, but strings are sequences of code points, and code points do not map one-to-one onto what people perceive: a flag emoji is two code points, an accented letter can be one composed code point or a base plus combining mark, and Devanagari conjuncts, Korean syllable blocks, and skin-toned emoji are multi-code-point sequences. Unicode Standard Annex #29 defines grapheme clusters — the approximate "user-perceived character" units — and its boundary rules power cursor movement, selection, truncation, and string-length displays. Getting boundaries wrong produces cursors that split emoji, backspace that deletes half a character, and counters that lie. This article covers extended grapheme cluster boundaries, the rules that matter in practice, and engineering practices for correct segmentation.

## Scope

This article addresses extended grapheme cluster boundary segmentation as specified in UAX #29 (Unicode Text Segmentation): the GB rules, cluster categories (CR, LF, Control, Extend, ZWJ, Regional_Indicator, Prepend, SpacingMark, L/V/T/H hangul jamo classes), and API usage in ICU and modern platforms. It covers validation and common defects in editing surfaces and text measurement. It does not cover word or sentence segmentation, line breaking (UAX #14), or tailorings beyond the standard.

## Workflow or implementation guidance

An extended grapheme cluster is a sequence of code points between boundary positions. The GB rule set can be summarized operationally: a boundary exists between two code points unless a rule joins them. The load-bearing rules in practice are:

- **GB3/GB4/GB5** keep CR LF together and put boundaries around controls.
- **GB6-GB8** join Hangul jamo sequences (L+V, LV+T, etc.) so Korean syllable blocks composed of multiple jamo act as one cluster.
- **GB9** joins Extend characters (combining marks, variation selectors) to the preceding base.
- **GB9a** joins SpacingMark (many vowel signs in Indic scripts that occupy visual space).
- **GB9b** keeps Prepend characters (some formatting and Arabic number-sign-like marks) attached to what follows.
- **GB11** joins emoji ZWJ sequences: `Extended_Pictographic ZWJ × Extended_Pictographic`, so family emoji and skin-tone compounds stay whole.
- **GB12/GB13** pair regional indicators so two RIs form one flag and a run of RIs alternates boundary/no-boundary — this is why `🇺🇸🇬🇧` is two flags, not one monster or four letters.
- **GB999** puts a boundary between anything else.

Implementation guidance:

1. Never compute "length in characters" as code points. A reply-count limit of "280 characters" implemented over code points lets users send what displays as 140 emoji, and one implemented over UTF-16 code units silently halves emoji-heavy CJK-adjacent text; implement limits over grapheme clusters, or better, bytes with cluster-aware truncation.
2. Use a compliant segmentation library as the single source of boundaries: ICU's `BreakIterator` with the character (grapheme) kind, or the platform equivalent (`Intl.Segmenter` with `granularity: 'grapheme'` in JavaScript, `str.graphemeClusters` tooling in Swift which uses native grapheme semantics, grapheme cluster handling in Rust's `unicode-segmentation`).
3. For cursor movement and selection, iterate cluster boundaries; for backspace deletion, delete from the cursor back to the previous boundary. A text editor that deletes single UTF-16 code units leaves orphaned surrogates and combining marks.
4. Truncation with ellipsis must cut at a boundary: find the boundary position ≤ target length, then append the ellipsis. Cutting mid-cluster produces tofu boxes and broken emoji at exactly the visible places QA tends to miss (long emoji names, Zalgo-style decorated text).
5. When measuring text width, measure per cluster with shaping; cluster count is a proxy for complexity, not pixel width (Hangul clusters are wide; combining marks add zero width).
6. Handle CRLF explicitly: GB3 keeps CR followed by LF as one cluster; treating them as two clusters makes delete-key behavior inconsistent across platforms.

A worked example: the string "👩🏽‍🚀" (woman astronaut with medium skin tone) is several code points — base pictographic, skin-tone modifier (Extend-class), ZWJ, another pictographic — and forms exactly one cluster under GB11 + GB9. `"🇺🇸🇬🇧"` contains four regional indicators forming two clusters. `"é"` is one cluster whether stored as U+00E9 or as `e` + U+0301. `"가"` composed of jamo L+V is one cluster. Each of these makes a good table-driven test.

Version pinning matters: the Extend/ZWJ/Regional_Indicator property assignments come from the Unicode character database of a specific Unicode version; emoji additions (new ZWJ sequences) change clustering between versions. Pin the Unicode version of your segmentation library the way you pin other data dependencies.

## Controls

- Centralize boundary computation in one library and forbid ad hoc `char` loops in editing code via review checklist.
- Property-test round trips: segment → rejoin clusters → assert byte-identical original; and assert every cluster is non-empty.
- Table-test the known hard cases: ZWJ emoji with skin tones, flag pairs and odd RI runs (`🇺🇸🇬` must yield two clusters, with the last single RI standing alone), Hangul jamo sequences, Indic SpacingMark conjuncts, CRLF, Prepend marks, and decomposed versus composed accents.
- Pin the Unicode version of the segmentation dependency and re-run the table tests on upgrade; changelog any cluster-count changes because they are user-visible (counter changes, cache invalidation).
- For input validation limits, enforce on cluster count and give feedback in the same units the UI displays.

## Validation evidence

- The GB rules, cluster categories, and conformance requirements are specified in UAX #29: Unicode Text Segmentation, published by the Unicode Consortium.
- ICU implements character-boundary segmentation per UAX #29 and exposes it via `BreakIterator`; the ICU User Guide documents its use.
- A reproducible check: segment `"🇺🇸🇬🇧"` with a compliant library and assert exactly two clusters; segment `"👩🏽‍🚀"` and assert one; segment `"e\u0301"` and assert one — three assertions that catch the most common non-compliant implementations.

## Failure modes and correction

- **UTF-16 code-unit counting.** Symptom: emoji count as 2, astral characters truncate into tofu. Correct by cluster-based counting.
- **Splitting on code points.** Symptom: cursors stop inside emoji and combining sequences; backspace needs multiple presses. Correct by boundary-aware cursor logic.
- **Truncation mid-cluster.** Symptom: trailing garbage glyph after ellipsis. Correct by cutting at the boundary ≤ limit.
- **Odd regional-indicator runs mishandled.** Symptom: three-flag strings render flags incorrectly. Correct by relying on GB12/GB13 pairing rather than regex `RI{2}` matching, which mispairs odd runs.
- **Stale Unicode data.** Symptom: newly added emoji split apart after an OS update but not in CI. Correct by pinning the library's Unicode version and testing with sequences from that version.

## Limitations

- Grapheme clusters approximate user perception; some scripts (notably some Indic conjunct behavior) still split clusters users perceive as single glyphs, and font rendering can differ from segmentation.
- Cluster segmentation is not a line-break, word-boundary, or spelling-unit mechanism; those need UAX #14 or tailorings.
- Locale tailorings to grapheme rules are not provided by UAX #29; the rules are language-agnostic by design.
- Performance on very long strings requires streaming segmentation rather than materializing all clusters.

## Canonical sources

- Unicode Consortium, UAX #29: Unicode Text Segmentation: https://unicode.org/reports/tr29/
- Unicode, ICU User Guide (BreakIterator and segmentation): https://icu.unicode.org/
