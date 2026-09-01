# CLDR Plural Rules: Parser Mechanics, Negation, and Operand Reuse

CLDR plural rules are how a runtime decides that 1 English file is `one` but 2 files are `other`, that Polish 22 is `many` and 5 is `few`, and that 1.5 is `other` almost everywhere except a handful of languages. The rules are small boolean expressions over the operands `n`, `i`, `v`, `w`, `f`, `t`, and `c`/`e`, and every plural-aware formatter either embeds a CLDR rule compiler or hand-copies its logic — and hand-copies rot. This article covers operand semantics, the rule grammar, decimal/negation edge cases, and the operand-reuse pitfalls that produce wrong plural forms.

## Scope

This article addresses CLDR cardinal and ordinal plural rule syntax as specified in UTS #35: operand definitions (`n` absolute value, `i` integer digits, `v` fraction digit count, `w` fraction digits without trailing zeros, `f` fraction digits as integer, `t` `f` without trailing zeros, `c`/`e` compact exponent), the rule grammar (`and`/`or`, `=`, `!=`, `..` ranges, `mod`), and decimal/negative operand handling. It covers implementation and testing of rule evaluation. It does not cover MessageFormat syntax (see the companion article), sentence selection UX, or locale data authoring politics.

## Workflow or implementation guidance

The operands extract structure from the formatted number:

- `n` — the absolute numeric value (1.5 for "1.5").
- `i` — the integer digits (1 for 1.5).
- `v` — count of visible fraction digits with trailing zeros (2 for "1.50").
- `w` — count of visible fraction digits without trailing zeros (1 for "1.50", 2 for "1.55").
- `f` — the visible fraction digits as an integer (50 for "1.50").
- `t` — `f` with trailing zeros removed (5 for "1.50").
- `c`/`e` — the compact-notation exponent (2 for "1.2c" style compact forms in plural-select contexts).

Rules combine comparisons: Polish `many` is `v = 0 and i % 10 = 2..4 and i % 100 != 12..14`. Evaluation order matters only in that `and` binds tighter than `or`, matching CLDR's grammar; parentheses are not part of the syntax.

Implementation mechanics that bite:

1. **Rules operate on the formatted form, not the mathematical value.** "1.0" and "1.00" have `v` = 1 and 2; a category chosen for `one` in French (`i = 0,1`) depends on `i`, but a language distinguishing visible decimals needs `v`/`w`. This means the string used for plural selection must be the same string (or same formatting settings) shown to the user: selecting with `Intl`-default maximum-fraction-digits but displaying two decimals selects on different operands than the eye sees.
2. **Negation: operands are absolute.** `n`, `i`, `f`, `t` are defined on the absolute value; `-1` has `n = 1`, `i = 1`. CLDR explicitly defines operands for negative numbers via absolute value, so English `-1 message` selects `one`. Implementations that feed a signed value into `mod` break here: in some languages `-1 % 10` in the host language yields `-1` (C, Java) rather than `9` (Python), and a hand-rolled rule engine then selects the wrong category for every negative count. Take `abs()` before any modular arithmetic, always.
3. **`mod` semantics are mathematical modulo on non-negative values.** Because operands are absolute, `i % 10` is well-defined; but the host language's `%` on the pre-absolute value is the classic defect. A second-order version of the bug: applying `abs` to `n` but forgetting `f`/`t`, which are already non-negative by construction — harmless but signals confused handling.
4. **Operand reuse across formatters.** If a UI displays "1.5 hours" but computes plural selection by calling a separate formatter configured differently (say, `maximumFractionDigits: 0`), selection sees `i=2, v=0` and picks the integer category. The fix pattern: format once, extract operands from the formatted string, pass both the string and the category onward. Modern `Intl.PluralRules` APIs derive operands from their configured options — configure them identically to the display formatter and pin the pairing in code review.
5. **Compact exponents (`c`/`e`).** Languages can treat "1.2K" style numbers differently; rules referencing `c` evaluate the compact exponent. If your pipeline formats compact ("2.5M users") but selects plurals from the expanded number, the two disagree in the few locales whose rules reference `c`. Rare, but worth a test if you localize compact counts.
6. **Decimal input paths.** Counts that arrive as floats (`2.0`) rather than formatted strings need explicit fraction-digit policy before operand extraction; `2.0` as JSON number formats as "2" (v=0) in most stacks but as "2.0" in others. Normalize at the boundary: the plural operand pipeline should begin with a decimal string produced by the same formatter the UI uses.

A worked example: a store displays "3.5 stars" and "4.0 stars". English rules: `one` is `i = 1 and v = 0`, so "4.0 stars" (v=1) is `other` — correct — and "1 star" only for exactly-integer 1. Arabic `few` uses `v != 0 …` clauses that make decimals categorically distinct from integers. An engine that drops `v` collapses these and renders wrong Arabic for every decimal rating.

## Controls

- Do not hand-copy rules into application code; consume them from a pinned CLDR-derived library, and record the CLDR version in the dependency lockfile documentation.
- Unit-test the rule engine against the CLDR sample values shipped with the data (each plural rule in CLDR ships with `@integer`/`@decimal` sample annotations); a conforming engine reproduces every sample's category.
- Add regression tests for negative operands: for every supported locale, evaluate `-1, -2, -2.5` and compare against the engine's evaluation of `1, 2, 2.5` — they must match category-for-category.
- Enforce formatter pairing: lint call sites where a display formatter and a plural selector are constructed separately; require a shared config object or a single API that returns both.
- Fuzz operands across `v/w/f/t` combinations (1, 1.0, 1.00, 1.10, 1.11, 0.1, 10.50) for the locales you ship; snapshot the category matrix at the pinned version and review diffs on upgrade.

## Validation evidence

- Operand definitions, the rule grammar, negation-by-absolute-value, and sample annotations are specified normatively in UTS #35 (LDML), Part 2, published by the Unicode Consortium.
- ECMAScript's `Intl.PluralRules` implements CLDR rule selection per ECMA-402, and its conformance tests exercise decimal and category coverage, demonstrating the operand-extraction contract in a shipping runtime.
- A reproducible check: for Polish, evaluate operands for `-22` and `22`; both must select `many`; an engine that returns `other` for `-22` is applying signed modulo — the exact defect class this article warns about.

## Failure modes and correction

- **Signed modulo.** Symptom: negative counts render `other`/`one` incorrectly in Slavic and Baltic locales. Correct by absolutizing operands before arithmetic.
- **Display/selection formatter mismatch.** Symptom: decimals display one way and select another's category. Correct by deriving operands from the displayed string.
- **Floats leaking into operand extraction.** Symptom: `2.0` categorizes inconsistently across services. Correct by formatting to a decimal string at the boundary first.
- **Hand-copied rules drifting from CLDR.** Symptom: locale rule updates (they do change) never reach your fork. Correct by deleting the fork.
- **Range syntax mishandling.** Symptom: `i % 100 = 12..14` implemented as three equality checks misses 13 or includes 112. Correct by implementing the grammar's `..` as inclusive range on the left-hand expression result.

## Limitations

- Plural rules classify numbers; they do not decide phrasing — a `one`-category count still reads oddly for fractions in copy ("1.5 item").
- Rules reference at most the defined operands; exotic formatting (scientific notation text, leading zeros preserved) has no operand and needs product-side normalization.
- `c`/`e` compact handling is young; library support varies and compact-plus-plural should be feature-tested per target runtime.
- CLDR occasionally revises a locale's rules; pinned behavior is a snapshot, and upgrades need the snapshot-diff review described above.

## Canonical sources

- Unicode Consortium, UTS #35: Unicode Locale Data Markup Language (LDML), Part 2 — Plural Rules Syntax and Operands: https://unicode.org/reports/tr35/
- Ecma International, ECMA-402: ECMAScript Internationalization API Specification (PluralRules): https://tc39.es/ecma402/
