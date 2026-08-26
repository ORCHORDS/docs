# bcp47-language-tag-syntax

**Issue:** Language tags look deceptively simple — everyone writes en-US or fr-FR — and then a production issue arrives shaped like zh-Hans-SG, es-419, or en-US-u-ca-buddhist-nu-latn and the hand-rolled parsing breaks. BCP 47 (RFC 5646 for tag syntax, RFC 4647 for matching) defines a layered grammar: language, script, region, variants, extension singletons, and private-use sequences, all governed by the IANA Language Subtag Registry. Code that treats a locale string as two letters, compares tags by string equality, or validates with a regex will mishandle Chinese script variants (the difference between Simplified and Traditional is the script subtag, not the language), Latin-American Spanish (es-419 is a region, not a country), calendar and numbering overrides carried in the Unicode -u- extension, and canonicalization (iw is legacy for he). Language tags are load-bearing identifiers in storage, APIs, Accept-Language negotiation, and hreflang output; mis-parsing them corrupts user-facing locale selection silently.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Tag anatomy and the registry

1. **Learn the subtag order once: language-Script-REGION-variant-extension-privateuse.** A well-formed tag is language (2-3 letters or a 5-8 letter registered code), optionally script (4 letters, capitalized by convention), optionally region (2 letters or 3 digits), then one or more variants (5-8 chars or 4 starting with a digit), then extensions (singleton plus subtags), then private use (-x-). Example: de-CH-1996 is German as used in Switzerland with the 1996 orthography variant.
2. **The IANA registry is the source of truth.** Every registered subtag (language, script, region, variant) lives in the IANA Language Subtag Registry in record-jar format, updated continuously. Validity questions — is 419 a valid region (yes, UN M49 Latin America), is ZH-HANT well-formed (yes after case normalization) — resolve against this registry, not against a stale enum in your code.
3. **Script subtags carry meaning you cannot ignore.** zh-Hans versus zh-Hant selects Simplified versus Traditional Chinese and implies different locales, fonts, and sometimes territories (zh-Hans-SG versus zh-Hant-HK). Serbian sr-Latn versus sr-Cyrl is a live script choice for users. Dropping the script subtag during normalization is a functional regression, not a cosmetic change.
4. **Grandfathered and irregular tags still appear in the wild.** Tags like i-klingon or en-GB-oed predate the registry machinery; RFC 5646 keeps them valid. A parser that rejects all non-standard-shaped tags will choke on real-world data from old systems. Map them to preferred modern forms (tlh, en-GB-oxendict) during canonicalization instead.

## Well-formedness vs validity

1. **Well-formed means syntax; valid means registered subtags.** zz-XQ passes an RFC 5646 syntax check but zZ are not registered subtags. A robust pipeline does both: structural parsing for well-formedness, then registry lookup (via a maintained library like the cldr data or language-tags packages) for validity. Only valid tags should reach Intl constructors.
2. **Do not validate with regexes.** The grammar has ordering and cardinality rules (script and region appear at most once, variants can repeat) plus registry dependencies that regexes cannot express. Use platform parsing — Intl.Locale in JavaScript (which throws on malformed tags), uloc_forLanguageTag in ICU, or dedicated libraries elsewhere — and reserve regex for quick pre-filters at most.
3. **Normalize casing on input, compare case-insensitively.** Subtag case is insignificant: EN-us, en-US, and en-us are the same tag. Canonical form lowercases language, Titlecases script, uppercases region (en-Latn-US). Store canonical form, but never reject input for casing.
4. **Apply preferred-value mappings.** The registry records that iw, in, and ji were replaced by he, id, and yi; older Java locales and legacy data emit the old forms. Canonicalization through Intl.getCanonicalLocales or equivalent applies these mappings — run stored tags through it on read if the data predates the fix.

## The Unicode -u- extension

1. **-u- carries CLDR behavior overrides inside the tag.** RFC 6067 defines the Unicode locale extension: attributes (3-8 chars) and keyword sequences of a 2-character key plus type values. en-US-u-ca-buddhist selects the Buddhist calendar; th-TH-u-nu-latn forces Latin digits in a Thai locale; de-DE-u-co-phonebk selects phonebook collation. These are first-class parts of locale identity for formatting.
2. **Keys map to UTS #35 keywords.** The valid keys and values (ca for calendar, nu for numbering system, co for collation, hc for hour cycle, and more) are defined in CLDR's LDML specification and change with CLDR releases. Copying a -u- sequence without checking current CLDR keyword validity produces tags that parse but silently drop behavior.
3. **Preserve the extension through your locale pipeline.** A common bug: negotiation or persistence code strips everything after the region, so a user who asked for the Islamic calendar via ar-SA-u-ca-islamic-umalqura loses it after login. Treat the full tag, extension included, as the unit users configure; store it verbatim.
4. **Do not over-encode product state in the tag.** Extensions are for standard CLDR behavior, not arbitrary flags — that is what -x- private use is for, and even that should be rare. Product features (theme, currency) belong in settings, not language tags; overloaded tags break every standards-compliant consumer downstream.

## Transformed content, private use, and matching

1. **-t- records transformation provenance.** RFC 6497's transformed-content extension marks text that was converted — typically machine-translated — such as en-t-ar-i0-machine signaling English translated from Arabic by a machine engine. It is the standard way to embed translation provenance in a language tag for downstream consumers.
2. **-x- is the escape hatch with a cost.** Anything after -x- is private use and uninterpretable outside your system (de-DE-x-formal for a formal register variant is a legitimate internal use). Every standards-based tool ignores it, so behavior keyed on -x- must be implemented by your code everywhere the tag travels.
3. **Match with RFC 4647 semantics, not string equality.** Lookup truncates from the right (zh-Hans-SG matches zh-Hans then zh) with a default fallback; basic filtering selects ranges including wildcards. Implement locale negotiation with these rules — the existing knowledge_base articles on Accept-Language negotiation cover the wire side; the point here is that tag-internal structure is what makes truncation correct.
4. **Use likelySubtags to expand minimal tags.** CLDR's likelySubtags data maps minimal tags to defaults (zh expands to zh-Hans-CN). Intl.Locale.prototype.maximize exposes this in JavaScript. Expand before choosing fonts, plural rules, or regional defaults so users with a bare language tag still get coherent behavior.

## Engineering rules

1. **Tags are opaque in storage; parse at the edges.** Store the full user-provided tag verbatim (canonicalized), and parse it into components only where a decision needs a component. Re-parsing on every access invites drift between services that parse differently.
2. **Centralize tag handling in one module per service.** Validation, canonicalization, script/region extraction, and extension access belong in one reviewed implementation per codebase, not in N ad-hoc splitOn('-') call sites — audit for those in every locale-touching PR.
3. **Test with the nasty corpus.** Unit-test the parser against: es-419, zh-Hant, de-CH-1901, en-US-u-ca-buddhist, ar-SA-u-ca-islamic-umalqura, sl-rozaj-biske (dialect variants), i-klingon, x-internal-only, and the empty/malformed strings fuzzing produces. Known-expected outputs for each pin the behavior.
4. **Re-validate against registry and CLDR updates.** Both the IANA registry and CLDR keyword sets evolve; schedule a periodic task that re-runs your tag corpus through the current validator and reports newly valid or newly deprecated subtags instead of discovering them from user reports.
