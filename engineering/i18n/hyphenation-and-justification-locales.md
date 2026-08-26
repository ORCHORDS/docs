# hyphenation-and-justification-locales

**Issue:** Justified text (text-align: justify) with hyphenation is standard print typography that fails silently on the web in a locale-dependent way. German compounds stretch across half a column with no break opportunity; Polish consonant clusters overflow; Thai has no spaces and cannot hyphenate with dictionaries at all; Japanese never hyphenates but breaks anywhere subject to kinsoku rules; and browsers only apply automatic hyphenation when the lang attribute is correctly set and they ship a dictionary for that language. Teams enable text-align: justify plus hyphens: auto globally, then discover that for a third of their locales the result is rivers of whitespace or overflowing words. The engineering problem is per-locale justification and hyphenation policy: tagging language correctly, choosing which locales get hyphens at all, tuning limits, and handling the languages where CSS hyphenation simply does not apply.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## The lang attribute is the hidden dependency

1. **Hyphenation never runs without lang.** Per MDN, hyphens: auto is language-specific: browsers select hyphenation rules from the lang attribute on the element or an ancestor, and without a correct lang value automatic hyphenation does not happen at all. A mis-tagged German paragraph under html lang="en" renders as unhyphenated, badly spaced justified text with no console warning.
2. **Dictionaries are per browser and per OS.** Chrome ships its own hyphenation dictionaries per language; Firefox historically relies on Hunspell-style dictionaries. Coverage differs: major languages are fine, smaller ones (e.g. some Slavic and African languages) may hyphenate in one browser and not another. Test the actual browser matrix per locale, not just Chrome.
3. **Lang tagging must survive templating.** In localized SPAs, set lang on the html element when the locale changes and on embedded foreign-language quotes inline. A common bug is the SSR shell always emitting lang="en" while the client swaps strings, leaving the shipped document permanently mis-tagged for hyphenation, quotation marks, and screen-reader pronunciation simultaneously.
4. **Inherit correctly in mixed content.** A Japanese page quoting an English paragraph needs lang="en" on the quote element so the English hyphenates while the surrounding Japanese follows kinsoku rules. One global lang value cannot serve mixed-direction, mixed-script content.

## Per-locale policy decisions

1. **German justifies poorly without hyphenation.** German word compounds routinely exceed 25 characters, so justified German text without hyphens: auto produces extreme inter-word gaps. German is the canonical case where justification requires hyphenation: enable both together or use left alignment.
2. **Polish, Czech, Finnish need looser limits.** These languages have long words and rich morphology; configure hyphenate-limit-chars (supported in Safari, and in Chromium behind progressive enhancement) so words shorter than 6-8 characters are not hyphenated and words do not end with a single orphan character after the break.
3. **Thai is the exception — no spaces, no hyphens.** Thai segments at word boundaries invisible in the text; CSS hyphenation does not apply, and justification must rely on Thai-aware line breaking (dictionary-based segmentation in the browser, triggered by lang="th"). Do not enable justify on Thai without testing: browsers insert breaks at Thai word boundaries, but inter-word distribution behaves unlike space-delimited languages.
4. **CJK never hyphenates but justifies naturally.** Chinese and Japanese break between characters (subject to kinsoku), so justify works well without hyphens; the settings are the opposite of German. Keep hyphens off for ja/zh locales and rely on default breaking plus line-break rules.
5. **Avoid hyphenation in UI chrome.** Buttons, labels, table headers, and headings should not hyphenate regardless of locale — a hyphenated verb on a button reads as an error. Scope hyphens: auto to long-form body text selectors only, and leave hyphens: manual plus overflow-wrap as the default for short strings.

## Justification quality beyond hyphens

1. **text-wrap: balance for headings.** Modern Chromium and Firefox support text-wrap: balance and pretty, which distribute lines without hyphenation; use balance for headings and pretty for paragraphs where supported instead of justify, since ragged-right with good wrapping often beats poor justification.
2. **hyphenate-character for locale-correct marks.** Languages differ in the break character (hyphen, double hyphen); hyphenate-character lets the CSS specify it where supported. For most locales the default U+2010 hyphen is correct, but verify for Turkish and Catalan usage where conventions differ from English.
3. **overflow-wrap as the safety net.** Pair hyphens: manual/none with overflow-wrap: break-word so a pathological long URL or German compound cannot overflow its container in browsers lacking dictionary support for that locale. This is a containment strategy, not typography — it prevents layout breakage while degrading gracefully.
4. **Never justify bidirectional narrow columns.** Justified Arabic or Hebrew in narrow columns with mixed Latin tokens produces stretched kashida-like gaps in browsers that do not support kashida insertion; prefer start-aligned (text-align: start) text for rtl locales unless the design system has tested justification there.

## Testing and enforcement

1. **Per-locale visual snapshot of a stress paragraph.** Maintain fixture paragraphs per locale (German compound-heavy, Polish cluster-heavy, Thai unspaced, CJK) and screenshot them at narrow widths in the CI visual suite; hyphenation and justification failures are visual and silent to unit tests.
2. **Lint lang coverage.** A static-analysis rule verifies that every localized page template sets lang and that embedded lang switches match the translation catalog's language subtags. Treat a missing lang as a build failure, because it silently disables hyphenation, quoting rules, and a11y pronunciation at once.
3. **Can I use checks per release.** Hyphenation dictionary coverage and hyphenate-limit-chars support shift between browser releases; re-verify the support matrix on caniuse when the browser support policy changes, and keep the CSS written so unsupported properties degrade (extra limits are enhancements, not requirements).
4. **Native-reader review of break quality.** A dictionary-correct hyphenation can still be wrong for brand terms and neologisms; add a soft-hyphen review pass where localizers can insert U+00AD in catalog strings for words the browser breaks badly, and verify hyphens: manual honors them.
