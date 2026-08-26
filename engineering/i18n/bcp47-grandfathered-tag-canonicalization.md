# BCP 47 grandfathered-tag canonicalization

**Issue:** Locale stores encounter grandfathered, redundant, deprecated, and suppress-script language tags. Hand rewriting them can lose variants or extensions, while retaining aliases forever fragments caches and translation lookup.

**Date:** 2026-08-18
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Controls and implementation

Parse with a standards library against a pinned IANA Language Subtag Registry. Apply registered Preferred-Value mappings while preserving extlangs, variants, private use, and Unicode extensions according to the canonicalization contract. Record original input separately when audit or user display needs it. Remove suppress-script only when canonicalization rules permit; never infer a missing region.

Version the registry and migration. Canonical lookup keys must change atomically across catalogs, caches, user preferences, and server/client runtimes.

## Verification

Test every grandfathered class, redundant tags, deprecated language/region/script subtags, suppress-script, variant prefixes, extensions, private use, malformed tags, and registry upgrades. Assert parse-canonicalize-serialize idempotence.

## Gotchas

Canonical equivalence is not linguistic equivalence, and canonicalization does not select a best supported locale. Private-use values cannot be interpreted without a private contract.

## Sources

- IETF, [BCP 47 / RFC 5646](https://www.rfc-editor.org/rfc/rfc5646.html)
- IANA, [Language Subtag Registry](https://www.iana.org/assignments/language-subtag-registry/language-subtag-registry)
