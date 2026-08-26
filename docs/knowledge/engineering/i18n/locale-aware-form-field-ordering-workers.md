# Locale-Aware Form Field Ordering in Workers

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case
A registration or checkout form collects names and addresses, but the expected field order
differs by locale: Japanese users expect family name before given name; Korean addresses
run from country down to street; many locales omit state/province entirely.

## Context
A Cloudflare Worker exposes a `/form-schema/:formType` endpoint that returns a JSON
schema describing field order, labels, and optionality for the requesting locale. The
client renders the form dynamically from this schema, ensuring the correct cultural
ordering without per-locale branching in front-end code. Field order data is derived from
CLDR's `PersonName` and `PostalAddress` supplemental data.

---

## Name Field Order by Locale

CLDR defines two name ordering conventions: `givenFirst` (Western default) and
`surnameFirst` (East Asian, Hungarian, parts of Africa).

```typescript
// src/lib/name-schema.ts

export type NameFieldId = "honorific" | "givenName" | "middleName" | "familyName" | "suffix";

interface NameField {
  id: NameFieldId;
  label: string;       // already localized
  required: boolean;
  maxLength: number;
}

/**
 * CLDR surnameFirst locales (non-exhaustive; extend from CLDR supplemental data).
 * Source: CLDR PersonName data, surnameFirst ordering locales.
 */
const SURNAME_FIRST_LOCALES = new Set([
  "ja", "zh", "zh-Hant", "ko", "hu", "vi", "km", "lo", "my",
  "si", "th", "mn", "am", "ti",
]);

function isSurnameFirst(locale: string): boolean {
  const lang = locale.split("-")[0];
  return SURNAME_FIRST_LOCALES.has(locale) || SURNAME_FIRST_LOCALES.has(lang);
}

const NAME_LABELS: Record<NameFieldId, Record<string, string>> = {
  honorific:  { en: "Title", ja: "敬称", ko: "호칭", de: "Anrede", fr: "Civilité" },
  givenName:  { en: "First name", ja: "名", ko: "이름", de: "Vorname", fr: "Prénom" },
  middleName: { en: "Middle name", ja: "ミドルネーム", ko: "중간 이름", de: "Zweiter Vorname", fr: "Deuxième prénom" },
  familyName: { en: "Last name", ja: "姓", ko: "성", de: "Nachname", fr: "Nom de famille" },
  suffix:     { en: "Suffix", ja: "称号", ko: "칭호", de: "Namenszusatz", fr: "Suffixe" },
};

function localizedLabel(field: NameFieldId, locale: string): string {
  const lang = locale.split("-")[0];
  return NAME_LABELS[field][locale]
    ?? NAME_LABELS[field][lang]
    ?? NAME_LABELS[field]["en"];
}

export function buildNameSchema(locale: string): NameField[] {
  const surnameFirst = isSurnameFirst(locale);

  // Base Western order
  const westernOrder: NameFieldId[] = ["honorific", "givenName", "middleName", "familyName"];

  // Surname-first order; middle name is rare in these locales
  const surnameFirstOrder: NameFieldId[] = ["honorific", "familyName", "givenName"];

  const order = surnameFirst ? surnameFirstOrder : westernOrder;

  return order.map((id) => ({
    id,
    label: localizedLabel(id, locale),
    required: id === "givenName" || id === "familyName",
    maxLength: id === "middleName" ? 50 : 100,
  }));
}
```

---

## Address Field Order by Locale

Postal address field ordering follows CLDR's `postalCodeData` and address format strings.
Simplified mapping for the most common patterns:

```typescript
// src/lib/address-schema.ts

export type AddressFieldId =
  | "country" | "administrativeArea" | "locality"
  | "dependentLocality" | "postalCode" | "sortingCode"
  | "addressLine1" | "addressLine2" | "organization" | "recipient";

interface AddressField {
  id: AddressFieldId;
  label: string;
  required: boolean;
  hidden: boolean;
}

/**
 * CLDR-derived address formats (abbreviated).
 * Format string tokens: N=name, O=org, A=address lines, D=dependent locality,
 * C=city, S=admin area, Z=postal code, X=sorting code, R=country
 */
const ADDRESS_FORMATS: Record<string, AddressFieldId[]> = {
  // United States
  US: ["recipient", "organization", "addressLine1", "addressLine2", "locality", "administrativeArea", "postalCode", "country"],
  // Japan: postal code → prefecture → city → address → recipient
  JP: ["postalCode", "administrativeArea", "locality", "dependentLocality", "addressLine1", "organization", "recipient", "country"],
  // Germany: recipient → org → street → postal code + city → country
  DE: ["recipient", "organization", "addressLine1", "addressLine2", "postalCode", "locality", "country"],
  // South Korea: country → province → city → district → detail → org → recipient
  KR: ["country", "administrativeArea", "locality", "dependentLocality", "addressLine1", "organization", "recipient", "postalCode"],
  // Brazil includes sortingCode
  BR: ["recipient", "organization", "addressLine1", "addressLine2", "locality", "administrativeArea", "postalCode", "country"],
  // Default fallback
  DEFAULT: ["recipient", "organization", "addressLine1", "addressLine2", "locality", "administrativeArea", "postalCode", "country"],
};

// Fields not used in a given country format are hidden, not removed,
// so the client can still collect them if needed for shipping APIs.
const FIELD_LABELS: Partial<Record<AddressFieldId, Record<string, string>>> = {
  postalCode:          { en: "Postal code", US: "ZIP code", JP: "郵便番号", DE: "Postleitzahl", KR: "우편번호" },
  administrativeArea:  { en: "State / Province", US: "State", JP: "都道府県", DE: "Bundesland", KR: "시/도" },
  locality:            { en: "City", JP: "市区町村", DE: "Stadt", KR: "시/군/구" },
  dependentLocality:   { en: "District", JP: "町名・番地", KR: "읍/면/동" },
};

export function buildAddressSchema(locale: string, countryCode: string): AddressField[] {
  const format = ADDRESS_FORMATS[countryCode] ?? ADDRESS_FORMATS.DEFAULT;
  const formatSet = new Set(format);
  const allFields = Object.keys(ADDRESS_FORMATS.DEFAULT) as AddressFieldId[];

  return format.map((id) => {
    const labelMap = FIELD_LABELS[id] ?? {};
    const label = labelMap[countryCode] ?? labelMap[locale.split("-")[0]] ?? labelMap["en"] ?? id;
    return {
      id,
      label,
      required: ["addressLine1", "locality", "postalCode", "country"].includes(id),
      hidden: false,
    };
  }).concat(
    allFields
      .filter((id) => !formatSet.has(id))
      .map((id) => ({ id, label: id, required: false, hidden: true })),
  );
}
```

---

## Workers Endpoint — Form Schema API

```typescript
// src/worker.ts

import { buildNameSchema } from "./lib/name-schema";
import { buildAddressSchema } from "./lib/address-schema";

export default {
  async fetch(request: Request): Promise<Response> {
    const url = new URL(request.url);
    const pathParts = url.pathname.split("/").filter(Boolean);

    // GET /form-schema/:formType?locale=ja-JP&country=JP
    if (pathParts[0] === "form-schema" && pathParts[1]) {
      const formType = pathParts[1];
      const locale = url.searchParams.get("locale")
        ?? request.headers.get("Accept-Language")?.split(",")[0]?.trim()
        ?? "en";
      const country = url.searchParams.get("country")
        ?? (request as any).cf?.country
        ?? "US";

      let schema: unknown;

      if (formType === "name") {
        schema = buildNameSchema(locale);
      } else if (formType === "address") {
        schema = buildAddressSchema(locale, country);
      } else if (formType === "registration") {
        schema = {
          name: buildNameSchema(locale),
          address: buildAddressSchema(locale, country),
        };
      } else {
        return new Response("Unknown form type", { status: 400 });
      }

      return new Response(JSON.stringify(schema), {
        headers: {
          "Content-Type": "application/json",
          "Cache-Control": "public, max-age=3600",
          Vary: "Accept-Language",
        },
      });
    }

    return new Response("Not Found", { status: 404 });
  },
};
```

---

## Anti-patterns

- **Hard-coding field order in React/Vue components** — any locale change forces a
  front-end release; a schema API lets you update ordering without touching the client.
- **Using a single "Full name" field globally** — this breaks machine-readability and
  address-printing for locales that need given/family name as separate fields.
- **Dropping fields rather than hiding them** — shipping APIs often require a structured
  full address even if local convention omits a field; mark fields `hidden: true` and let
  the client decide whether to surface them.
- **Inferring country from locale alone** — `fr` is spoken in France, Belgium, Canada,
  and Switzerland, each with a different address format; always collect country separately.

---

## Gotchas

- `cf.country` on the `request.cf` object reflects the visitor's IP geolocation, not their
  shipping destination; do not auto-select address country from it — use it only as a
  default suggestion.
- Hungarian (`hu`) is `givenFirst` in modern CLDR despite the traditional surname-first
  convention; verify your CLDR version before encoding it.
- South Korea changed postal code format from 6-digit to 5-digit in 2015; validate the
  format with `/^\d{5}$/` for `KR`, not `/^\d{6}$/`.
- Japanese postal codes use a hyphen: `〒123-4567`; strip the `〒` prefix before
  submitting to APIs.

---

## Verification

```bash
# Name schema — Japanese (surname-first expected)
curl "http://localhost:8787/form-schema/name?locale=ja-JP&country=JP" | jq '.[].id'
# Expected: "honorific", "familyName", "givenName"

# Name schema — English (given-first expected)
curl "http://localhost:8787/form-schema/name?locale=en-US&country=US" | jq '.[].id'
# Expected: "honorific", "givenName", "middleName", "familyName"

# Address schema — Japan
curl "http://localhost:8787/form-schema/address?locale=ja-JP&country=JP" | jq '[.[] | select(.hidden==false) | .id]'
# Expected first field: "postalCode"

# Address schema — USA
curl "http://localhost:8787/form-schema/address?locale=en-US&country=US" | jq '[.[] | select(.hidden==false) | .id]'
# Expected first field: "recipient"
```

---

## Related

- `international-address-2026.md`
- `personal-name-formatting-2026.md`
- `locale-aware-input-validation.md`
- `locale-negotiation-accept-language.md`
- `cloudflare-workers-geolocation-locale-routing.md`

---

## Sources

- <https://cldr.unicode.org/index/cldr-spec/person-names>
- <https://github.com/google/libaddressinput/wiki/AddressValidationMetadata>
- <https://developers.cloudflare.com/workers/runtime-apis/request/#incomingrequestcfproperties>
- <https://unicode-org.github.io/cldr-staging/charts/latest/supplemental/territory_info.html>
