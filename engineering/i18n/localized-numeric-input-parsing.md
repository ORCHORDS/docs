# localized-numeric-input-parsing

**Issue:** Formatting numbers for display is a solved problem — Intl.NumberFormat handles it. Parsing numbers that users typed is not. When the UI locale is Arabic, a user entering a price types ١٢٣٤٫٥٠ using Arabic-Indic digits and the Arabic decimal separator; a Persian user types ۱۲۳۴/۵۰ with Extended Arabic-Indic digits; a French user types 1 234,50 with a comma decimal and a space group separator. JavaScript's Number(), parseInt(), and parseFloat() accept only ASCII digits and the ASCII dot, so every one of those inputs becomes NaN or, worse, a silently wrong value (parseInt("1.234,50") in a de-DE mindset yields 1.234 — a thousand-fold error if treated as units). The engineering problem is the reverse direction of formatting: converting locale-formatted user input, with any of Unicode's sixty-plus decimal digit shapes and locale-specific separators, into the canonical number your domain layer stores — and guaranteeing the round trip back through formatting looks stable to the user.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Why parsing fails before it starts

1. **Native parsers are ASCII-only.** Number, parseInt, and parseFloat reject every non-ASCII digit: the Arabic-Indic block U+0660-0669, Extended Arabic-Indic (Persian/Urdu) U+06F0-06F9, Devanagari U+0966-096F, fullwidth U+FF10-FF19, and the rest of Unicode's Nd category. There is no platform-level parseLocaleNumber; you build it.
2. **input type="number" makes it worse, not better.** Browsers vary in whether they accept non-ASCII digits in number inputs, and form validation frequently rejects or coerces them. For localized numeric entry use input type="text" with inputmode="decimal" so the numeric keypad appears while the value stays a locale-formatted string you control. Remember some UI libraries have no non-Latin digit support at all (the flatpickr date-picker discussions document this gap) — audit every input component.
3. **Mobile keyboards betray the locale.** Users in ar or fa locales frequently report that their keyboard emits Western digits even though the display format uses Eastern digits — or the reverse after an OS update. Real-world input is mixed-script by the time it reaches you, so parsing must accept both digit shapes simultaneously, not just the nominally correct one for the locale.
4. **Grouping and decimal symbols collide across locales.** A dot is a decimal separator in en-US but a group separator in de-DE; the Arabic locales use U+066C (ARABIC THOUSANDS SEPARATOR) and U+066B (ARABIC DECIMAL SEPARATOR), while some Arabic users type the ASCII dot and comma anyway. fr-FR uses a narrow no-break space for grouping, which is not the character a user's spacebar produces — inputs arrive with regular spaces, non-breaking spaces, or narrow no-break spaces unpredictably.

## Digit-shape normalization

1. **Map every Nd digit to ASCII by code-point arithmetic.** For the common blocks, subtracting the block's zero code point yields the value: ١٢٣ (U+0661-0663) minus U+0660 gives 123; the same trick works for U+06F0, U+0966, U+0E50 (Thai), and U+FF10 blocks. A translate pass over the string handles all of them in one pass without a 60-entry lookup table.
2. **Or normalize with a regex property escape.** The Unicode property escape /\p{Nd}/u (covered in the existing regex-property-escapes article) identifies digit characters generally, and String.prototype.normalize("NFC") first collapses composed lookalikes so identical-looking inputs compare equal before mapping.
3. **Decide your canonical form and write it down.** The recommended pattern: store the canonical decimal string (ASCII digits, dot decimal, no grouping) as the single source of truth in state, and treat the user-visible field as a formatted projection of it. Parsing happens once, on change; formatting happens on blur. This is the architecture behind every reliable localized input.
4. **Never parse partially on every keystroke with side effects.** While the user types 1.234,50 the intermediate strings are ambiguous in half the locales. Validate shape progressively if you must show inline errors, but only commit the parsed value on blur or submit, when the string is complete.

## Separator-aware parsing

1. **Reverse Intl.NumberFormat.formatToParts instead of guessing.** Current best practice (documented in the randombits.dev locale-parsing guide and Mike Bostock's Observable notebook on localized number parsing) is to ask Intl.NumberFormat for the locale's parts, learn which symbols play group and decimal roles, then strip groups and swap the decimal to a dot before calling Number. This stays correct as CLDR updates separators instead of hard-coding them.
2. **Strip whitespace variants before processing.** Normalize all Unicode space characters (U+0020, U+00A0, U+202F narrow no-break space) when the locale groups with spaces; forgetting the narrow no-break space is the classic fr-FR bug because copy-pasted French numbers carry it invisibly.
3. **Validate shape after normalization, not before.** After digit mapping and separator handling the string should match /^-?\d+(\.\d+)?$/; if it does not, the input is genuinely malformed and you can show a locale-correct error. Validating the raw string with an ASCII regex produces false errors for perfectly valid Arabic or Devanagari input — the most-reported symptom of this whole bug class.
4. **Handle the trailing-separator state.** An in-progress 1234, (German) must not be coerced to 1234 or NaN mid-typing; if you validate progressively, allow a dangling decimal separator as a transient state and only reject it on commit.

## Round-trip guarantees and display formatting

1. **Assert format(parse(x)) equals x in tests.** For each locale, generate formatted samples (integers, decimals, grouped thousands, negatives, and the locale's minus sign — some locales use U+2212 or trailing minus), parse them, and re-format. Any mismatch is a round-trip bug the user will see as their input changing under them.
2. **Re-format on blur with the same locale and options.** The displayed grouping and digit shape must come from the same Intl.NumberFormat configuration used for parsing decisions; mixing a parse with one locale and display with another is how ١٢٣ turns into 123 on the next paint.
3. **Keep currency separate from the number.** Parse the numeric field; keep currency as a separate control. Users type 12,50 and pick EUR — parsing 12,50 € merges symbols into the numeric grammar and doubles your separator edge cases for no benefit.
4. **Respect digit-shape overrides.** A -u-nu- extension or user setting can force Latin digits in an ar locale (or Eastern digits in an en locale). The formatter decides what users see; the parser should still accept what the formatter produces plus whatever their keyboard emits, which is why parsing tolerates both digit sets regardless of display settings.

## Edge cases and test discipline

1. **Fuzz with the full Unicode digit inventory.** Generate test inputs from every Nd block, mixed-digit strings (١2٣4), separators from ten different locales, empty strings, lone separators, double separators, and maximal-length strings. Known outputs for each pin the parser against regressions.
2. **Test boundary magnitudes per locale.** Values crossing the grouping threshold (999 to 1,000 to 1,234,567), negative zero, exponents (most locale grammars should reject 1e3 — decide and test), and numbers beyond Number.MAX_SAFE_INTEGER belong in the suite with explicit expectations.
3. **Verify on real devices with native keyboards.** Emulator Latin keyboards cannot reproduce what a Samsung keyboard with an ar-EG locale emits; per the workspace mobile testing rules, capture the exact code points a real device produces with a small echo endpoint or logging before freezing the parser's accepted grammar.
4. **Instrument parse failures in production.** Log (locale, code points, result) tuples — never raw values — for parse failures, and review them monthly. The gap between your accepted grammar and real user input is only visible in that data, and it is how the ar-mixed-keyboard cases were originally discovered.
