# phone-number-e164-parsing-display-2026

**Issue:** The product stored phone numbers exactly as users typed them ("06 12 34 56 78", "(415) 555-2671 ext. 3"), validated them with a hand-rolled `/^\+?[0-9\s-]{7,}$/` regex, and rendered them raw in every UI surface. After expanding beyond one country, SMS delivery failed (carriers require E.164), duplicate accounts appeared (same number, different formatting), and support could not tell which country a number belonged to. Phone numbers are not "strings with digits": they are structured data with a country code, national number, optional extension, and per-country validity rules that only a metadata library can evaluate.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## The failure modes

1. **Regex validation.** A regex cannot know that `06 12 34 56 78` is valid in France but `0612345678` is not assignable in the US, or that UK numbers vary between 10 and 11 significant digits. Regexes accept invalid numbers and reject valid ones (Hong Kong 8-digit numbers, Argentine mobile numbers with extra digits).
2. **Storing formatted input.** Saving "(415) 555-2671" loses the country context entirely — it cannot be normalized later because the default country at read time may differ from the country at write time. Formatting belongs to the display layer, never to storage.
3. **Treating number-as-typed as identity.** Two registrations of the same physical number in different formats create duplicate accounts. Deduplication requires one canonical form.
4. **One display format everywhere.** Showing `+33612345678` to a French user is hostile (they expect `06 12 34 56 78`); showing `(415) 555-2671` to a German user hides the country. Display format must be chosen per context, not stored once.
5. **Losing extensions and non-digits.** Extensions (`ext. 3`), and legitimate letters in vanity numbers (`1-800-FLOWERS`) are silently destroyed by `.replace(/\D/g, '')` pipelines that assume everything non-digit is noise.

## Storage and parsing rules

1. **Canonical storage in E.164.** Normalize at the boundary and store `+<countrycode><nationalnumber>`, maximum 15 digits per ITU-T E.164 (e.g. `+33612345678`). Every integration point (SMS, tel links, dedup keys) consumes this single form.
2. **Parse with an explicit default country.** Use `libphonenumber` (Java/C++), `libphonenumber-js` (JS) or equivalents: `parsePhoneNumber('06 12 34 56 78', 'FR')` resolves to `+33612345678`. The default country comes from the user's locale/selection, never from the server's timezone.
3. **Validate with library semantics, not shape.** Prefer `isValidPhoneNumber(value, country)` / `isValidNumberForRegion` — these check number length, prefix assignability, and number type (mobile vs fixed-line) against shipped metadata. Some inputs cannot be unambiguously converted to E.164 without a country; if the country is unknown, refuse rather than guess.
4. **Keep the extension separate.** RFC 3966 models this: store `+14155552671;ext=3` or split fields. Never concatenate the extension into the national number.
5. **Pin and update the metadata.** Numbering plans change (new prefixes, number portability rules). libphonenumber ships metadata updates continuously; upgrade the package on a schedule so validation rules do not rot.

## Display and formatting strategy

1. **Format at render time.** Derive the display string from stored E.164 on every render — `format(nationalNumber, 'NATIONAL')` for domestic contexts, `'INTERNATIONAL'` (`+33 6 12 34 56 78`) for cross-border lists, and `E164` for machine contexts (QR codes, copy-to-clipboard for SMS apps).
2. **National for same-country viewers.** If the viewer's region equals the number's region, show the national format; otherwise show international. libphonenumber exposes the number's region from parsing, so this is a region-pair decision.
3. **Use as-you-type formatting for inputs.** `AsYouType('FR')` reformats on every keystroke (`06 12 34…`), giving instant visual feedback instead of a validation surprise at submit. Pair with a country selector that sets the parsing default — a bare text input cannot disambiguate.
4. **Dialing needs different formatting.** `formatNumberForMobileDialing` produces what a phone app actually needs (adding the national trunk prefix or international prefix depending on where the caller is). `tel:` links should use RFC 3966 (`tel:+33612345678;ext=3`), not display formatting.
5. **Show a confirm step.** For account-critical numbers, send a verification code; validity checks catch format errors, not typos into a wrong-but-valid number.

## Pitfalls

1. **False positives from validity checks.** libphonenumber validity is pattern-based; a wrong-but-well-formed number passes. Never treat "valid" as "belongs to this user" without verification.
2. **Shared/callcenter numbers.** Some regions allow the same number for multiple SIMs (multi-SIM markets in Africa/Asia); uniqueness constraints on E.164 can lock out legitimate users.
3. **Vanity numbers.** `1-800-FLOWERS` must be converted with `KeypadLetterToNumber` semantics before E.164 conversion; stripping letters breaks it.
4. **Hashing for privacy.** When using numbers as opaque identifiers (analytics, lookups without PII exposure), hash the E.164 form — hashing the raw input yields different hashes per formatting variant and defeats deduplication.
