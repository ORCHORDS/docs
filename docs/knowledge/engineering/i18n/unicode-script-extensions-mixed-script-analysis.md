# Unicode Script_Extensions for mixed-script analysis

**Issue:** A validator decides a string's script from Unicode `Script` alone. Combining marks, shared punctuation, and characters used by several writing systems are misclassified, so legitimate names are blocked while risky mixtures pass.

**Date:** 2026-08-18
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Property boundary

Unicode Standard Annex #24 defines script properties. `Script` assigns one primary script value; `Script_Extensions` can provide a set of scripts with which a character is commonly used. Values such as Common and Inherited require contextual treatment and must not automatically become independent “scripts present.”

These properties describe character usage. They do not detect language, nationality, keyboard, or user intent. Mixed-script analysis is therefore a policy input, not a translation or language-detection system.

## Analysis pattern

1. Iterate Unicode code points, not UTF-16 code units.
2. Load `Script` and `Script_Extensions` from one pinned Unicode Character Database version.
3. For each code point, derive its permitted script set according to UAX #24. Handle Common, Inherited, marks, and join controls using the profile's documented context rules.
4. Combine sets across the identifier or token. Preserve ambiguity rather than choosing the first script value.
5. Apply a namespace-specific allowed-script or restriction-level policy. Human names and free prose need different policy from domains, usernames, package names, or payment aliases.
6. Return structured findings: code point, position, property values, resolved set, and policy rule. Do not silently rewrite characters.
7. Pair script analysis with the relevant identifier syntax, normalization, bidi, default-ignorable, and confusable controls.

For user-facing text, warnings and review are usually safer than rejection. For security identifiers, define an allowlist and a documented exception process.

## Data and rollout

Pin the Unicode version in code and generated tables. During upgrades, evaluate existing values with both versions and report changed classifications before enforcement. A new script assignment or `Script_Extensions` update can change a decision without any application-code change.

Keep policy data separate from UCD data. “Unicode says this character can be used with these scripts” is not the same as “this product permits this combination.”

## Verification

Use official UCD property data plus fixtures containing Latin with inherited combining marks, Japanese script combinations, Arabic-script digits and punctuation, emoji/common symbols, identifiers mixing Cyrillic and Latin, supplementary-plane scripts, join controls, and unassigned code points. Verify position reporting uses a documented coordinate system.

Fuzz with normalization-equivalent strings and ensure analysis is deterministic for the pinned version.

## Gotchas

- Counting distinct raw `Script` values over-reports Common and Inherited.
- A single-script result does not prove an identifier is non-deceptive.
- Applying strict identifier rules to sentences excludes ordinary multilingual text.
- Script properties do not substitute for locale or language metadata.

## Sources

- [Unicode Standard Annex #24 — Unicode Script Property](https://www.unicode.org/reports/tr24/)
