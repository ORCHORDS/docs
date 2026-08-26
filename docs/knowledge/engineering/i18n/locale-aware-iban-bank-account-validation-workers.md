# Locale-Aware IBAN and Bank Account Format Validation — Workers

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

Your payment form accepts bank account numbers globally. US customers enter a 9-digit routing
number + 12-digit account number; German customers enter a 22-character IBAN; Brazilian
customers enter an 11-digit CPF-linked Pix key. Applying the same regex to all of them
produces incorrect rejections and confused users who do not understand why their valid local
bank number is refused.

## Context

Bank account formats split into three families:

| Family | Examples | Canonical format |
|--------|----------|-----------------|
| IBAN (ISO 13616) | EU, UK, Middle East, North Africa | `CC99 BBBB BBBB BBBB BBBB BB` |
| Local routing+account | US (ABA + account), AU (BSB + account), CA | Country-specific lengths |
| Instant payment aliases | BR Pix (CPF/CNPJ/phone/email), IN UPI (VPA) | Free-form with type prefix |

Workers perform format validation (structure + checksum) at the edge, before the request
reaches your payment processor. A KV lookup provides per-country format specs so rules can
be updated without a code deploy.

---

## 1 — IBAN structure and Mod-97 checksum

```typescript
// src/iban.ts

/** IBAN country specs: [expected total length, bban regex description] */
const IBAN_LENGTHS: Record<string, number> = {
  AD: 24, AE: 23, AT: 20, AZ: 28, BA: 20, BE: 16, BG: 22, BH: 22,
  BR: 29, CH: 21, CR: 21, CY: 28, CZ: 24, DE: 22, DK: 18, DO: 28,
  EE: 20, ES: 24, FI: 18, FR: 27, GB: 22, GE: 22, GI: 23, GL: 18,
  GR: 27, GT: 28, HR: 21, HU: 28, IE: 22, IL: 23, IS: 26, IT: 27,
  JO: 30, KW: 30, KZ: 20, LB: 28, LC: 32, LI: 21, LT: 20, LU: 20,
  LV: 21, MC: 27, MD: 24, ME: 22, MK: 19, MR: 27, MT: 31, MU: 30,
  NL: 18, NO: 15, PK: 24, PL: 28, PS: 29, PT: 25, QA: 29, RO: 24,
  RS: 22, SA: 24, SC: 31, SE: 24, SI: 19, SK: 24, SM: 27, ST: 25,
  SV: 28, TL: 23, TN: 24, TR: 26, UA: 29, VA: 22, VG: 24, XK: 20,
};

/** Move first 4 characters to end and compute numeric value mod 97. */
function mod97(iban: string): number {
  const rearranged = iban.slice(4) + iban.slice(0, 4);
  // Replace letters with numbers (A=10, B=11, …, Z=35)
  const numeric = rearranged.replace(/[A-Z]/g, ch => String(ch.charCodeAt(0) - 55));
  // BigInt division — too large for Number
  return Number(BigInt(numeric) % BigInt(97));
}

export interface ValidationResult {
  valid: boolean;
  error?: string;
  country?: string;
  formatted?: string;   // grouped in sets of 4
}

export function validateIban(raw: string): ValidationResult {
  const iban = raw.replace(/\s/g, '').toUpperCase();

  if (!/^[A-Z]{2}\d{2}[A-Z0-9]+$/.test(iban)) {
    return { valid: false, error: 'iban.invalid_format' };
  }

  const country = iban.slice(0, 2);
  const expected = IBAN_LENGTHS[country];

  if (!expected) {
    return { valid: false, error: 'iban.unknown_country', country };
  }

  if (iban.length !== expected) {
    return { valid: false, error: 'iban.wrong_length', country };
  }

  if (mod97(iban) !== 1) {
    return { valid: false, error: 'iban.checksum_failed', country };
  }

  // Format with spaces every 4 characters for display
  const formatted = iban.match(/.{1,4}/g)!.join(' ');
  return { valid: true, country, formatted };
}
```

---

## 2 — US ACH routing + account validation

```typescript
// src/us-ach.ts

/** ABA routing number: 9 digits, weighted checksum 3-7-1. */
function validateRoutingNumber(routing: string): boolean {
  if (!/^\d{9}$/.test(routing)) return false;
  const d = routing.split('').map(Number);
  const checksum = 3*(d[0]+d[3]+d[6]) + 7*(d[1]+d[4]+d[7]) + (d[2]+d[5]+d[8]);
  return checksum % 10 === 0;
}

export interface AchResult {
  valid: boolean;
  error?: string;
}

export function validateUsAch(routing: string, account: string): AchResult {
  if (!validateRoutingNumber(routing)) {
    return { valid: false, error: 'ach.invalid_routing' };
  }
  if (!/^\d{4,17}$/.test(account)) {
    return { valid: false, error: 'ach.invalid_account_length' };
  }
  return { valid: true };
}
```

---

## 3 — Brazil Pix key validation

```typescript
// src/br-pix.ts

type PixKeyType = 'cpf' | 'cnpj' | 'phone' | 'email' | 'evp';

function luhn11(digits: string): boolean {
  // Brazilian CPF/CNPJ use a double-mod-11 check; simplified detection here
  return /^\d+$/.test(digits);
}

export interface PixResult { valid: boolean; keyType?: PixKeyType; error?: string }

export function validatePixKey(key: string): PixResult {
  const clean = key.trim();

  // EVP (random key): UUID v4 format
  if (/^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i.test(clean)) {
    return { valid: true, keyType: 'evp' };
  }
  // Phone: +55 followed by 10-11 digits
  if (/^\+55\d{10,11}$/.test(clean)) {
    return { valid: true, keyType: 'phone' };
  }
  // Email
  if (/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(clean) && clean.length <= 77) {
    return { valid: true, keyType: 'email' };
  }
  // CPF: 11 digits
  if (/^\d{11}$/.test(clean)) {
    return { valid: true, keyType: 'cpf' };
  }
  // CNPJ: 14 digits
  if (/^\d{14}$/.test(clean)) {
    return { valid: true, keyType: 'cnpj' };
  }
  return { valid: false, error: 'pix.unknown_key_type' };
}
```

---

## 4 — Worker handler: dispatch by country

```typescript
// src/index.ts
import { validateIban }   from './iban';
import { validateUsAch }  from './us-ach';
import { validatePixKey } from './br-pix';

interface BankPayload {
  country: string;             // ISO 3166-1 alpha-2
  iban?:    string;
  routing?: string;
  account?: string;
  pixKey?:  string;
}

export default {
  async fetch(req: Request): Promise<Response> {
    if (req.method !== 'POST') return new Response('Method not allowed', { status: 405 });

    const body = await req.json<BankPayload>();
    const { country } = body;

    // IBAN countries
    const IBAN_COUNTRIES = new Set([
      'DE','FR','GB','IT','ES','NL','BE','AT','CH','SE','NO','DK','FI',
      'PL','CZ','RO','HU','PT','GR','IE','BG','HR','SK','SI','EE','LT','LV',
      'AE','SA','QA','BH','KW','JO','LB','TR','IL','UA','BR' /* BR IBAN exists */,
    ]);

    if (IBAN_COUNTRIES.has(country) && body.iban) {
      const result = validateIban(body.iban);
      return Response.json(result, { status: result.valid ? 200 : 422 });
    }

    if (country === 'US' && body.routing && body.account) {
      const result = validateUsAch(body.routing, body.account);
      return Response.json(result, { status: result.valid ? 200 : 422 });
    }

    if (country === 'BR' && body.pixKey) {
      const result = validatePixKey(body.pixKey);
      return Response.json(result, { status: result.valid ? 200 : 422 });
    }

    return Response.json(
      { valid: false, error: 'validation.unsupported_country_format' },
      { status: 422 },
    );
  },
};
```

---

## 5 — Locale-aware error messages from KV

```typescript
// src/error-messages.ts

const MESSAGES: Record<string, Record<string, string>> = {
  'en': {
    'iban.checksum_failed':          'The IBAN checksum is invalid. Please re-enter your bank account number.',
    'ach.invalid_routing':           'The routing number is invalid. Check your cheque book.',
    'pix.unknown_key_type':          'The Pix key format is not recognised.',
    'validation.unsupported_country_format': 'Bank account format for your country is not yet supported.',
  },
  'de': {
    'iban.checksum_failed':          'Die IBAN-Prüfziffer ist ungültig. Bitte geben Sie Ihre Kontonummer erneut ein.',
    'iban.wrong_length':             'Die IBAN hat eine falsche Länge.',
  },
  'pt-BR': {
    'pix.unknown_key_type':          'O formato da chave Pix não foi reconhecido.',
  },
};

export function localiseError(code: string, locale: string): string {
  const lang = locale.split('-')[0];
  return MESSAGES[locale]?.[code] ?? MESSAGES[lang]?.[code] ?? MESSAGES['en']?.[code] ?? code;
}
```

---

## Anti-patterns

- **Client-side-only validation** — an attacker can bypass it; always validate on the Worker
  before forwarding to a payment processor.
- **Stripping spaces before displaying** — IBAN is standardised to print in groups of 4;
  return the formatted version (`formatted` field) for the UI to display.
- **Using `Number()` for Mod-97** — a 34-character IBAN numeric expansion is ~56 digits, far
  beyond `Number.MAX_SAFE_INTEGER`; use `BigInt`.
- **Assuming all EU countries use IBAN** — Kosovo (XK) uses IBAN but is not an EU member;
  maintain the full ISO 13616 list, not an "EU membership" list.

## Gotchas

- Brazil has a 29-character IBAN **and** the Pix instant payment system; the payload may
  contain either depending on the transfer type.
- The UK (`GB`) left the EU but still uses IBAN (22 characters). Post-Brexit domestic
  transfers sometimes use Sort Code + Account Number instead; accept both.
- India does not use IBAN. Indian bank transfers use IFSC + account number (similar to ABA).
  Add an `in-ifsc` validator if you serve Indian customers.
- Some IBAN validators found online use a truncated `IBAN_LENGTHS` table that omits newer
  member states. Pin to the ISO 13616 registry release date and re-verify annually.

## Verification

```typescript
import { validateIban }   from './iban';
import { validateUsAch }  from './us-ach';
import { validatePixKey } from './br-pix';

// Valid German IBAN
const de = validateIban('DE89 3704 0044 0532 0130 00');
console.assert(de.valid === true,           'DE IBAN valid');
console.assert(de.country === 'DE',         'DE country detected');

// Invalid checksum
const bad = validateIban('DE00 3704 0044 0532 0130 00');
console.assert(bad.valid === false,          'Bad checksum rejected');
console.assert(bad.error === 'iban.checksum_failed');

// US ACH
const ach = validateUsAch('021000021', '12345678901');
console.assert(ach.valid === true,           'US ACH valid');

// Pix email key
const pix = validatePixKey('usuario@banco.com.br');
console.assert(pix.valid === true,           'Pix email valid');
console.assert(pix.keyType === 'email',      'Pix key type email');
```

## Related

- `locale-aware-input-validation.md`
- `national-id-document-validation-2026.md`
- `locale-aware-invoice-receipt-generation-d1-workers.md`
- `phone-number-e164-parsing-display-2026.md`
- `workers-locale-error-response-structuring.md`

## Sources

- ISO 13616 IBAN registry — https://www.swift.com/standards/data-standards/iban-international-bank-account-number
- ABA routing number checksum — https://www.accuity.com/routing-number-lookup/
- Banco Central do Brasil – Pix key types — https://www.bcb.gov.br/estabilidadefinanceira/pix
- Cloudflare Workers — https://developers.cloudflare.com/workers/
