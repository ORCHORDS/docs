# GDPR Pseudonymization vs Anonymization — Technical Controls in Workers + D1

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

You want to reduce GDPR obligations on analytics, test data, or archival records, but are unsure whether your implementation produces pseudonymous data (still personal data, fewer obligations) or anonymous data (outside GDPR entirely). You need:

- A deterministic pseudonymization scheme using HMAC-keyed tokens stored in D1.
- Anonymization that satisfies the WP29 / EDPB three-part test (singling out, linkability, inference).
- Separate handling for analytics pipelines vs. legal hold archives.
- Re-identification controls that meet Article 25 (data protection by design).

---

## Context

**Pseudonymization** (GDPR Art. 4(5)): processing that replaces directly identifying fields with a reversible token; the mapping key is held separately. The data remains personal data but qualifies for reduced-risk treatment under Art. 89 (research/statistics) and Recital 28.

**Anonymization**: processing that irreversibly prevents identification by the controller or any reasonably likely third party. Properly anonymized data falls outside GDPR scope entirely. The WP29 Opinion 05/2014 requires surviving the **singling-out**, **linkability**, and **inference** tests.

Common mistake: calling a SHA-256 hash of an email "anonymized." Hashes of low-entropy values are re-identifiable by brute force — they are pseudonymization, not anonymization.

---

## 1. HMAC Pseudonymization Utility

```typescript
// lib/pseudonymize.ts
export async function pseudonymize(
  value: string,
  secret: string // store in Workers secret, never in D1
): Promise<string> {
  const key = await crypto.subtle.importKey(
    "raw",
    new TextEncoder().encode(secret),
    { name: "HMAC", hash: "SHA-256" },
    false,
    ["sign"]
  );
  const sig = await crypto.subtle.sign(
    "HMAC",
    key,
    new TextEncoder().encode(value)
  );
  return btoa(String.fromCharCode(...new Uint8Array(sig)))
    .replace(/\+/g, "-")
    .replace(/\//g, "_")
    .replace(/=+$/, ""); // URL-safe base64
}

// Reverse lookup requires the original value (store mapping for legal holds)
export async function storePseudonymMapping(
  plaintext: string,
  token: string,
  db: D1Database,
  retainUntil: string // ISO date — for legal hold / erasure scheduling
): Promise<void> {
  await db
    .prepare(
      `INSERT OR IGNORE INTO pseudonym_map
         (token, plaintext_encrypted, retain_until, created_at)
       VALUES (?, ?, ?, datetime('now'))`
    )
    .bind(token, encrypt(plaintext), retainUntil) // encrypt() wraps AES-GCM
    .run();
}

// Placeholder — replace with your AES-GCM envelope encryption
function encrypt(plaintext: string): string {
  return Buffer.from(plaintext).toString("base64"); // MUST use real encryption
}
```

---

## 2. D1 Schema — Pseudonymization Infrastructure

```sql
-- migrations/0001_pseudonymization.sql

-- Pseudonym-to-plaintext mapping (held separately from analytics tables)
CREATE TABLE IF NOT EXISTS pseudonym_map (
  token             TEXT PRIMARY KEY,
  plaintext_encrypted TEXT NOT NULL,  -- AES-GCM envelope encrypted
  retain_until      TEXT NOT NULL,    -- ISO date for scheduled deletion
  created_at        TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX idx_pseudonym_retain ON pseudonym_map(retain_until);

-- Analytics table uses tokens only — no raw PII
CREATE TABLE IF NOT EXISTS page_views_analytics (
  id              INTEGER PRIMARY KEY AUTOINCREMENT,
  user_token      TEXT NOT NULL,  -- HMAC pseudonym of user_id
  path            TEXT NOT NULL,
  occurred_at     TEXT NOT NULL DEFAULT (datetime('now')),
  country_code    TEXT,           -- generalised to country (not IP)
  device_type     TEXT            -- coarse: mobile / desktop / bot
);

-- Scheduled deletion of expired mappings (GDPR Art. 17 + Art. 89)
-- Run via cron trigger
CREATE TABLE IF NOT EXISTS pseudonym_deletion_log (
  deleted_at    TEXT NOT NULL DEFAULT (datetime('now')),
  token_prefix  TEXT NOT NULL,  -- first 8 chars only (not re-identifiable)
  reason        TEXT NOT NULL
);
```

---

## 3. Anonymization Pipeline — WP29 Three-Part Test

```typescript
// lib/anonymize.ts
/**
 * Applies k-anonymity-inspired generalization to a user record.
 * After this transform the record must survive:
 *   1. Singling-out: no combination of fields uniquely identifies 1 person.
 *   2. Linkability: fields cannot be joined to re-identify across tables.
 *   3. Inference: remaining fields do not allow probabilistic re-identification.
 */
export interface RawUserRecord {
  email: string;
  ip: string;
  birthDate: string; // "YYYY-MM-DD"
  postcode: string;
  profession: string;
  purchaseAmount: number;
}

export interface AnonymizedRecord {
  ageRange: string;       // "25-34" not exact DOB
  regionCode: string;     // first 3 chars of postcode
  professionCategory: string; // broad SIC-like category
  purchaseBand: string;   // "0-50", "51-200", "201+"
}

export function anonymizeRecord(raw: RawUserRecord): AnonymizedRecord {
  const year = new Date().getFullYear();
  const birthYear = parseInt(raw.birthDate.split("-")[0], 10);
  const age = year - birthYear;
  const ageRange =
    age < 18 ? "<18" :
    age < 25 ? "18-24" :
    age < 35 ? "25-34" :
    age < 45 ? "35-44" :
    age < 55 ? "45-54" : "55+";

  const band =
    raw.purchaseAmount <= 50 ? "0-50" :
    raw.purchaseAmount <= 200 ? "51-200" : "201+";

  return {
    ageRange,
    regionCode: raw.postcode.slice(0, 3).toUpperCase(),
    professionCategory: broadenProfession(raw.profession),
    purchaseBand: band,
  };
}

function broadenProfession(profession: string): string {
  const p = profession.toLowerCase();
  if (p.includes("engineer") || p.includes("developer")) return "technology";
  if (p.includes("nurse") || p.includes("doctor")) return "healthcare";
  if (p.includes("teacher") || p.includes("professor")) return "education";
  return "other";
}
```

---

## 4. Analytics Write Path — Pseudonym, Never Raw PII

```typescript
// workers/track-event.ts
export interface Env {
  DB: D1Database;
  PSEUDONYM_SECRET: string; // Workers secret
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const { userId, path, country, deviceType } = await request.json<{
      userId: string;
      path: string;
      country: string;
      deviceType: string;
    }>();

    // Pseudonymize — NEVER store raw userId in analytics table
    const userToken = await pseudonymize(userId, env.PSEUDONYM_SECRET);

    await env.DB.prepare(
      `INSERT INTO page_views_analytics
         (user_token, path, country_code, device_type, occurred_at)
       VALUES (?, ?, ?, ?, datetime('now'))`
    )
      .bind(userToken, path, country.slice(0, 2).toUpperCase(), deviceType)
      .run();

    return new Response(null, { status: 204 });
  },
};

// Imported from lib/pseudonymize.ts
async function pseudonymize(value: string, secret: string): Promise<string> {
  const key = await crypto.subtle.importKey(
    "raw",
    new TextEncoder().encode(secret),
    { name: "HMAC", hash: "SHA-256" },
    false,
    ["sign"]
  );
  const sig = await crypto.subtle.sign("HMAC", key, new TextEncoder().encode(value));
  return btoa(String.fromCharCode(...new Uint8Array(sig)))
    .replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}
```

---

## 5. Expired Pseudonym Map Deletion (Cron Trigger)

```typescript
// workers/pseudonym-cleanup.ts — scheduled: "0 2 * * *"
export default {
  async scheduled(_event: ScheduledEvent, env: Env): Promise<void> {
    // Fetch tokens expiring today or earlier
    const { results } = await env.DB.prepare(
      `SELECT token FROM pseudonym_map WHERE retain_until <= date('now')`
    ).all<{ token: string }>();

    for (const { token } of results) {
      await env.DB.prepare(
        "DELETE FROM pseudonym_map WHERE token = ?"
      )
        .bind(token)
        .run();

      await env.DB.prepare(
        `INSERT INTO pseudonym_deletion_log (token_prefix, reason)
         VALUES (?, 'retain_until_expired')`
      )
        .bind(token.slice(0, 8))
        .run();
    }

    console.log(`[PSEUDONYM-CLEANUP] Deleted ${results.length} expired mappings`);
  },
};
```

---

## Anti-patterns

- **SHA-256 of email as "anonymization"**: Email hashes are brute-forceable in seconds with rainbow tables — this is pseudonymization at best, de facto identifiable in practice.
- **Storing the mapping table in the same D1 database as analytics**: Physical separation is required; a breach of the analytics DB must not expose the mapping.
- **Using the same HMAC key across all data types**: Compromise of one mapping reveals all pseudonyms; use separate secrets per data category.
- **Generalizing only one field**: k-anonymity requires *all* quasi-identifiers to be generalized simultaneously — generalizing DOB but not postcode is insufficient.

---

## Gotchas

- **GDPR Art. 89 exemptions apply only to pseudonymized data**: Anonymized data needs no Art. 89 basis, but you bear the burden of proving anonymization meets the WP29 test.
- **Re-identification risk changes over time**: What is anonymous today may be re-identifiable in 5 years as auxiliary datasets grow — build a re-identification risk review schedule.
- **IP addresses are always personal data** under EU case law: Do not store full IPs in analytics tables even for short periods; truncate to /24 (IPv4) or /48 (IPv6) before storage.
- **Key rotation breaks pseudonym continuity**: If you rotate the HMAC secret, existing tokens no longer resolve; plan key rotation carefully and update the mapping table.

---

## Verification

```bash
# Confirm no raw emails or IPs in analytics table
wrangler d1 execute DB --command \
  "SELECT * FROM page_views_analytics LIMIT 5;"

# Check expired pseudonym mappings are cleaned
wrangler d1 execute DB --command \
  "SELECT COUNT(*) AS expired FROM pseudonym_map WHERE retain_until <= date('now');"

# Review deletion log
wrangler d1 execute DB --command \
  "SELECT * FROM pseudonym_deletion_log ORDER BY deleted_at DESC LIMIT 10;"
```

---

## Related

- `data-minimization-workers-d1-pii-redaction.md` — PII scrubbing at ingest
- `gdpr-right-to-erasure-d1-r2-pipeline.md` — Erasure of pseudonym maps on DSR
- `gdpr-data-retention-policy.md` — Retention schedules for pseudonymized data
- `privacy-enhancing-technologies-pets.md` — Differential privacy, k-anonymity

---

## Sources

- GDPR Art. 4(5) definition of pseudonymization: https://gdpr-info.eu/art-4-gdpr/
- GDPR Recital 26 (anonymization): https://gdpr-info.eu/recitals/no-26/
- WP29 Opinion 05/2014 on Anonymisation Techniques: https://ec.europa.eu/justice/article-29/documentation/opinion-recommendation/files/2014/wp216_en.pdf
- EDPB Guidelines 04/2022 on data subject rights: https://edpb.europa.eu/our-work-tools/our-documents/guidelines/guidelines-042022_en
- Cloudflare Workers Web Crypto API: https://developers.cloudflare.com/workers/runtime-apis/web-crypto/
