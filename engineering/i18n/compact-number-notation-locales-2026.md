# compact-number-notation-locales-2026

**Issue:** Dashboards, counters, and analytics chips almost always abbreviate large numbers, but the abbreviation system itself is locale-specific. English uses power-of-a-thousand suffixes (K, M, B, T); Japanese, Chinese, and Korean count in powers of ten thousand (万, 億, 兆 / 만, 억); and Indian locales group by lakh (10^5) and crore (10^7), yielding compact forms like 12L or 12 लाख. Hard-coding K/M/B for all locales produces numbers that target users misread (10K maps awkwardly to 1万), and naive grouping renders 1,23,456 as the wrong 123,456. Compact notation must be delegated to locale-aware formatting, with thresholds tuned per market.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Why one suffix scheme does not fit all

1. **Western suffixes are powers of 10^3.** K (10^3), M (10^6), B (10^9), and T (10^12) shift every three digits, so 12,345,678 becomes 12.3M. Digit grouping in the full form matches at three digits (12,345,678).

2. **CJK suffixes are powers of 10^4.** Japanese 万 (10^4), 億 (10^8), and 兆 (10^12), Chinese 万 and 亿, and Korean 만 and 억 shift every four digits. Japanese-localization guidance for dashboards recommends showing values under 10,000 in full, 10,000 through 99,999,999 with 万/億, and only moving to higher units after that. Appending K/M/B to a Japanese UI reads as untranslated and forces mental conversion.

3. **Indian numbering groups by lakh and crore.** The first group is three digits, then groups of two: 1,00,000 is one lakh and 1,00,00,000 is one crore. Compact forms use L and Cr (12L, 1.2Cr) in Latin-script locales like en-IN, and लाख / करोड़ in Devanagari locales. Modern ICU/CLDR data (V8 and peers since roughly 2021) renders these correctly, but older embedded ICU builds fell back to K/M — verify on your minimum supported runtime.

4. **The suffix vocabulary is CLDR data, not logic.** Which abbreviation appears at which magnitude comes from CLDR per-locale patterns, including long forms (compactDisplay: "long" gives "12 lakh", "1.2 million"). Never hand-map magnitudes to suffix strings in application code; you will be re-implementing CLDR incorrectly.

## Implementation with Intl.NumberFormat

1. **Use notation compact and pick the display style deliberately.** A formatter created with notation: "compact" and compactDisplay: "short" (default) yields 1.2M or 1.2万; compactDisplay: "long" yields 1.2 million or 12 lakh. Long form reads better in sentence context, short form in dense chips and axes.

2. **Keep full precision accessible.** Compact form is lossy by design; pair it with a tooltip or a click-through that shows the exact localized full form via a standard formatter. This matters for financial figures where rounding ambiguity is unacceptable.

3. **Respect the locale chain.** Construct the formatter with the user locale (ja-JP, en-IN, zh-Hans-CN), not the app default. A Japanese user on an en-US-formatted dashboard sees the wrong number system for their expectations even though the digits are readable.

4. **Pin your ICU/CLDR version in CI.** Compact patterns and Indian grouping correctness vary by ICU data version across runtimes (browser, Node, embedded webviews). Snapshot formatter output for a fixed corpus of values across your supported locales so a runtime upgrade that changes patterns is caught in review, not in production.

## Thresholds and UX decisions

1. **Choose magnitude thresholds per locale, not globally.** An English UI commonly compacts from 10,000 (10K); Japanese convention keeps full digits up to 9,999 and switches at 10,000 to 万. If the product compacts uniformly at 10^4 everywhere, English users see 10K while Japanese users see 1万 — both correct — but compacting at 10^3 globally would show 9.8K to Japanese users, which is wrong for that market.

2. **Reserve decimals consistently.** One decimal (1.2万, 12.3M) is the convention; two decimals make chips noisy, zero decimals lose too much information at the low end of a magnitude. Allow overriding per surface (axis labels versus hero stats).

3. **Watch translation length in chips.** Long-form suffixes (million versus लakh) and Devanagari or CJK glyphs change chip width; test compact components with the longest supported locale (often German long form or Hindi) so containers do not clip.

4. **Do not compact in legal or money-critical strings.** Compact notation inside contracts, invoices, or payment confirmations invites disputes; use full localized numbers there and compact notation only for glanceable analytics surfaces.

## Testing checklist

1. **Fixture corpus across systems of magnitude.** Assert formatter output for representative values (9,999; 10,000; 99,999; 123,456; 12,345,678; 1,23,45,678) in en, en-IN, hi, ja, zh-Hans, and ko to cover all three grouping regimes.

2. **Round-trip full versus compact.** Verify the full-format tooltip for every compact chip matches the underlying value exactly, including Indian 1,23,456 grouping in the full form.

3. **Visual test CJK glyph rendering.** Confirm the font stack actually contains 万/億/만/억 and Devanagari लाख; fallback tofu in a dashboard chip is a release-blocking visual bug.

4. **Test on the oldest supported runtime.** Run the corpus on the minimum browser/Node versions in your support matrix to detect ICU fallbacks (the 12L versus 1.2M regression class) before users on old webviews do.
