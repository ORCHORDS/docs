# CLDR likely-subtags maximize inference boundary

**Issue:** An application treats a short locale such as `en`, `zh`, or `sr` as a complete statement of language, script, and region. It then stores inferred subtags as if the user supplied them and makes legal, currency, or content decisions from a statistical default.

**Date:** 2026-08-18
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Inference model

Unicode CLDR defines likely-subtag data and algorithms that maximize a language identifier by filling missing language, script, or region fields. Minimization removes redundant subtags while preserving the maximized meaning under the same data.

This supports resource selection and locale mechanics. It is an inference from CLDR data—not evidence of a user's residence, citizenship, currency, timezone, measurement preference, or regulatory jurisdiction.

## Data model

Keep three values distinct:

- **requested tag:** the normalized, structurally valid tag received from the user/client;
- **maximized tag:** a derived language-script-region form using a named CLDR version;
- **selected supported locale:** the resource bundle chosen by negotiation/fallback.

Do not overwrite the requested tag with the maximized form. Store provenance and CLDR/runtime version for derived values when they affect persisted behavior.

## Implementation controls

1. Canonicalize and validate the language tag using a BCP 47-aware locale library.
2. Apply the library's CLDR-backed maximize operation, not a hand-maintained language-to-country table.
3. Use the maximized script/region only for tasks whose contract explicitly accepts likely inference, such as choosing a script-specific font or breaking a resource-selection tie.
4. Ask for or derive from authoritative account data any consequential region choice. Currency, tax, privacy, catalog, shipping, and legal decisions need their own inputs.
5. Treat undetermined or private-use tags explicitly. A failed maximize must remain diagnosable and must not default silently to the server locale.
6. Pin CLDR data in reproducible builds. During upgrades, diff maximized results and selected bundles for the supported/requested corpus.
7. Use minimization only for presentation or canonical storage contracts that guarantee maximize(minimized) is equivalent under the pinned data.

## Verification

Test language-only, language-region, language-script, fully specified, deprecated aliases, macrolanguage-sensitive, `und`, private-use, and invalid inputs. Include languages with multiple commonly used scripts and regions. Assert that maximizing never mutates the raw user preference and never directly changes jurisdictional settings.

Snapshot mappings with the CLDR version. A data upgrade should produce an explicit reviewable diff rather than unexplained cache-key or bundle changes.

## Gotchas

- “Likely” means a default inferred from CLDR, not a confidence score.
- A region in a locale tag is not necessarily the user's physical location.
- Maximization is not locale negotiation and does not prove a bundle exists.
- Minimization results can change when CLDR data changes.

## Sources

- [Unicode Locale Data Markup Language (UTS #35) — Likely Subtags](https://unicode.org/reports/tr35/#Likely_Subtags)
