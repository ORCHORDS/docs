# Hebrew Right-to-Left Number Placement

Hebrew text runs right to left, yet the numbers embedded in it — amounts, dates, phone numbers — are written left to right as in every other language. The bidi algorithm handles most of this automatically, but number placement in Hebrew has specific conventions and specific failure modes: surrounding text reflows around the number, signs and separators detach, parentheses flip, and mixed Latin fragments inside Hebrew sentences scramble without careful handling. This article covers the bidi model for numbers in Hebrew, the placement conventions, and the engineering practices that keep Hebrew interfaces readable.

## Scope

This article addresses bidirectional text handling as specified in UAX #9 (Unicode Bidirectional Algorithm) as it applies to numeric runs in Hebrew text: the European Number (EN) and Common Number Separator (CS) classes, implicit levels, signs, percentages, currency, phone numbers, and embedded Latin or RTL segments. It covers HTML/CSS and string-level mitigations. It does not cover full layout mirroring, Arabic-specific shaping, or keyboard input methods.

## Workflow or implementation guidance

Under the bidi algorithm, Hebrew letters are strong right-to-left (class R). Digits are weak: European digits are EN. The resolving algorithm gives an EN inside an RTL paragraph an embedding level that keeps the digit run left-to-right internally while the surrounding Hebrew flows right to left. This works for the common case. The failures cluster in the seams:

- **Signs and adjacent weak characters.** A minus sign (ES class when used as minus) or a range dash between two numbers participates in number context differently than expected; `מ-5 עד 10` (from 5 to 10) usually resolves acceptably, but `-5` at the start of a logical Hebrew run can render as `5-` because the minus attaches visually to the wrong side. The standard fix is to use the true minus character (U+2212) or wrap the signed number in an isolate.
- **Parentheses and other paired brackets.** Brackets are mirrored neutrals; a phone number in parentheses at the end of a Hebrew sentence can close on the wrong side. Isolates fix this reliably.
- **Currency symbols.** A `$` or `₪` adjacent to digits is a neutral/ET character; its visual side depends on resolution. Hebrew convention places the currency symbol before the number when reading (which is to the right of the number visually in RTL flow) — but only the formatter's data should decide; hand-templating produces mirrored results.
- **Percentages.** The `%` is ET; `50%` usually holds together, but `50% הנחה` at a sentence edge may detach the sign. Test at boundaries.
- **Dates and hyphenated ranges.** `2026-09-11` is digits and hyphens; the hyphen between digits is CS only between same-type numbers, otherwise neutral. ISO dates inside Hebrew generally render intact, but ranges like `11-12` can flip to read as `12-11`, reversing the intended span.

The robust engineering pattern is isolates, not reordering:

1. Treat every formatted number, date, currency amount, and phone number as an atomic left-to-right unit when embedding it into Hebrew strings. Wrap it in Unicode directional isolates: FSI (U+2068) … PDI (U+2069), or LRI (U+2066) … PDI when the content is known LTR. The isolate makes the enclosed run's direction independent of the surrounding RTL context and prevents the number from interacting with adjacent neutrals.
2. In markup, prefer the HTML `dir` attribute on a wrapping element (`<span dir="ltr">…</span>` or `dir="auto"` for user-generated content) over injected control characters when the string will never leave the DOM; use Unicode controls only where plain text is required (emails, push notifications, log lines).
3. Compose sentences from segments with known direction; let translators place placeholders and wrap them with isolates in the translation file itself (`‏{amount}‎` style markers with isolates in the source string), rather than post-processing the translated string in code.
4. For phone numbers, keep the plus prefix inside the isolated unit (`+972-2-1234567` as one LTR island); otherwise the `+` can visually detach to the right of the digits.
5. For lists of numbers in Hebrew tables, set column direction explicitly (`dir="ltr"` on numeric columns or CSS `direction: ltr; unicode-bidi: isolate;`) so alignment and separators stay sane while headers remain RTL.
6. Never "fix" display by reversing strings. Reversal corrupts the logical order, breaks copy-paste, search, screen readers, and any later re-rendering under a different algorithm version.

A worked example: the Hebrew sentence `שלמת 250 ₪ ב-11 בספטמבר` ("you paid 250 ILS on September 11") renders correctly from the data, but the template `{date} בשעה {time}` with a naive substitution can place the date at the wrong visual end. Wrapping each placeholder as an isolated LTR unit keeps the sentence's visual order faithful to the logical Hebrew while each number reads naturally left to right.

Test fixtures should include: sentence-initial and sentence-final numbers, signed amounts, parenthesized phone numbers, currency amounts with symbol and code (`₪` versus `ILS`), date ranges with en dash, percentages at clause edges, and copy-paste round trips from rendered output back into plain text.

## Controls

- Mandate isolates or explicit direction markup for every interpolated numeric placeholder in localized strings; lint translation catalogs for placeholders not wrapped in isolates or `dir`-carrying markup.
- Render screenshots in RTL QA for all money, date, and phone surfaces; textual assertions alone do not catch visual misplacement.
- Prefer Unicode isolates (LRI/PDI, FSI/PDI) over legacy embedding controls (LRE/RLE/PDF) in new strings; isolates nest cleanly and are ignored safely by older renderers.
- Keep ICU/CLDR and browser versions pinned or tracked in CI so bidi class changes (rare, but real, e.g., new characters gaining classes) surface in review rather than production.
- Validate that screen-reader output of isolated numbers matches the intended reading order, since assistive technology consumes logical order.

## Validation evidence

- Directional classes, the resolving algorithm, isolate characters (FSI, LRI, PDI), and mirroring rules are specified in UAX #9: Unicode Bidirectional Algorithm, published by the Unicode Consortium.
- HTML's `dir` attribute and the CSS `unicode-bidi`/`direction` properties implement the embedding and isolation model at the markup level, as specified in WHATWG HTML and CSS Writing Modes.
- A reproducible check: place `‎-5%‎`-style signed percentage at both ends of a Hebrew test sentence with and without isolates and compare rendered order; the unisolated variant at the edge flips sign placement in conforming renderers — demonstrating the failure mode is algorithmic, not a rendering bug.

## Failure modes and correction

- **Detached signs.** Symptom: minus or percent visually on the wrong side of the number at sentence edges. Correct by isolating the whole signed value.
- **Flipped ranges.** Symptom: `11-12` reads as `12-11` so the stated period reverses. Correct by isolating the range or using a non-breaking hyphen inside the unit.
- **Parenthesis mirroring surprises.** Symptom: phone number in parentheses closes against the sentence instead of the number. Correct by including parentheses inside the isolated run.
- **Manual reversal.** Symptom: text looks right but copies, searches, and screen-reads wrong. Correct by removing reversal logic and using isolates.
- **Post-translation string surgery.** Symptom: one locale fixed, others broken by generic wrapping logic. Correct by putting isolation markers in the source strings per placeholder.

## Limitations

- Renderers outside your control (old terminals, some email clients) may ignore isolates; degrade gracefully by keeping critical numbers in separate lines or fields.
- Bidi is display order, not memory order; persistence and search operate on logical text and must never store visually reordered strings.
- Numbers in Arabic-script contexts (including Arabic digits) follow related but distinct conventions; do not assume Hebrew fixes generalize.
- Complex legal or financial formatting may follow house style overriding algorithmic defaults.

## Canonical sources

- Unicode Consortium, UAX #9: Unicode Bidirectional Algorithm: https://unicode.org/reports/tr9/
- Unicode Consortium, UTS #35 (LDML) — number and currency formatting data that governs symbol placement: https://unicode.org/reports/tr35/
