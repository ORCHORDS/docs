# international-address-2026

**Issue:** A team builds a checkout flow. The address form has fields Name, Street, City, State, ZIP, Country. A German customer enters the address in their native format: Straße first, then house number, then PLZ, then Ort. The form rejects "Straße" because there's no field for it. The customer abandons the cart.

**Date:** 2026-08-10
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Symptom

Address formats vary by country. The 2026 fix is Google's `libaddressinput` (open-source, used in Chrome, Android, Google Cloud) or equivalent. The 2026 default is locale-aware address forms with CLDR-backed metadata.

## Root cause

Address formats are not just labels; they differ in:
- Field order (Japan: postal code first; US: ZIP last)
- Field presence (US has state; UK has county; Japan has prefecture)
- Postal code format (US: 5-digit or 5+4; UK: alphanumeric; Japan: 3+4)
- Required vs optional fields (UK: county not always required; Brazil: state required)
- Field labels (US: "ZIP code"; UK: "Postcode"; both label the same field differently)

The 2026 default: use a library that knows the format for each country.

## The 5 address format levels

| Level | Country | Format |
|---|---|---|
| Simple | US | `%N%n%O%n%A%n%C, %S %Z` (Name, Org, Address, City, State ZIP) |
| Postal-code-first | Japan | `〒%Z%n%S%n%C%n%A` (Postal code, State, City, Address) |
| Multi-line | UK | `%N%n%O%n%A%n%C%n%S%n%Z` (Name, Org, Address, City, State, Postcode) |
| Multi-script | Korea | `%N%n%O%n%A%n%C %S%n%Z` |
| Free-form | some regions | Single address line |

The format string uses placeholders (%N = name, %A = address lines, %C = city, etc.). The library renders the right format per country.

## Google's libaddressinput

The 2026 default for international address forms.

- **Open source** — Apache 2.0, github.com/google/libaddressinput
- **C++ and Java libraries** — used in Chrome and Android
- **Data service** — chromium-i18n.appspot.com/ssl-address
- **Coverage** — 240+ countries with format, validation, region hierarchy
- **Metadata** — required fields, field format (regex), example values, language variants

The library asks for the country, then renders the right form for that country with the right fields, labels, validation, and order.

## The 6 address fields (libaddressinput model)

| Code | Field | Required in |
|---|---|---|
| N | Name | most |
| O | Organization | optional |
| A | Street address line(s) | most |
| D | Dependent locality (district/suburb) | some |
| C | City or locality | most |
| S | Administrative area (state, province, prefecture) | most |
| Z | Postal code | most (not all) |
| X | Sorting code (CEDEX, sector) | rare |

The metadata specifies which fields are required and which are optional per country.

## The required field examples

| Country | Required | Optional | Format |
|---|---|---|---|
| US | N, A, C, S, Z | O | ZIP: `\\d{5}([ \\-]\\d{4})?` |
| UK | A, C, Z | N, O, S | Postcode: `[A-Z]{1,2}[0-9R][0-9A-Z]? [0-9][A-Z]{2}` |
| Japan | Z, S, C, A | N, O | 〒 followed by 3-4 digits |
| Germany | A, C, Z | N, O, S | PLZ: 5 digits |
| Brazil | A, C, S, Z | N, O | CEP: `\\d{5}-\\d{3}` |
| China | S, C, A, Z | N, O | 6-digit postal code |

The library provides per-region ZIP format validation (e.g., California ZIP starts with 9[0-5]).

## The 4 implementation patterns

| Pattern | When | Pros | Cons |
|---|---|---|---|
| libaddressinput (C++/Java) | native apps, Chrome-based | best metadata, no network calls | native build, C++/Java only |
| libaddressinput via REST | any app via Address Data Service | no native build | network call per validation |
| Google Places API | production with full address | autocomplete + validation | $$$, Google dependency |
| Custom CLDR + regex | low-budget, simple cases | no dependencies | 240 countries of metadata to maintain |

The 2026 default: libaddressinput for native; libaddressinput via REST for web; Places API when autocomplete is needed.

## The 5-step adoption pattern

1. **Pick the library** — libaddressinput native or REST, or Places API
2. **Ask for country first** — the country determines the form
3. **Render the form** — fields in the right order, right labels, right placeholders
4. **Validate as the user types** — show valid/invalid feedback
5. **Persist in a canonical form** — normalize the data; don't store country-specific quirks

The country-first pattern means the form is right-sized for the user.

## The 5 best practices

1. **Use the right library, not hand-rolled regex.** Address formats are not stable; libraries update.
2. **Country first, then fields.** Don't show a US-style form to a Japanese customer.
3. **Persist the data normalized.** CLDR region code (US, GB, DE), structured fields, full address lines.
4. **Validate postal code per country.** US ZIP regex differs from UK postcode regex differs from Japan 〒.
5. **Support dependent locality for relevant countries.** UK counties, Korean districts, etc. — the library knows.

## The 5 anti-patterns

1. **One form for all countries.** US-style address for everyone is wrong for Japan, Korea, China, etc.
2. **Hard-coded ZIP regex per country.** 240 countries; the library knows them.
3. **Free-text address only.** No validation; the data is dirty.
4. **Country code as a free-text field.** Use a select with the canonical list (CLDR region codes).
5. **No dependent locality.** UK, Korea, China have sub-regions; missing them breaks delivery.

## The CLDR region code standard

The 2026 default: ISO 3166-1 alpha-2 codes (US, GB, DE, JP, etc.) backed by CLDR.

- ISO 3166-1 alpha-2 — 2-letter codes
- ISO 3166-2 — subdivision codes (US-CA = California, GB-LND = London)
- CLDR territory codes — extension of ISO 3166 with more subdivisions

Use ISO 3166-1 alpha-2 as the canonical country code in your data model.

## The canonical data model

```typescript
interface Address {
  countryCode: string;         // ISO 3166-1 alpha-2, e.g. "US", "JP"
  administrativeArea: string;   // state, province, prefecture (ISO 3166-2)
  locality: string;             // city
  dependentLocality?: string;   // district, county
  postalCode: string;           // ZIP, postcode, 〒
  sortingCode?: string;         // CEDEX, sector code
  addressLines: string[];       // 1-4 lines depending on country
  organization?: string;
  recipients: string[];         // name(s)
  languageCode?: string;        // BCP 47, e.g. "ja", "en-US"
}
```

The Google Cloud Document AI PostalAddress is one model. CLDR is the source for the field names and types.

## The 4 validation patterns

| Pattern | What | When |
|---|---|---|
| Per-field format | postal code regex per country | always |
| Hierarchy validation | city must be in state; state must be in country | production |
| Delivery point | USPS, Royal Mail, etc. APIs | high-value shipments |
| Geocoding | lat/lng from address | delivery routing |

The 2026 production default: per-field format + hierarchy validation. Delivery point is for shipping integrations.

## The privacy / GDPR consideration

Address is personal information under GDPR. The 2026 pattern:

- Minimize storage — only what the shipping/contact use case needs
- Document the lawful basis — usually contract performance
- Set retention — purge old addresses after the use case ends
- Honor data subject rights — provide the data on request, erase on request

Address data is not a "harmless" field; it identifies a person.

## Verification

The tell that international addresses are handled:

- A library (libaddressinput, Places API, or equivalent) is in use
- The form is country-aware (fields, order, validation)
- Postal code validation is per-country
- Data is stored in a canonical structured form
- GDPR / privacy is handled

The tell it isn't:

- One form for all countries
- No postal code validation
- Free-text address only
- Hard-coded regex per country
- Address stored as a single string

## Gotchas

- **240 countries is a lot.** The library handles it; you don't.
- **Postal code formats change.** Japan 7-digit to 8-digit happens. The library updates.
- **Dependent locality is often missed.** UK county, Korean district, Chinese prefecture. The library knows.
- **The "country first" rule** — the country determines everything else.
- **CLDR region codes are canonical.** ISO 3166-1 alpha-2 (US, GB, DE) is the storage format; CLDR adds subdivisions.

## Related

- `i18n/cldr-data-2026.md` — CLDR backing data
- `i18n/personal-name-formatting-2026.md` — name formatting
- `i18n/icu-message-format.md` — message format
- `i18n/locale-negotiation.md` — locale selection

## Source URLs (verified 2026-08-10)

- https://github.com/google/libaddressinput — libaddressinput
- https://chromium-i18n.appspot.com/ssl-address — Address Data Service
- https://github.com/google/libaddressinput/wiki/AddressValidationMetadata — metadata format
- https://docs.cloud.google.com/document-ai/docs/reference/rest/Shared.Types/PostalAddress — PostalAddress schema
- https://cldr.unicode.org/ — CLDR
- https://www.iso.org/iso-3166-country-codes.html — ISO 3166
- https://github.com/google/libaddressinput/blob/master/common/src/main/java/com/google/i18n/addressinput/common/AddressData.java — AddressData class
