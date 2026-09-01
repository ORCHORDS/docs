# Arabic Digit Shaping Arabic Indic Numerals

Number rendering in Arabic breaks when the pipeline assumes the digits U+0030 through U+0039 are the only digits that exist. Arabic-Indic digits are a distinct Unicode block (U+0660 to U+0669) plus the Extended Arabic-Indic set (U+06F0 to U+06F9) used by Persian, Urdu, and Pashto. Arabic-Indic digits have strong AL (Arabic letter) bidirectional behavior, not EN (European number), which changes how they participate in bidi resolution inside RTL runs. They also carry no compatibility decomposition, so normalization to NFC, NFD, NFKC, or NFKD never converts an Arabic-Indic digit to or from its ASCII counterpart. Digit identity is therefore a locale, numbering system, and shaping decision that must be made explicitly at format time, not something text normalization will fix later.

## Scope

Covers selecting, storing, and round-tripping Arabic-Indic numerals in Arabic-Indic and Extended Arabic-Indic numbering systems, controlling digit identity in `Intl.NumberFormat`, persisting digit variants in storage and identifiers, and reordering digits within RTL text with correct bidi isolation. Applies to product surfaces that format counts, prices, dates, and identifiers for `ar`, `ar-SA`, `ar-EG`, `ps`, `ur`, `fa`, and `ckb` locale users. Out of scope: numeric value transliteration of free-form user input beyond normalization into a canonical internal form, Arabic ligature and contextual joining of letters (a separate shaping concern), and calendar or month name localization.

## Workflow or implementation guidance

Decide once, at the edge, which form a number takes in each layer of the system. Internally store numeric values as numbers or as ASCII-digit strings; render locale digits only at presentation time. In JavaScript, force the numbering system with the `nu` keyword of the Unicode locale extension: `new Intl.NumberFormat('ar-EG-u-nu-arab', ...)` yields U+0660 digits, while `ar-EG-u-nu-latn` forces ASCII digits inside an otherwise Arabic locale, which many Arabic products prefer for prices or SKU-heavy screens. Never pass the numeral string through a normalize step expecting a transformation: `'٣'.normalize('NFKC')` is still U+0663. To convert forms, map digit code points explicitly, 0x0660 to 0x0639 offsets against 0x0030, or use a numbering-system-aware formatter in ICU (`unum` with a ` numberingSystem` attribute, or `NumberingSystem.getInstanceByName("arab")` in ICU4J).

When Arabic-Indic digits travel through bidi text, they are typed AL and are reordered with the surrounding RTL run, so the visual order of a number inside an Arabic sentence is stable even though a stray ASCII digit is EN and gets different treatment around separators. Wrap interpolated numbers in their own bidi isolate (`\u2066` LRI or `\u2067` RLI plus PDI, or `Intl.Segmenter`-adjacent formatting wrappers) when a locale-formatted number is injected into markup, so a trailing slash, percent, or minus sign cannot jump to the wrong side of the run. The minus and percent signs are the classic casualties: `-٣` in an RTL context can render with the sign on the right of the digit unless the whole numeric expression is isolated. For storage keys and API identifiers, reject non-ASCII digits at the boundary (a small allowlist of `0-9` plus the decimal separator) and translate user-typed Arabic-Indic digits to ASCII on input, because database collations, URL encoders, and hash functions are digit-form sensitive and silently mismatch.

Also verify the zero. U+0660 is ARABIC-INDIC DIGIT ZERO, not U+0640 ARABIC TATWEEL, which is a horizontal joining stroke and appears in badly converted strings when an off-by-one mapping table is used. Include the digit set in your test corpus: all ten Arabic-Indic digits, the decimal separator U+066B (ARABIC DECIMAL SEPARATOR) and thousands separator U+066C (ARABIC THOUSANDS SEPARATOR), which are the locale-correct separators in fully Arabic-Indic formatted numbers.

## Controls

- Resolve the numbering system from the resolved locale after formatting, via `resolvedOptions().numberingSystem`, and assert it equals the intended `arab`, `arabext`, or `latn` in tests.
- Store numeric data in ASCII digits or binary numeric types; treat Arabic-Indic renderings as presentation-only output that can be regenerated from the value.
- Map user-supplied Arabic-Indic and Extended Arabic-Indic digits to ASCII at input boundaries before validation, hashing, or lookup.
- Wrap formatted numerals in bidi isolates when embedding into mixed-direction markup; never rely on the ambient paragraph direction to place the sign.
- Pin the ICU or CLDR build backing the formatter, because the default numbering system per locale (for example `ar` defaulting to `arab` versus `ar-MA` leaning `latn`) is CLDR data, not code.
- Include U+0660 to U+0669, U+06F0 to U+06F9, U+066B, and U+066C in the rendering test corpus and in font coverage checks.

## Validation evidence

Verified by rendering a fixed numeric corpus across target locales and asserting code-point-level output. With `Intl.NumberFormat('ar-EG-u-nu-arab').format(12345.67)` the result contains U+0661, U+0662, U+0663 and the Arabic decimal separator rather than ASCII; with `ar-EG-u-nu-latn` the same value yields ASCII digits. `'\u0663'.normalize('NFKC') === '\u0663'` confirms no compatibility mapping exists, and a byte comparison of NFC and NFD forms of a string of Arabic-Indic digits shows identity. Bidi behavior was checked by asserting the direction of the rendered fragment inside an RTL paragraph using `getBBoxes`-style rendering tests in a browser harness; isolated and unisolated minus-sign placements differ as expected under UBA rules for AL versus EN classes. Default numbering system per locale was confirmed against CLDR numbering system data in the CLDR release pinned by the runtime.

## Failure modes and correction

Wrong digits entirely (ASCII in Arabic UI or Arabic-Indic digits in a `latn` context): the locale identifier lost its `nu` keyword during negotiation or persistence; store the full tag and re-read `resolvedOptions()`. Minus sign or percent flipping sides of the number in RTL: the numeric expression is not direction-isolated; add LRI/RLI/PDI or wrap in an element with the correct `dir`. Lookups failing for numbers typed with an Arabic keyboard: input digits were persisted unconverted; add a digit-normalization pass at the API boundary and backfill stored data with the same mapping. Tatweel appearing where zeros belong: a hand-rolled conversion table with an off-by-one offset; replace with explicit code-point arithmetic or ICU numbering system conversion and add a regression test containing zero. Mixed digit forms inside one number after concatenation of translated fragments: stop concatenating formatted fragments; format the complete numeric expression in one call so separators stay consistent.

## Limitations

Digit choice is only one axis of Arabic numeric presentation; grouping size, sign position, and currency symbol placement are separate CLDR patterns that this article does not cover in full. Native review is still required to confirm that a forced `latn` numbering system is acceptable for a given product surface, because preferences differ by region and domain. The bidi treatment here addresses numbers specifically; full UBA behavior for parentheses, hyphens, and embedded Latin words is out of scope.

## Canonical sources

- Unicode Standard, Arabic block chart including Arabic-Indic digits and separators: https://www.unicode.org/charts/PDF/U0600.pdf
- Unicode CLDR LDML Part 3: Numbers, numbering systems and locale digit defaults: https://unicode.org/reports/tr35/tr35-numbers.html
- Unicode Standard Annex 9, Unicode Bidirectional Algorithm, bidi class values including AL: https://unicode.org/reports/tr9/#Table_Bidi_Class_Values
