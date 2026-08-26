# Unicode locale region and subdivision overrides

**Issue:** An application overloads the BCP 47 region subtag to request regional formatting or subdivision behavior, changing language identity and breaking locale matching.
**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented; consume only where supported

UTS #35 defines Unicode locale extension keys including `rg` for region override and `sd` for subdivision. Preserve them as preferences and apply only to operations whose locale-data contract supports them.

**Source:** [Unicode LDML — Unicode locale extension keys](https://unicode.org/reports/tr35/#Unicode_locale_identifier)

## Controls

- canonicalize the full locale with a standards library;
- distinguish language/script/region identity from supplemental regional preference;
- validate values against the pinned CLDR key/type data;
- preserve unknown-but-well-formed extensions through storage;
- expose explicit user settings instead of silently inferring subdivision.

## Verification

Test locale tags with region plus `rg`, `sd`, both keys, unsupported values, fallback, server/client CLDR mismatch, and round-trip serialization. Confirm negotiation does not strip extensions accidentally.

## Gotchas

Support varies by formatter and runtime. `sd` is not a precise geolocation signal. Region override must not change legal/tax behavior without an explicit domain decision.
