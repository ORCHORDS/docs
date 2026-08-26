# TCF 2.2 Consent String Parsing and Enforcement

- **Date**: 2026-08-22
- **Author**: example.com
- **Status**: production

---

## Symptom / Use-case

Your site runs an IAB Europe Transparency and Consent Framework (TCF) 2.2–registered Consent Management Platform (CMP). The CMP writes a `euconsent-v2` cookie containing a Base64url-encoded consent string. Your Cloudflare Workers need to: (a) read and parse that string server-side to gate analytics pixels and personalisation scripts before they fire, (b) forward the parsed consent signal to downstream ad-tech vendors that require it, and (c) maintain an audit trail for GDPR Article 7(1) accountability. Without server-side enforcement, a race condition between the CMP JavaScript loading and third-party scripts allows tracking before consent is confirmed.

---

## Context

The TCF 2.2 (approved by the IAB Europe Board in April 2023 and entered into force August 2023 following the Belgian APD consent order) defines a binary consent string format that encodes:

- **TC String version** (field: 6 bits, currently `2`)
- **Created / LastUpdated** timestamps (36 bits each, in deciseconds since epoch)
- **CmpId** — the registered CMP identifier (12 bits)
- **CmpVersion** — version of the CMP that produced the string (12 bits)
- **ConsentScreen** — which screen the user saw (6 bits)
- **ConsentLanguage** — ISO 639-1 two-letter code (12 bits)
- **VendorListVersion** — the Global Vendor List version in use (12 bits)
- **TcfPolicyVersion** — must be `4` for TCF 2.2 (6 bits)
- **IsServiceSpecific** — whether this string is for a single publisher (1 bit)
- **PurposeConsents** — 24-bit bitfield for IAB purposes 1–24
- **PurposeLegitimateInterests** — 24-bit bitfield
- **PurposeOneTreatment** — whether Purpose 1 (personalisation) was given special treatment (1 bit)
- **VendorConsents** — variable-length bitfield of consented vendor IDs
- **VendorLegitimateInterests** — variable-length bitfield
- **PublisherRestrictions** — optional list of publisher-imposed purpose restrictions per vendor

Parsing the TC String without a library requires careful bit manipulation because the format is a packed binary stream encoded as Base64url without padding.

Under TCF 2.2, Purpose 1 (Store and/or access information on a device) **requires** explicit opt-in consent — legitimate interest is not a valid basis. This was the central issue in the Belgian APD's January 2022 IAB Europe decision.

---

## TC String Parsing in a Cloudflare Worker

### 4.1 Base64url Decode and Bit Extraction

```typescript
// src/tcf/parse.ts

export interface TcString {
  version: number;
  created: Date;
  lastUpdated: Date;
  cmpId: number;
  cmpVersion: number;
  consentLanguage: string;
  vendorListVersion: number;
  tcfPolicyVersion: number;
  isServiceSpecific: boolean;
  purposeConsents: Set<number>;      // Purpose IDs 1-24 where user gave consent
  purposeLegitimateInterests: Set<number>;
  vendorConsents: Set<number>;       // Vendor IDs where user gave consent
  vendorLegitimateInterests: Set<number>;
}

/** Decode a Base64url string (no-padding) to Uint8Array */
function base64urlToBytes(s: string): Uint8Array {
  // Restore standard Base64 padding
  const padded = s.replace(/-/g, '+').replace(/_/g, '/');
  const withPad = padded + '==='.slice(0, (4 - (padded.length % 4)) % 4);
  const binary = atob(withPad);
  return Uint8Array.from(binary, c => c.charCodeAt(0));
}

class BitReader {
  private bytes: Uint8Array;
  private pos = 0; // current bit position

  constructor(bytes: Uint8Array) {
    this.bytes = bytes;
  }

  readBits(n: number): number {
    let result = 0;
    for (let i = 0; i < n; i++) {
      const byteIndex = Math.floor(this.pos / 8);
      const bitIndex  = 7 - (this.pos % 8);
      const bit = (this.bytes[byteIndex] >> bitIndex) & 1;
      result = (result << 1) | bit;
      this.pos++;
    }
    return result;
  }

  readBool(): boolean {
    return this.readBits(1) === 1;
  }

  /** Deciseconds since 1 Jan 1970 — used for Created / LastUpdated */
  readDeciSecondDate(): Date {
    const deci = this.readBits(36);
    return new Date(deci * 100);
  }

  readString(charCount: number): string {
    let out = '';
    for (let i = 0; i < charCount; i++) {
      const code = this.readBits(6) + 65; // 'A' = 0
      out += String.fromCharCode(code);
    }
    return out;
  }

  readBitfieldSet(size: number): Set<number> {
    const set = new Set<number>();
    for (let i = 1; i <= size; i++) {
      if (this.readBool()) set.add(i);
    }
    return set;
  }

  readVendorSet(): Set<number> {
    const maxVendorId = this.readBits(16);
    const isRangeEncoding = this.readBool();
    if (!isRangeEncoding) {
      return this.readBitfieldSet(maxVendorId);
    }
    // Range encoding
    const set = new Set<number>();
    const numEntries = this.readBits(12);
    for (let i = 0; i < numEntries; i++) {
      const isRange = this.readBool();
      const startId = this.readBits(16);
      if (isRange) {
        const endId = this.readBits(16);
        for (let v = startId; v <= endId; v++) set.add(v);
      } else {
        set.add(startId);
      }
    }
    return set;
  }
}

export function parseTcString(rawCookie: string): TcString | null {
  // TCF cookies may contain multiple segments separated by '.'
  // Only the first segment is the Core TC String
  const coreSegment = rawCookie.split('.')[0];
  try {
    const bytes = base64urlToBytes(coreSegment);
    const r = new BitReader(bytes);

    const version = r.readBits(6);
    if (version !== 2) {
      console.warn(`Unexpected TC String version: ${version}`);
      return null;
    }

    const created     = r.readDeciSecondDate();
    const lastUpdated = r.readDeciSecondDate();
    const cmpId       = r.readBits(12);
    const cmpVersion  = r.readBits(12);
    /* consentScreen */  r.readBits(6);
    const consentLanguage   = r.readString(2);
    const vendorListVersion = r.readBits(12);
    const tcfPolicyVersion  = r.readBits(6);
    /* isServiceSpecific */
    const isServiceSpecific = r.readBool();
    /* useNonStandardStacks */ r.readBool();
    /* specialFeatureOptIns */ r.readBits(12);
    const purposeConsents            = r.readBitfieldSet(24);
    const purposeLegitimateInterests = r.readBitfieldSet(24);
    /* purposeOneTreatment */  r.readBool();
    /* publisherCC */ r.readString(2);

    const vendorConsents            = r.readVendorSet();
    const vendorLegitimateInterests = r.readVendorSet();

    return {
      version, created, lastUpdated,
      cmpId, cmpVersion, consentLanguage,
      vendorListVersion, tcfPolicyVersion,
      isServiceSpecific,
      purposeConsents, purposeLegitimateInterests,
      vendorConsents, vendorLegitimateInterests,
    };
  } catch (err) {
    console.error('Failed to parse TC String:', err);
    return null;
  }
}
```

---

## Enforcement Middleware in a Worker

Gate downstream requests based on parsed consent. Purposes used most commonly:

| ID | Purpose (IAB) |
|---|---|
| 1  | Store and/or access information on a device (cookies) |
| 3  | Create a personalised ads profile |
| 4  | Select personalised ads |
| 7  | Measure ad performance |
| 8  | Measure content performance |
| 9  | Apply market research to generate audience insights |
| 10 | Develop and improve products |

```typescript
// src/consent-middleware.ts
import { parseTcString, TcString } from './tcf/parse';

const REQUIRED_PURPOSES_FOR_ANALYTICS = [1, 8, 10];
const REQUIRED_PURPOSES_FOR_ADS       = [1, 3, 4];

export interface ConsentGate {
  analyticsAllowed: boolean;
  adsAllowed: boolean;
  tcString: TcString | null;
}

export function evaluateConsent(request: Request): ConsentGate {
  const cookieHeader = request.headers.get('cookie') ?? '';
  const tcRaw = parseCookie(cookieHeader, 'euconsent-v2');

  if (!tcRaw) {
    return { analyticsAllowed: false, adsAllowed: false, tcString: null };
  }

  const tc = parseTcString(tcRaw);
  if (!tc) {
    return { analyticsAllowed: false, adsAllowed: false, tcString: null };
  }

  // Validate policy version — must be 4 for TCF 2.2
  if (tc.tcfPolicyVersion !== 4) {
    console.warn(`Stale TC String: policy version ${tc.tcfPolicyVersion}`);
    return { analyticsAllowed: false, adsAllowed: false, tcString: tc };
  }

  // Purpose 1 must be consent, never LI (TCF 2.2 requirement)
  const purposeOneConsented = tc.purposeConsents.has(1);

  const analyticsAllowed = purposeOneConsented &&
    REQUIRED_PURPOSES_FOR_ANALYTICS.every(p => tc.purposeConsents.has(p));

  const adsAllowed = purposeOneConsented &&
    REQUIRED_PURPOSES_FOR_ADS.every(p => tc.purposeConsents.has(p));

  return { analyticsAllowed, adsAllowed, tcString: tc };
}

function parseCookie(header: string, name: string): string | null {
  for (const pair of header.split(';')) {
    const [k, v] = pair.trim().split('=');
    if (k === name) return decodeURIComponent(v ?? '');
  }
  return null;
}

// Usage in main fetch handler
export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const { analyticsAllowed, adsAllowed, tcString } = evaluateConsent(request);

    // Mutate response headers to signal consent to downstream scripts
    const response = await fetch(request);
    const mutated = new Response(response.body, response);

    mutated.headers.set('X-Consent-Analytics', analyticsAllowed ? '1' : '0');
    mutated.headers.set('X-Consent-Ads',       adsAllowed       ? '1' : '0');

    // Audit log — record signal per request (sample 1 % in high traffic)
    if (Math.random() < 0.01 && tcString) {
      await env.CONSENT_AUDIT.put(
        `consent:${Date.now()}:${crypto.randomUUID()}`,
        JSON.stringify({
          cmpId: tcString.cmpId,
          vendorListVersion: tcString.vendorListVersion,
          purposeConsents: [...tcString.purposeConsents],
          analyticsAllowed,
          adsAllowed,
          ts: new Date().toISOString(),
        }),
        { expirationTtl: 60 * 60 * 24 * 90 } // 90-day KV TTL
      );
    }

    return mutated;
  }
};
```

---

## Consent Audit Trail for GDPR Article 7(1)

GDPR Article 7(1) requires that the controller be able to demonstrate that the data subject has consented. For TCF this means persisting the TC String (or a hash of it) at the time of collection alongside the purpose bitmap and CMP metadata.

```typescript
// src/tcf/audit.ts
export async function recordConsentEvidence(
  env: Env,
  userId: string,
  tcString: TcString,
  rawTcCookie: string
): Promise<void> {
  const evidence = {
    userId,
    cmpId: tcString.cmpId,
    cmpVersion: tcString.cmpVersion,
    vendorListVersion: tcString.vendorListVersion,
    tcfPolicyVersion: tcString.tcfPolicyVersion,
    consentLanguage: tcString.consentLanguage,
    purposeConsents: [...tcString.purposeConsents].sort(),
    vendorConsents: [...tcString.vendorConsents].sort(),
    created: tcString.created.toISOString(),
    lastUpdated: tcString.lastUpdated.toISOString(),
    // Hash the raw cookie for integrity; never store raw string in some jurisdictions
    tcStringHash: await hashSha256(rawTcCookie),
    recordedAt: new Date().toISOString(),
  };

  await env.CONSENT_AUDIT_DB.prepare(`
    INSERT INTO consent_records
      (user_id, cmp_id, vendor_list_version, tcf_policy_version,
       purpose_consents_json, vendor_consents_count,
       tc_string_hash, consent_date, recorded_at)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
  `).bind(
    evidence.userId,
    evidence.cmpId,
    evidence.vendorListVersion,
    evidence.tcfPolicyVersion,
    JSON.stringify(evidence.purposeConsents),
    evidence.vendorConsents.length,
    evidence.tcStringHash,
    evidence.lastUpdated,
  ).run();
}

async function hashSha256(input: string): Promise<string> {
  const buf = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(input));
  return Array.from(new Uint8Array(buf)).map(b => b.toString(16).padStart(2,'0')).join('');
}
```

---

## Anti-patterns

- **Client-side-only enforcement.** A CMP that only gates scripts after its own JS loads introduces a race condition — a fast network may fire a tracking pixel before the CMP's `addEventListener('CmpApiUi', ...)` callback runs. Server-side enforcement in a Worker eliminates this gap.
- **Treating an absent `euconsent-v2` cookie as implicit consent.** Absence of the cookie means the CMP has not yet shown the UI or the user has rejected. Default to `analyticsAllowed = false`.
- **Using LI (legitimate interest) as the basis for Purpose 1.** The Belgian APD's binding decision (January 2022) and TCF 2.2 specification explicitly prohibit legitimate interest for Purpose 1. Any code that falls back to `purposeLegitimateInterests.has(1)` if consent is denied is non-compliant.
- **Not validating `tcfPolicyVersion === 4`.** A TC String with `tcfPolicyVersion < 4` was produced by a TCF 2.0 or 2.1 CMP and does not satisfy the TCF 2.2 requirements for the new stack.
- **Forwarding the raw TC String to CDN third parties without checking their vendor registration.** Only forward the TC String to vendors that are on the IAB Global Vendor List and whose ID appears in the parsed `vendorConsents` set.

---

## Gotchas

- **Legitimate Interest Signals (LIS) segment.** TCF 2.2 strings may include a `DisclosedVendors` segment and a `PublisherTC` segment after the core segment (separated by `.`). The enforcement worker should parse only the core segment unless a publisher-level override is required.
- **The Global Vendor List updates weekly.** Hard-coding vendor IDs in your enforcement logic will drift. Fetch the GVL from `https://vendorlist.consensu.org/v3/vendor-list.json` via a scheduled Worker and cache in KV for lookup.
- **`isServiceSpecific = false` means the string was created in the Global context.** If your site uses a site-specific consent scope, you must check that `isServiceSpecific = true`; otherwise the string may have been created on a different publisher's site.
- **The CMP must refresh the TC String when the user changes consent in a subsequent session.** Stale strings (checked via `lastUpdated`) that are older than your consent refresh policy (commonly 13 months for GDPR) should be treated as expired and trigger a new CMP UI display.

---

## Verification

```bash
# 1. Decode a sample TC String manually
node -e "
const s = 'CPXxRfAPXxRfAAfKABENB-CgAAAAAAAAAAAAAAAA'; // sample
const b = Buffer.from(s.replace(/-/g,'+').replace(/_/g,'/'), 'base64');
console.log('Version bits (first 6):', (b[0] >> 2) & 0x3F);
"

# 2. Run the Worker locally and test with a known TC String
npx wrangler dev --local
curl -H 'Cookie: euconsent-v2=CPXxRfAPXxRfAAfKABENB-CgAAAAAAAAAAAAAAAA' \
  http://localhost:8787/ -I | grep X-Consent

# 3. Validate your CMP is TCF 2.2 registered
curl -s 'https://cmplist.consensu.org/v3/cmp-list.json' | jq '.cmps["YOUR_CMP_ID"]'

# 4. Check purpose consents for a given TC String using a reference library
npx @iabtcf/core decode CPXxRfAPXxRfAAfKABENB-CgAAAAAAAAAAAAAAAA
```

---

## Related

- `cookie-consent-cloudflare-pages-workers.md` — full cookie consent banner implementation
- `gdpr-consent-management-cloudflare-workers.md` — GDPR consent management using Workers
- `gdpr-lawful-basis-workers-d1-consent.md` — persisting lawful basis records

---

## Sources

- IAB Europe TCF 2.2 Specification — https://iabeurope.eu/tcf-2-2/
- IAB Europe Global Vendor List v3 — https://vendorlist.consensu.org/v3/vendor-list.json
- Belgian APD decision against IAB Europe (February 2022, Case: DOS-2022-01349)
- @iabtcf/core npm package — reference TCF string implementation
- GDPR Article 7 — Conditions for consent
- EDPB Guidelines 05/2020 on consent
- Cloudflare Workers Cookie parsing — https://developers.cloudflare.com/workers/examples/extract-cookie-value/
