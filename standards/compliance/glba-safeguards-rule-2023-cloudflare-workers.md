# GLBA Safeguards Rule 2023: Financial Customer Data Protection with Cloudflare Workers, D1, and R2

**Date:** 2026-08-22
**Author:** example.com
**Status:** production

---

## Symptom / Use-Case

A fintech startup or BHPH dealership is building its customer data platform on Cloudflare Workers and D1. A bank partner or state regulator asks for evidence that the FTC's updated Gramm-Leach-Bliley Act (GLBA) Safeguards Rule — effective June 2023 — is implemented in your information security program. You need to translate the nine enumerated elements (16 CFR § 314) into concrete Workers architecture controls.

---

## Context

The **GLBA Safeguards Rule** (16 CFR Part 314, revised 2023) applies to **financial institutions** under FTC jurisdiction — mortgage brokers, auto dealers, payday lenders, tax preparers, non-bank financial services, and any company significantly engaged in financial activities. The 2023 update introduced prescriptive requirements previously absent:

- Designate a **qualified individual** (CISO or equivalent) responsible for the program.
- Conduct periodic **risk assessments** with written results.
- Implement **access controls**, including MFA for information systems.
- Encrypt **customer information** in transit and at rest.
- Develop, test, and implement a **change management** process.
- Monitor and test safeguards via **penetration testing** (annual) and **vulnerability scanning** (quarterly).
- Implement **event logging** and **anomaly detection**.
- Report to the board/equivalent body **annually**.
- Report qualifying security events to the FTC **within 30 days** (≥500 customers affected).

"Customer information" means nonpublic personal information (NPI) about customers who obtain financial products or services primarily for personal, family, or household purposes.

---

## Section 1 — NPI Inventory and Classification in D1

Before you can protect NPI, you must know where it lives. Tag all D1 tables that store NPI.

```sql
-- migrations/001_glba_schema.sql

-- Master NPI inventory view
CREATE TABLE data_inventory (
  table_name   TEXT NOT NULL,
  column_name  TEXT NOT NULL,
  npi_category TEXT NOT NULL CHECK(npi_category IN (
    'account_number','ssn','credit_score','income','transaction',
    'bank_routing','loan_terms','insurance','tax_return','contact'
  )),
  encrypted    INTEGER NOT NULL DEFAULT 1,  -- boolean: 1 = yes
  retention_days INTEGER NOT NULL,
  PRIMARY KEY (table_name, column_name)
);

-- Core customer financial records table
CREATE TABLE customer_accounts (
  id              TEXT PRIMARY KEY,
  customer_ref    TEXT NOT NULL,        -- opaque ID, not SSN
  encrypted_npi   TEXT NOT NULL,        -- AES-GCM blob
  account_type    TEXT NOT NULL,
  created_at      TEXT NOT NULL DEFAULT (datetime('now')),
  last_accessed_at TEXT,
  deleted_at      TEXT
);

-- Access event log (§ 314.4(h) monitoring requirement)
CREATE TABLE npi_access_log (
  id           TEXT PRIMARY KEY,
  table_name   TEXT NOT NULL,
  record_id    TEXT NOT NULL,
  accessor_id  TEXT NOT NULL,
  accessor_ip  TEXT,
  action       TEXT NOT NULL CHECK(action IN ('read','write','delete','export')),
  purpose      TEXT NOT NULL,
  accessed_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX idx_npi_log_record   ON npi_access_log(record_id, accessed_at);
CREATE INDEX idx_npi_log_accessor ON npi_access_log(accessor_id, accessed_at);
```

---

## Section 2 — Encryption at Rest with Application-Layer Key Management

GLBA requires encryption of NPI "in transit and at rest." D1's infrastructure encryption satisfies at-rest for the storage layer, but the Safeguards Rule's spirit — and any examiners' expectation — requires you to control the keys.

```typescript
// src/glba/crypto.ts
const KEY_ALGORITHM: AesKeyGenParams = { name: 'AES-GCM', length: 256 };

interface EncryptedBlob {
  iv: string;     // base64
  ct: string;     // base64 ciphertext
  keyId: string;  // for key rotation tracking
}

export async function encryptNpi(
  data: Record<string, unknown>,
  env: Env
): Promise<string> {
  const keyMaterial = Uint8Array.from(atob(env.GLBA_ENCRYPTION_KEY), c => c.charCodeAt(0));
  const cryptoKey = await crypto.subtle.importKey('raw', keyMaterial, KEY_ALGORITHM, false, ['encrypt']);
  const iv = crypto.getRandomValues(new Uint8Array(12));
  const encoded = new TextEncoder().encode(JSON.stringify(data));
  const ciphertext = await crypto.subtle.encrypt({ name: 'AES-GCM', iv }, cryptoKey, encoded);

  const blob: EncryptedBlob = {
    iv: btoa(String.fromCharCode(...iv)),
    ct: btoa(String.fromCharCode(...new Uint8Array(ciphertext))),
    keyId: env.GLBA_KEY_ID,  // e.g. "v3" — bump on rotation
  };
  return JSON.stringify(blob);
}

export async function decryptNpi(
  blobJson: string,
  env: Env
): Promise<Record<string, unknown>> {
  const blob: EncryptedBlob = JSON.parse(blobJson);
  if (blob.keyId !== env.GLBA_KEY_ID) {
    throw new Error(`Key rotation required: record uses key ${blob.keyId}, current key is ${env.GLBA_KEY_ID}`);
  }
  const keyMaterial = Uint8Array.from(atob(env.GLBA_ENCRYPTION_KEY), c => c.charCodeAt(0));
  const cryptoKey = await crypto.subtle.importKey('raw', keyMaterial, KEY_ALGORITHM, false, ['decrypt']);
  const iv = Uint8Array.from(atob(blob.iv), c => c.charCodeAt(0));
  const ct = Uint8Array.from(atob(blob.ct), c => c.charCodeAt(0));
  const plain = await crypto.subtle.decrypt({ name: 'AES-GCM', iv }, cryptoKey, ct);
  return JSON.parse(new TextDecoder().decode(plain));
}
```

---

## Section 3 — Multi-Factor Authentication Enforcement (§ 314.4(c)(2))

The 2023 rule explicitly requires MFA for any individual who accesses customer information. Enforce this at the Workers edge before any NPI read path.

```typescript
// src/glba/mfa-middleware.ts
interface MfaClaims {
  sub: string;
  role: string;
  mfa_verified: boolean;
  mfa_verified_at: number;   // Unix timestamp
  mfa_method: 'totp' | 'webauthn' | 'sms';
}

const MFA_MAX_AGE_SECONDS = 4 * 60 * 60;  // 4 hours — adjust per policy

export async function requireMfa(
  request: Request,
  env: Env
): Promise<Response | null> {
  const token = request.headers.get('Authorization')?.replace('Bearer ', '');
  if (!token) return new Response('Unauthorized', { status: 401 });

  let claims: MfaClaims;
  try {
    claims = await verifyJwt<MfaClaims>(token, env.JWT_PUBLIC_KEY);
  } catch {
    return new Response('Invalid token', { status: 401 });
  }

  if (!claims.mfa_verified) {
    return Response.json({
      error: 'MFA_REQUIRED',
      message: 'GLBA Safeguards Rule § 314.4(c)(2) requires MFA to access customer information.',
    }, { status: 403 });
  }

  const mfaAge = Math.floor(Date.now() / 1000) - claims.mfa_verified_at;
  if (mfaAge > MFA_MAX_AGE_SECONDS) {
    return Response.json({
      error: 'MFA_SESSION_EXPIRED',
      message: 'MFA session expired. Please re-authenticate.',
    }, { status: 403 });
  }

  return null;  // MFA satisfied — proceed
}
```

---

## Section 4 — Anomaly Detection and Event Monitoring (§ 314.4(h))

Log and alert on unusual NPI access patterns using Workers Analytics Engine and KV for rate-state.

```typescript
// src/glba/anomaly-monitor.ts
interface AccessPattern {
  count: number;
  distinctRecords: Set<string>;
  lastSeen: number;
}

export async function detectAnomaly(
  env: Env,
  accessorId: string,
  recordId: string
): Promise<boolean> {
  const windowKey = `glba:access:${accessorId}:${new Date().toISOString().slice(0, 13)}`;  // hourly bucket
  const raw = await env.GLBA_STATE.get(windowKey, { type: 'json' }) as AccessPattern | null;

  const pattern: AccessPattern = raw
    ? { ...raw, distinctRecords: new Set(raw.distinctRecords) }
    : { count: 0, distinctRecords: new Set(), lastSeen: 0 };

  pattern.count += 1;
  pattern.distinctRecords.add(recordId);
  pattern.lastSeen = Date.now();

  // Thresholds — tune per business context
  const RECORD_LIMIT = 200;   // distinct records per hour
  const COUNT_LIMIT  = 500;   // total accesses per hour

  const anomalous = pattern.count > COUNT_LIMIT || pattern.distinctRecords.size > RECORD_LIMIT;

  await env.GLBA_STATE.put(
    windowKey,
    JSON.stringify({ ...pattern, distinctRecords: [...pattern.distinctRecords] }),
    { expirationTtl: 7200 }
  );

  if (anomalous) {
    // Emit to Analytics Engine for SIEM ingestion
    env.ANALYTICS.writeDataPoint({
      blobs: [accessorId, 'GLBA_ANOMALY', recordId],
      doubles: [pattern.count, pattern.distinctRecords.size],
      indexes: [accessorId],
    });
    // Also send to alert queue
    await env.ALERT_QUEUE.send({
      type: 'GLBA_ANOMALY',
      accessorId,
      accessCount: pattern.count,
      distinctRecords: pattern.distinctRecords.size,
      windowHour: new Date().toISOString().slice(0, 13),
    });
  }

  return anomalous;
}
```

---

## Section 5 — Vendor / Service Provider Oversight (§ 314.4(f))

The Safeguards Rule requires written contracts with service providers that handle NPI, mandating that they implement appropriate safeguards.

```typescript
// src/glba/vendor-gate.ts
interface Vendor {
  id: string;
  name: string;
  contract_signed_at: string;
  contract_expires_at: string;
  safeguards_attestation_at: string;
  allowed_npi_categories: string;   // JSON array
}

export async function vendorSafeguardsCheck(
  env: Env,
  apiKey: string,
  npiCategory: string
): Promise<{ allowed: boolean; reason?: string }> {
  const keyHash = await sha256Hex(apiKey);

  const vendor = await env.DB.prepare(`
    SELECT v.* FROM vendors v
    JOIN vendor_api_keys k ON k.vendor_id = v.id
    WHERE k.key_hash = ? AND k.revoked_at IS NULL
  `).bind(keyHash).first<Vendor>();

  if (!vendor) return { allowed: false, reason: 'Unknown vendor' };

  if (new Date(vendor.contract_expires_at) < new Date()) {
    return { allowed: false, reason: `Vendor contract expired ${vendor.contract_expires_at}` };
  }

  const attestationAge = Date.now() - new Date(vendor.safeguards_attestation_at).getTime();
  const ONE_YEAR_MS = 365 * 24 * 60 * 60 * 1000;
  if (attestationAge > ONE_YEAR_MS) {
    return { allowed: false, reason: 'Annual safeguards attestation overdue' };
  }

  const allowed: string[] = JSON.parse(vendor.allowed_npi_categories);
  if (!allowed.includes(npiCategory)) {
    return { allowed: false, reason: `Vendor not authorised for NPI category '${npiCategory}'` };
  }

  return { allowed: true };
}

async function sha256Hex(input: string): Promise<string> {
  const digest = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(input));
  return Array.from(new Uint8Array(digest)).map(b => b.toString(16).padStart(2, '0')).join('');
}
```

---

## Section 6 — FTC Breach Notification Pipeline (30-Day Window)

Security events affecting ≥500 customers must be reported to the FTC within 30 days of discovery.

```typescript
// src/glba/breach-notification.ts
// Triggered by your incident response Worker when a qualifying event is confirmed

interface GlbaBreachEvent {
  discoveredAt: string;
  affectedCustomerCount: number;
  npiCategoriesInvolved: string[];
  description: string;
  containmentActions: string[];
}

export async function initiateBreachWorkflow(
  env: Env,
  event: GlbaBreachEvent
): Promise<void> {
  const deadlineDays = 30;
  const deadline = new Date(event.discoveredAt);
  deadline.setDate(deadline.getDate() + deadlineDays);

  // Persist breach record
  await env.DB.prepare(`
    INSERT INTO breach_incidents
      (id, discovered_at, affected_count, npi_categories, description, ftc_deadline, status)
    VALUES (?, ?, ?, ?, ?, ?, 'open')
  `).bind(
    crypto.randomUUID(),
    event.discoveredAt,
    event.affectedCustomerCount,
    JSON.stringify(event.npiCategoriesInvolved),
    event.description,
    deadline.toISOString()
  ).run();

  if (event.affectedCustomerCount >= 500) {
    // Escalate immediately — FTC notification within 30 days
    await env.ALERT_QUEUE.send({
      type: 'GLBA_BREACH_FTC_NOTIFICATION_REQUIRED',
      deadline: deadline.toISOString(),
      affectedCount: event.affectedCustomerCount,
      description: event.description,
    });
  }

  // Schedule reminder 7 days before deadline
  const reminderAt = new Date(deadline);
  reminderAt.setDate(reminderAt.getDate() - 7);
  await env.BREACH_REMINDER_QUEUE.send(
    { type: 'FTC_NOTIFICATION_REMINDER', deadlineIso: deadline.toISOString() },
    { delaySeconds: Math.max(0, Math.floor((reminderAt.getTime() - Date.now()) / 1000)) }
  );
}
```

---

## Anti-Patterns

- **Using `console.log()` with NPI fields** — Worker logs flow to Cloudflare's logging infrastructure and potentially to third-party drains. Log only opaque record IDs.
- **Storing NPI in KV without encryption** — KV is a good session store but unsuitable for raw NPI. Always encrypt before writing.
- **Relying on Cloudflare infrastructure encryption as your only safeguard** — Examiners want you to demonstrate control of encryption keys, not just rely on the cloud provider.
- **Skipping MFA for internal "service accounts"** — The Safeguards Rule does not carve out service accounts. Use mTLS or workload identity tokens with short TTLs.
- **Failing to document the annual information security report to board** — Evidence of the qualified individual's annual report is a direct audit artefact. Store it in R2 with a retention tag.

---

## Gotchas

- **"Financial institution" is broader than banks** — Mortgage servicers, auto dealers arranging financing, tax preparers, and payday lenders are all covered. Check FTC's NAICS-based guidance.
- **The 30-day FTC notification clock starts at discovery, not confirmation** — Internal investigation time is not excluded. Notify first, investigate in parallel.
- **Annual penetration test is a minimum** — State regulators (e.g. NY DFS for dual-regulated entities) may require shorter cycles.
- **Safeguards Rule does not override GLBA privacy rule** — Your annual privacy notice to customers (opt-out of sharing with affiliates) is a separate obligation not addressed by the Safeguards Rule.

---

## Verification Checklist

- [ ] All D1 tables storing NPI are in `data_inventory` with `encrypted = 1`.
- [ ] `GLBA_ENCRYPTION_KEY` and `GLBA_KEY_ID` are Wrangler secrets (not in `wrangler.toml`).
- [ ] Every NPI read path calls `requireMfa()` before decryption.
- [ ] `npi_access_log` is written on every access (including reads).
- [ ] Anomaly thresholds are tuned and anomaly events reach your SIEM.
- [ ] Vendor contracts and safeguards attestations are tracked in `vendors` table with expiry alerts.
- [ ] Breach workflow fires when `affectedCustomerCount >= 500`.
- [ ] Annual board security report is stored in R2 under a retention-tagged prefix.
- [ ] Penetration test results are stored and remediation tracked.

---

## Related Articles

- `ftc-safeguards-notification-event-clock.md`
- `data-minimization-workers-d1-pii-redaction.md`
- `audit-log-mandatory.md`
- `gdpr-breach-notification-72h.md`
- `nis2-incident-reporting-72-hour.md`

---

## Sources

- 16 CFR Part 314 (FTC Safeguards Rule, 2023 revision)
- FTC: "FTC Safeguards Rule: A Guide for Business" (2023)
- FTC Final Rule, 87 Fed. Reg. 70914 (Nov. 18, 2022)
- FTC Safeguards Rule Notification Requirement (effective May 2024)
- Cloudflare Workers Secrets: https://developers.cloudflare.com/workers/configuration/secrets/
- Cloudflare D1 documentation: https://developers.cloudflare.com/d1/
- Cloudflare Queues: https://developers.cloudflare.com/queues/
