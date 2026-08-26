# CLDR language matching distance and thresholds

**Issue:** A locale selector labels a result “best fit” but implements it with unordered prefix checks, a hard-coded language table, or a region-only score. It silently chooses a distant locale, changes behavior after a runtime upgrade, or treats matching as symmetric when the CLDR data says otherwise.

**Date:** 2026-08-18
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Problem and applicability

Unicode CLDR languageMatching data supports distance-based matching between a user's desired locales and an application's supported locales. It is distinct from RFC 4647 lookup and from likely-subtag maximization, although a CLDR implementation can use likely subtags as part of its algorithm.

Use it when product requirements permit best-fit selection and the chosen runtime exposes a versioned CLDR-based matcher. Use deterministic lookup when the protocol or compatibility contract requires lookup semantics.

## Controls and implementation

1. Preserve the ordered desired list, including any valid weight information from the input protocol, and the explicit supported-locale list.
2. Canonicalize tags with a BCP 47-aware library, then apply the CLDR implementation's specified matching algorithm. Do not recreate matchVariable data or distance tables in application code.
3. Keep language, script, and region distances distinct. Maximization can provide missing comparison fields, but inferred fields must not overwrite the original request.
4. Respect ordered languageMatch rules, including one-way behavior where present. A distance from desired A to supported B is not automatically interchangeable with desired B to supported A.
5. Apply desired-list demotion and the implementation threshold deliberately. A threshold is a product rejection boundary: beyond it, return the documented default or “no acceptable match” rather than an arbitrary nearest locale.
6. Break equal-distance results using documented supported-list ordering, not hash-map iteration or build-dependent resource discovery.
7. Pin the CLDR/runtime version for reproducible deployments. Diff selections for the supported/requested test corpus before upgrading data.
8. Report the selected resource locale separately from the requested and maximized tags. Never derive legal region, currency, residency, or identity from the match.

## Verification

Test language-only, script-sensitive, region-sensitive, macro-language, variant, alias, undetermined, private-use, and invalid tags; multiple desired locales; weights; equal distances; one-way rules; threshold boundary; no acceptable match; and supported-list reorder.

Snapshot both selected locale and distance/decision provenance under the pinned CLDR version. Compare results across a planned CLDR upgrade and require review for every changed selection.

## Gotchas

- “Best fit” is not one universal browser-independent algorithm.
- Likely subtags fill comparison fields; they do not prove user intent.
- A smaller distance is not permission to cross a product's content or regulatory boundary.
- Supported-list order can be observable when candidates tie.

## Official sources

- [Unicode Locale Data Markup Language — Language Matching](https://www.unicode.org/reports/tr35/#LanguageMatching)
- [RFC 4647 — Matching of Language Tags](https://www.rfc-editor.org/rfc/rfc4647.html)
