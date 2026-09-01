# CLDR Currency Formats and Negative Amount Styles

Currency formatting looks deceptively simple until the details surface: where the symbol sits, how negative amounts are signaled, whether the accounting style wraps negatives in parentheses, and how the same currency renders differently across territories. CLDR encodes these conventions per locale in its numbering and currency format data, and ignoring them produces price lists that users read as wrong or, worse, amounts whose sign they misread. This article covers the CLDR currency format model, negative-amount styles, plural-aware unit patterns, and validation practices.

## Scope

This article addresses currency formatting as defined by UTS #35 numbering patterns and CLDR currency data: standard versus accounting formats, negative pattern selection, symbol and code display, and pluralized currency unit names. It covers `Intl`-style formatting behavior and ICU usage. It does not cover currency conversion, minor-unit rounding policy (cash rounding), blockchain assets, or persistence of monetary values.

## Workflow or implementation guidance

CLDR models currency formatting as a decimal format pattern plus a currency-specific pattern selection. Each locale carries `currencyFormat` (standard) and `currencyFormat-accounting` patterns; the standard pattern places the sign or parentheses per locale convention, and the accounting pattern typically uses parentheses for negatives in en locales but may differ elsewhere. Negative subpatterns are the part of the pattern after the semicolon in raw LDML (for example `#,##0.00;(#,##0.00)`); when no negative subpattern exists, the minus sign is placed per the locale's default.

The display name of a currency (plural-aware) comes from the currency unit patterns: English distinguishes "1.00 US dollar" from "2.00 US dollars" through plural categories, and some languages have more categories (Russian and Polish use several). Using the symbol (`$`), the code (`USD`), or the localized name is a per-surface decision with rules of thumb: symbols for consumer-facing compact UIs in known territories, codes in multi-currency contexts to avoid `$` ambiguity (USD, CAD, AUD, MXD all use `$`), and localized names in legal or narrative text.

Implementation workflow:

1. Always format with an explicit currency code (ISO 4217 alpha-3), never a hand-built symbol string. The formatter resolves the correct symbol and position from CLDR data for the active locale.
2. Select standard versus accounting style deliberately: accounting style is for financial statements and ledgers; consumer contexts almost always want standard.
3. For negative amounts, do not concatenate `"-"` yourself. Pass the sign through the formatter so the negative subpattern or accounting parentheses apply. A leading dash before a French-formatted amount (`-1 234,56 €`) is already handled; adding your own sign can yield `--1 234,56 €` or break RTL display.
4. For RTL locales (`ar`, `he`), rely on the formatter's bidi handling; currency symbols and digits interleave with the minus sign in ways that naive string surgery breaks. If you must embed formatted amounts into surrounding text, use the Unicode bidi isolates (for example U+2068 FSI and U+2069 PDI) around the formatted span.
5. Minor units: format with the currency's default fraction digits (JPY has 0, BHD has 3, most have 2), and only override when displaying a deliberate unit (for example, paise). Overriding fraction digits on every currency uniformly produces the classic "¥123.00" defect in Japanese interfaces.
6. Wide symbols: some locales provide a full-width or narrow symbol form (`US$` versus `$`); select narrow forms only in compact layouts where ambiguity is acceptable.

A worked example: the amount `-1234.56` in USD formats as `-$1,234.56` in `en-US` standard style, `($1,234.56)` in `en-US` accounting style, `-1.234,56 $` in `de-DE` standard style, and `−1 234,56 €`-family output in `fr-FR` with a non-ASCII minus and narrow no-break space grouping. None of these can be safely reconstructed by template code; they must come from the data.

Grouping separators also come from the pattern: `fr-FR` groups thousands with narrow no-break space (U+202F in current CLDR), not a regular space or dot. Tests that compare formatted strings must therefore normalize against the exact pinned CLDR output, not hand-typed expectations with ordinary spaces.

## Controls

- Pin the ICU/CLDR version in CI and production images; grouping separator characters have changed between releases (French thousands separator moved from U+00A0 to U+202F), and tests comparing exact strings will catch the drift only if pinned.
- Snapshot-test a matrix of (locale × currency × positive/negative × standard/accounting) covering at least `en-US`, `de-DE`, `fr-FR`, `ja-JP`, `ar-EG`, `he-IL` with USD, EUR, JPY, BHD.
- Route every user-visible monetary render through a single formatting service so negative-style and symbol choices are auditable in one place; forbid ad hoc `symbol + amount` concatenation via code review checklist.
- Store amounts as integer minor units or exact decimals and format at the boundary; never format-and-reparse in pipelines where rounding could silently alter values.
- For multi-currency lists, default to ISO 4217 code display and make symbol display an explicit per-market configuration, preventing `$` collisions across USD/CAD/AUD.

## Validation evidence

- Currency format patterns, accounting variants, plural currency unit names, and symbol data are specified in UTS #35 (LDML), Part 1 and the CLDR data itself, published by the Unicode Consortium.
- ECMAScript Internationalization API specification (ECMA-402) defines the `currency` and `currencyDisplay` options whose behavior is driven by this CLDR data.
- A reproducible check: format `-1234.56` USD with `currencySign: 'accounting'` in `en-US` and observe parentheses, then in `standard` sign observe the leading minus; do the same in `fr-FR` and observe space grouping and trailing symbol — confirming data-driven behavior worth fixture-testing.

## Failure modes and correction

- **Hand-rolled negative signs.** Symptom: double signs or misplaced dashes in RTL locales. Correct by delegating sign handling to the formatter's negative subpattern.
- **Uniform fraction digits.** Symptom: `¥1,000.00` in Japanese UIs or three-decimal omission for BHD. Correct by using the currency's default minor units from data.
- **Symbol ambiguity in multi-currency contexts.** Symptom: Canadian users misreading `$` amounts as CAD when charged USD. Correct by preferring codes or disambiguated symbols (`US$`, `CA$`) per CLDR symbol variants.
- **Stale fixture expectations.** Symptom: CI fails after an ICU upgrade with invisible character differences (U+00A0 vs U+202F). Correct by regenerating fixtures at pin time and reviewing the diff as part of the upgrade.
- **Accounting style in consumer UIs.** Symptom: users see `(5,00 €)` and read it as a string annotation, not a negative. Correct by restricting accounting format to financial-report surfaces.

## Limitations

- CLDR provides conventions, not law; some contracts and jurisdictions mandate specific presentation that overrides locale defaults.
- Plural unit names depend on the formatter supporting plural categories; templates that bypass plural rules will produce "1.00 US dollars" style defects.
- Cryptocurrencies and custom units lack ISO 4217 codes and need bespoke formatting outside the CLDR currency model.
- Rounding behavior for cash-denomination contexts (Swiss cash rounding to 5 centimes) is policy, not format data, and must be layered explicitly.

## Canonical sources

- Unicode Consortium, UTS #35: Unicode Locale Data Markup Language (LDML) — currency formats and plural rules: https://unicode.org/reports/tr35/
- Ecma International, ECMA-402: ECMAScript Internationalization API Specification: https://tc39.es/ecma402/
