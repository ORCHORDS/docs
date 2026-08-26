# locale-data-exchange-2026

**Issue:** A team operates in the US and Japan. They store customer addresses in two different schemas (one US-focused, one Japan-focused). They need to exchange data with EU partners. The team needs a unified locale data exchange standard.

**Date:** 2026-08-10
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## The 4 standards for locale data exchange

1. **ISO 3166-1 alpha-2 / alpha-3.** Country codes (US, USA; JP, JPN; DE, DEU).
2. **ISO 639-1 / ISO 639-3.** Language codes (en, eng; ja, jpn; de, deu).
3. **BCP 47 / IETF language tags.** Full locale tags (en-US, ja-JP, de-DE, zh-Hant-HK).
4. **CLDR territory codes.** Unicode CLDR's region codes (subset of ISO 3166, with some additions for disputed territories).

## The 5-step adoption pattern

1. **Store canonical codes** (BCP 47 in `locale` column, ISO 3166 alpha-2 in `country` column).
2. **Validate at API boundary.** Reject malformed tags with a 400.
3. **Use the same canonical form internally** (BCP 47 lowercase language, uppercase region, hyphen separators).
4. **Convert at display** using `Intl.DisplayNames` to show "English (US)" in each user's language.
5. **Never store display names.** Always store codes, format at render.

## The 5 anti-patterns

1. **Storing "United States" in a country column.** Triggers translation work in every UI surface.
2. **Mixing "en-US" and "en_US" and "eng-USA" across systems.** Pick BCP 47 and stick to it.
3. **Using country codes for languages** ("US" instead of "en"). Different concept.
4. **Storing flag emojis** as locale indicators. 🇺🇸 is the US flag, not English. Pitcairn Islands has no official flag emoji.
5. **Hardcoded country lists.** CLDR has 240+ regions; ISO 3166 has 249.

## Gotchas

- **BCP 47 vs ICU locale ID:** same syntax (en-US), different semantic anchors. Use BCP 47.
- **Disputed territories** (Taiwan TW, Palestine PS) - politically sensitive; check legal advice.
- **Deprecated codes:** `sh` (Serbo-Croatian, deprecated to `sr-Latn` / `sr-Cyrl`), `iw` (Hebrew, use `he`).
- **CLDR has territory aliases:** `UK` → `GB` since CLDR 45. Don't hardcode either; use `Intl` to normalize.
- **Script tags** (`Hant`, `Hans`, `Latn`, `Cyrl`) are essential for languages with multiple scripts (Chinese, Serbian).

## Source URLs (verified 2026-08-10)

- https://www.iso.org/iso-3166-country-codes.html
- https://www.iso.org/iso-639-language-codes.html
- https://datatracker.ietf.org/doc/html/rfc5646
- https://cldr.unicode.org/index/cldr-spec/minimaldata
- https://www.iana.org/assignments/language-subtag-registry
