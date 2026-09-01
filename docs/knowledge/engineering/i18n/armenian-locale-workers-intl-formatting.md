# Armenian Locale Workers Intl Formatting

Armenian (`hy`) is a small-locale trap: the script is a dedicated Unicode block (U+0530 to U+058F, uppercase and lowercase Armenian letters), the language has its own plural behavior, its own month and weekday names, and its own quotation conventions, but almost no team tests for it until an Armenian user files a screenshot of mixed English and Armenian output. The common failure is not missing translations, it is a formatter instantiated with a default or fallback locale that renders numbers, dates, and lists with Latin patterns inside Armenian text, or a plural category set borrowed from English that produces ungrammatical Armenian counts. On Cloudflare Workers, the `Intl` surface is ECMA-402 backed by ICU data, so `hy` support is real but conditional on how the locale is resolved and passed through.

## Scope

Covers resolving the Armenian locale in a Workers runtime, formatting numbers, dates, and lists with `Intl` for `hy` and `hy-AM`, plural selection with `Intl.PluralRules`, casing and collation of the Armenian alphabet (which has a distinct letter inventory and an majuscule/minuscule distinction that matters for sorting and case folding), and fallback behavior when Armenian resources are absent. Applies to request-time locale negotiation in a Workers route, server-rendered or client-rendered localized output, and storage of user locale preferences. Out of scope: Armenian transliteration and romanization pipelines, dialect handling beyond the standard `hy` identifier, and font subsetting strategy.

## Workflow or implementation guidance

Start by treating `hy` as a complete locale, not a translation of an English skeleton. Negotiate from the `Accept-Language` header with RFC 4647 lookup semantics, and accept `hy`, `hy-AM`, and `hyw` (Western Armenian, a separate registered language if the product distinguishes) explicitly. Store the negotiated tag verbatim. In the handler, derive formatters once per request: `new Intl.NumberFormat(locale)`, `new Intl.DateTimeFormat(locale, {...})`, `new Intl.ListFormat(locale)`, and `new Intl.PluralRules(locale)`. For dates, Armenian month names and weekday names come from CLDR via the runtime; do not hardcode a month array, because era and month casing follow CLDR patterns, and `hy` formats dates with its own field order and separators.

Plural selection is the highest-risk piece. Armenian CLDR plural rules distinguish `one` for 0 and 1 (integer category `i = 0 or i = 1`, with `v = 0`) and `other` otherwise. That means 0 takes the `one` form in Armenian, which surprises engineers calibrated on English, where 0 takes `other`. Author message catalogs with `{count, plural, one {...} other {...}}` and let the runtime select; never branch on `count === 1` in code, because that ships English plural logic into Armenian output. `Intl.PluralRules('hy').select(0)` returns `one`, and a unit test asserting this pins the behavior against the runtime's CLDR data.

Collation and casing: Armenian uppercase and lowercase forms both exist, and case-insensitive search must use locale-aware folding, not `toLowerCase()` alone paired with ASCII assumptions. If you sort lists of Armenian names, use `Intl.Collator('hy')` so that the Armenian alphabetical order (including the trailing letters that follow the Greek-derived core) is respected; byte-order sorting of code points happens to place U+0531 through U+0556 uppercase before the lowercase block U+0561 through U+0586 and will not match a dictionary. For string identity across user input, normalize to NFC on write (most Armenian text is already composed; combining marks are rare but legal) and compare case-insensitively only where the product means it.

Fallback policy: if a translation key is missing for `hy`, fall back to the next supported locale by explicit list (`hy` then the product default), and log the missing key with the locale so coverage debt is visible. Do not silently interpolate English fragments into Armenian sentences; the word order and suffix structure of Armenian make fragment stitching produce text that native readers immediately flag.

## Controls

- Negotiate and persist the full Armenian tag; do not reconstruct it from region or language hints.
- Instantiate `Intl.PluralRules('hy')` in tests and assert `select(0) === 'one'`, `select(1) === 'one'`, `select(2) === 'other'`.
- Use `Intl.Collator('hy')` for any user-visible sorting of Armenian strings; keep code-point sort only for internal keys.
- Normalize Armenian user text to NFC at ingestion; store the original alongside if provenance matters.
- Run the Workers locale matrix test for `hy` and `hy-AM` on every ICU data update, because month names and plural rules are CLDR-versioned.
- Log fallback events (Armenian requested, non-Armenian served) as a first-class metric.

## Validation evidence

Verified by executing the formatting corpus in a Workers runtime and asserting exact outputs. `Intl.PluralRules('hy').select(0)` and `.select(1)` both yield `one`; `.select(2)`, `.select(5)`, and decimal operands yield `other`. `new Intl.DateTimeFormat('hy', {dateStyle: 'long'}).format(new Date('2026-08-17'))` produces Armenian month and weekday text with no Latin fragments. `new Intl.NumberFormat('hy').format(1234567.89)` yields Armenian-style grouping consistent with CLDR `hy` number patterns. `new Intl.Collator('hy').compare` ordering was compared against code-point ordering on a name list and differs as expected for majuscule/minuscule interleaving. `Intl.getCanonicalLocales(['hy-AM'])` returns the tag unchanged, confirming validity. CLDR data behind these results was identified from the runtime's ICU version pinned in the deployment.

## Failure modes and correction

Counts rendered as "1 հոդված / 2 հոդված" with an English-style branch: code used `count === 1` instead of plural rules; replace the branch with `Intl.PluralRules` selection or ICU MessageFormat `plural`. Dates showing English month names inside Armenian sentences: the formatter was built with a hardcoded locale or the locale string failed validation and fell back to the runtime default; log the resolved locale and assert it in tests. Sorted lists in wrong alphabetical order: replace `Array.sort()` default with `Intl.Collator('hy').compare`. Search failing to match "ԵՐԵՎԱՆ" against "Երևան": apply case folding in the comparison layer with collator options rather than exact equality. Mixed-script sentences after fallback: make fallback whole-message, not fragment-level, and add a lint that fails builds on missing `hy` keys for shipped surfaces.

## Limitations

This article covers standard Eastern Armenian as `hy`; Western Armenian (`hyw`) has distinct morphology and needs its own plural review even though the locale identifier resolves. Native-speaker review remains necessary for tone and naturalness; mechanical assertions prove structure, not fluency. Workers runtime ICU data versions change with the platform; the plural and date facts above are stable across recent CLDR releases but should be re-pinned when the runtime's ICU major version changes.

## Canonical sources

- ECMA-402 ECMAScript Internationalization API specification: https://tc39.es/ecma402/
- Unicode CLDR LDML Part 1: Basic Language Handling and locale data, including Armenian plural rules: https://unicode.org/reports/tr35/tr35.html
- IETF RFC 4647, Matching of Language Tags, for Accept-Language negotiation: https://www.rfc-editor.org/rfc/rfc4647
