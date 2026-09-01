# BCP 47 Unicode Locale Extensions: the -u- and -t- Attributes

A bare locale tag like `fr` under-specifies behavior. Should dates show a 12- or 24-hour clock? Which calendar? Collation phonebook or default? Transformed from which source language? BCP 47 defines extension subtags — most importantly the Unicode `-u-` locale extension and the `-t-` transformed-content extension — that carry these settings inside the locale identifier itself. Parsing, canonicalizing, and honoring these extensions correctly is what separates a locale-aware service from one that silently defaults. This article covers the extension grammar, the high-value keywords, and engineering practice around accepting, validating, and propagating them.

## Scope

This article addresses BCP 47 language tags (RFC 5646/BCP 47) with Unicode extensions per UTS #35 LDML: the `-u-` extension syntax (`-u-ka-noignore`-style attributes and keyword/type pairs like `-u-co-phonebook`, `-u-nu-latn`, `-u-ca-islamic-umalqura`, `-u-hc-h23`, `-u-fw-mon`), the `-t-` transformed extension (`-t-en`-style language fields and `tLang`/molecule fields), and duplicate-handling, case, and canonicalization rules. It covers parsing and propagation in services. It does not cover basic language/region tag matching (RFC 4647 lookup), likely-subtags reasoning, or HTTP Accept-Language negotiation mechanics beyond extension passthrough.

## Workflow or implementation guidance

The `-u-` extension follows the pattern `-u-` then any number of singletons-each-2-to-8-alphanumeric subtags interpreted by Unicode's registry as: leading **attributes** (bare subtags with no value, e.g. `-u-emo` or `-u-ka-noignore` where `ka` is key `noignore` value-free interpretation differs — concretely, attributes are subtags before the first recognized key) followed by **key/value pairs** where a key is exactly two alphanumeric characters and its value is one or more 3–8 character subtags.

The keywords most services actually need:

- `ca` — calendar: `ca-gregory`, `ca-islamic-umalqura`, `ca-persian`, `ca-ethiopic`, `ca-japanese`, `ca-buddhist`.
- `nu` — numbering system: `nu-latn`, `nu-arab`, `nu-thai`, `nu-hanidec`. Critical for digit rendering in Arabic, Thai, and Chinese contexts.
- `co` — collation: `co-phonebook`, `co-pinyin`, `co-traditional`, `co-search`, `co-eor`.
- `hc` — hour cycle: `hc-h11`, `hc-h12`, `hc-h23`, `hc-h24`. Resolves the 12/24-hour clock question explicitly instead of by region default.
- `fw` — first day of week: `fw-sun`, `fw-mon`, `fw-sat`.
- `rg` — region override: `rg-gbzzzz`-style subdivision preference for region-sensitive defaults.
- `sd` — subdivision: `sd-usca` (US California) for region subdivision preference.
- `em`, `vt`, `lw`, `ss`, `tz` (time zone in some stacks via `-u-tz-…` private-ish usage varies) — less common; consult UTS #35's keyword registry before trusting a stack's support.

The `-t-` extension marks content transformed from another language: `-t-en` says "this content is English transformed", with optional fields like `tLang` (`-t-fr`), `m0` mechanism, and `s0`/`d0` source/destination identifiers — used mainly in machine-translation provenance chains (`ja-t-es-m0-google`-style tags carry a caveat: mechanism value registries are agreement-based, and vendor names appear in real data).

Parsing rules that matter:

1. **Keys are exactly 2 characters; values are 3–8.** A subtag of length 2 after `-u-` starts a key; longer subtags before any key are attributes. Case is insignificant (`-U-CO-PHONEBOOK` equals `-u-co-phonebook`) and output should be lowercased per canonical form.
2. **Duplicate keys/extension singletons are invalid.** BCP 47 forbids two `-u-` extensions in one tag; a parser seeing `-u-co-phonebook-u-nu-latn` must reject or fold to canonical single-`u` form — library behavior differs; reject early at your boundary.
3. **Unknown keys and values must be ignorable, not fatal.** The robustness principle of UTS #35's extension design: unknown `key-value` pairs are skipped, known keys with unknown values fall back to default behavior. A service that 500s on `-u-xx-yyy` (a future keyword) breaks on every registry addition.
4. **Canonicalization orders keys alphabetically** (Unicode's canonical form sorts keys) and normalizes case; `und-u-co-search-ca-gregory` canonicalizes to `und-u-ca-gregory-co-search`. Storing raw vs canonical affects cache keys and dedup — canonicalize once at the edge with a pinned ICU.
5. **Extension position is fixed**: after language and script/region (and any variants/extensions in proper singleton order, BCP 47 allows multiple different extension singletons, each appearing once).
6. **Propagation is a system decision.** Accept-Language does not standardize `-u-` content in general deployment; user preferences set via OS or account settings usually travel in app-specific channels. Decide once: derive final locale + extensions server-side from (user preference, request hints, defaults), emit a single resolved tag like `de-DE-u-co-phonebook-hc-h23`, and pass it to every formatting call in the request context.

A worked example: a bank's statement service must show German phonebook ordering, 24-hour timestamps, and Latin digits even when accessed from a browser requesting `de-CH`. The resolved locale becomes `de-DE-u-co-phonebook-hc-h23-nu-latn`; the same string appears in logs, cache keys, and the formatting layer, making every rendered artifact reproducible from its metadata.

For `-t-`: store it on content, not on requests. A translated article's metadata `pt-BR-t-en` records English origin; renderers mostly ignore it, but translation-memory and QA systems key off it. Ensure your content pipeline preserves `-t-` through transforms rather than stripping extensions wholesale.

## Controls

- Parse and canonicalize locale strings with one pinned library (ICU) at the system edge; forbid ad hoc regex parsing of locale tags in service code via review checklist.
- Validate unknown-extension tolerance with tests: assert requests carrying `-u-` keywords from one future Unicode version still succeed (no throw), with keywords ignored.
- Log resolved full locale (with extensions) on every render-affecting operation; bugs reported as "wrong sort" are unreproducible without the extensions in the trace.
- Contract-test keyword effects: for each keyword you rely on (`co`, `nu`, `hc`, `ca`, `fw`), a golden test proves the formatter output actually changes when the keyword changes — this catches stacks that parse and silently ignore.
- Maintain an allowlist of accepted `-u-` keywords per endpoint if abuse surface matters (long extension chains are cheap DoS padding); enforce a total tag length cap.

## Validation evidence

- The BCP 47 tag structure, extension singleton rules, and duplicate prohibition are specified in RFC 5646 (Tags for Identifying Languages), published by the IETF.
- The `-u-` and `-t-` extension syntax, keyword registry, canonicalization ordering, and default-resolution rules are specified in UTS #35 (LDML), published by the Unicode Consortium.
- A reproducible check: canonicalize `EN-u-CO-PHONEBOOK-ca-GREGORY` with ICU and assert the output `en-u-ca-gregory-co-phonebook`; then feed `-u-co-phonebook-u-nu-latn` (duplicate singleton) and confirm the boundary parser rejects rather than silently dropping one — two behaviors every production parser must exhibit.

## Failure modes and correction

- **Regex parsing of tags.** Symptom: valid extended tags rejected or mangled. Correct by ICU-based parsing at the edge.
- **Fatal on unknown keywords.** Symptom: outage when clients upgrade before servers. Correct by ignore-unknown semantics with logging.
- **Silent ignore of known keywords.** Symptom: phonebook sorting promised in the tag but lists sort default; users notice, tests don't. Correct with effect-contract tests per keyword.
- **Cache keys on raw tags.** Symptom: `de-DE` and `de-DE-u-hc-h23` share cache entries; 12-hour clock leaks to German users. Correct by canonicalizing before keying.
- **Stripping `-t-` in content pipelines.** Symptom: translation provenance lost; QA reruns cost. Correct by whitelisting extension preservation on content metadata.

## Limitations

- Keyword support varies by runtime (operating system formatters, databases, JS engines); the same tag behaves differently across stacks — capability-test per surface.
- `-t-` registry semantics (mechanisms, vendor identifiers) depend on bilateral agreements, not a strict standard registry.
- Extension tags lengthen Accept-Language-like channels beyond some intermediary limits; prefer internal channels for rich locale context.
- `rg`/`sd` region overrides are honored inconsistently by formatters; treat them as advisory.

## Canonical sources

- IETF, RFC 5646: Tags for Identifying Languages (BCP 47): https://www.rfc-editor.org/rfc/rfc5646
- Unicode Consortium, UTS #35: Unicode Locale Data Markup Language (LDML) — Unicode locale extensions (-u-, -t-): https://unicode.org/reports/tr35/
