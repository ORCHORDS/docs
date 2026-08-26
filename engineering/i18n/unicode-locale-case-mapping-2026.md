# unicode-locale-case-mapping-2026

**Issue:** A `textTransform: 'uppercase'` CSS class and `.toUpperCase()` calls were applied to user names and labels across the app. Turkish users saw "istanbul" uppercased as "ISTANBUL" (wrong — Turkish requires "İSTANBUL" with dotted capital İ), a German street "Straße" became "STRASSE" (one character turned into two, breaking a `.length`-based truncation and a `substring` cut), and a Greek name ending in sigma displayed with the wrong final letter form. JavaScript's default `toUpperCase`/`toLowerCase` use locale-independent (Unicode default) mappings; correct casing for human text requires locale-aware APIs, while identifiers require the opposite — strictly ASCII-only folding. Teams that use one strategy for both corrupt data somewhere.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## The failure modes

1. **The Turkish dotted/dotless i.** Turkish (and Azerbaijani) has two i-letters: dotted `i`/`İ` and dotless `ı`/`I`. Default casing maps `i`→`I` (should be `İ` in tr) and cannot map `ı` at all. The classic production bug: lowercasing the header "IMAGE" for a URL with the user's Turkish locale yields `ımage` with a dotless ı — a broken link. Round-trips fail: `ı` → `I` → `i` changes the letter.
2. **German sharp s.** `"ß".toUpperCase()` returns `"SS"` (capital ẞ exists but is rare) — length changes from 1 to 2, breaking fixed-width layouts, column math, and truncation that assumes length preservation. Lowercasing `"SS"` never yields `ß`, so the mapping is not invertible.
3. **Greek final sigma.** `"ΟΔΥΣΣΕΥΣ".toLowerCase()` must end in ς not σ; correct lowercase of the final sigma requires word-boundary context the default API partially handles — but naive per-character lowercasing loops (common in animation/typewriter code) get it wrong.
4. **Dutch IJ digraph.** Title-casing "ijsland" per-word requires "IJsland" (both letters capitalized), which generic title-case algorithms produce as "Ijsland".
5. **Lithuanian dot above.** Lowercasing `Į` must keep/absorb the dot per Lithuanian rules; default mapping leaves renderings that look wrong to Lithuanian readers.

## The correct APIs per context

1. **Human-facing prose: locale-aware methods.** Use `str.toLocaleUpperCase(locale)` / `toLocaleLowerCase(locale)` with the *content's* locale (`'tr-TR'` for Turkish text), not the viewer's or the server's. Pass the locale explicitly — the no-argument form uses the host locale and makes results environment-dependent (a classic CI-vs-production mismatch).
2. **CSS `text-transform` is language-dependent.** Browsers case-map according to the element's declared language, so `text-transform: uppercase` on Turkish text renders correctly **only if** `<html lang="tr">` (or an element-scoped `lang`) is set correctly. Wrong or missing `lang` silently produces the wrong İ/I.
3. **Identifiers: never use locale mappings.** For slugs, email local parts, URL segments, and cache keys, restrict to ASCII and fold ASCII-only (`s.replace(/[^a-zA-Z0-9]/g…).toLowerCase()`), because ASCII case mapping is identical in every locale. `toLowerCase()` on full Unicode is acceptable for identifiers only when non-ASCII is stripped first.
4. **Comparisons: case-fold, do not double-case.** `a.toLowerCase() === b.toLowerCase()` breaks for Turkish (`ı` vs `i`) and ß. Use `localeCompare` with `sensitivity` options, or Unicode case folding (NFKC_Casefold, exposed in JS via normalization-adjacent libraries and in ICU), which is designed to be lossless for comparison.
5. **Backend must match frontend.** Java `toLowerCase()` without a Locale uses the JVM default (famous Turkish server-locale bugs); always pass `Locale.ROOT` for machine identifiers and `new Locale("tr")` for Turkish user text. The same discipline applies in C# (`CultureInfo`), Python (`str.casefold()` for comparisons), and Go (`golang.org/x/text/cases` with a language tag).

## Patterns that prevent regressions

1. **Central casing helpers.** Wrap all uppercase/lowercase in two functions with unambiguous names: `upperForDisplay(text, locale)` (locale-aware) and `foldForKey(identifier)` (ASCII-safe), then lint-rule direct calls to the raw methods.
2. **Never slice or pad after casing.** Because mappings are not length-preserving (ß→SS, ﬁ ligature→fi), apply truncation/padding to the *original* string and case last — or re-measure after casing.
3. **Test with a casing corpus.** Keep unit-test strings: `"istanbul"`, `"ÇINARALTI"`, `"Çınaraltı"` (Turkish search/case classic), `"Straße"`, `"İstanbul"`, `"ΟΔΥΣΣΕΥΣ"`, `"ijsland"`. Assert tr-TR and de-DE outputs specifically.
4. **Persist originals, case on display.** Store user-entered text verbatim; derive cased variants at render time. Storing the uppercased form destroys the information needed for a later correct re-case in another locale.
5. **Watch string identity checks in the same locale.** Auto-suggest and duplicate-detection comparing typed input against stored values must fold with the same rules on both sides; mixing `toUpperCase` on one side and `toLocaleUpperCase('tr')` on the other makes Turkish duplicates invisible.
