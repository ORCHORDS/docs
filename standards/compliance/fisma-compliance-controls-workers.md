# FISMA Compliance Controls on Cloudflare Workers

- **Date:** 2026-08-23
- **Author:** example.com
- **Status:** production

## Symptom / Use-case

Your SaaS product is used by US federal agencies or their contractors. You must implement Federal Information Security Modernization Act (FISMA) controls — continuous monitoring, access control, audit logging, and incident response — within a Cloudflare Workers architecture.

## Context

FISMA (44 U.S.C. § 3551 et seq., as amended by the 2014 FISMA Reform Act) requires federal agencies and their information system providers to implement the NIST Risk Management Framework (RMF) and select controls from NIST SP 800-53 Rev 5. The impact level (Low / Moderate / High) drives the control baseline. Workers deployments supporting federal use cases must maintain continuous monitoring artefacts (POA&M, SSP, ConMon reports) and implement at minimum the Moderate baseline controls for cloud-based systems.

---

## 1. Access Control (AC Family) — Role Enforcement Middleware

FISMA AC-3 requires enforcing approved authorisations. Use Workers to validate JWT claims against a role matrix before proxying to origin.

```typescript
// src/fisma-ac-middleware.ts
interface Claims { sub: string; roles: string[]; agency: string }

const ROLE_MATRIX: Record<string, string[]> = {
  '/api/pii':       ['analyst', 'admin'],
  '/api/admin':     ['admin'],
  '/api/reports':   ['analyst', 'viewer', 'admin'],
};

export async function enforceAccessControl(
  request: Request,
  claims: Claims
): Promise<Response | null> {
  const path = new URL(request.url).pathname;
  const allowed = Object.entries(ROLE_MATRIX).find(([prefix]) =>
    path.startsWith(prefix)
  );
  if (!allowed) return null; // unprotected path, pass through
  const [, roles] = allowed;
  const hasRole = claims.roles.some(r => roles.includes(r));
  if (!hasRole) {
    return new Response(JSON.stringify({ error: 'AC-3 violation: insufficient role' }), {
      status: 403,
      headers: { 'Content-Type': 'application/json' }
    });
  }
  return null;
}
```

---

## 2. Audit & Accountability (AU Family) — Immutable Audit Log to R2

FISMA AU-2 and AU-9 require audit records to be protected from modification. Write logs to an R2 object with a content-addressed key.

```typescript
// src/fisma-audit-log.ts
import { createHash } from 'node:crypto'; // available in Workers via compatibility_date >= 2023-03-01

interface AuditEvent {
  eventType: string;
  userId: string;
  resource: string;
  outcome: 'success' | 'failure';
  timestamp: string;
  ipAddress: string;
  agencyId: string;
}

export async function writeAuditEvent(
  bucket: R2Bucket,
  event: AuditEvent
): Promise<string> {
  const body = JSON.stringify(event);
  // Content-addressed key prevents silent overwrite (AU-9)
  const hash = createHash('sha256').update(body).digest('hex');
  const key = `audit/${event.agencyId}/${event.timestamp.slice(0, 10)}/${hash}.json`;
  await bucket.put(key, body, {
    httpMetadata: { contentType: 'application/json' },
    customMetadata: { fismaControl: 'AU-2,AU-9', immutable: 'true' }
  });
  return key;
}
```

---

## 3. Identification & Authentication (IA Family) — PIV/CAC Header Validation

Federal systems must support PIV/CAC cards (IA-2(1)). When the agency's reverse proxy injects a certificate header, Workers validate it.

```typescript
// src/piv-validation.ts
export function validatePivHeader(request: Request): { valid: boolean; dn: string | null } {
  // Agency proxy injects X-Client-Cert-DN after mTLS termination
  const dn = request.headers.get('X-Client-Cert-DN');
  if (!dn) return { valid: false, dn: null };
  // PIV DNs contain OU=DoD or OU=<Agency Abbreviation>
  const pivPattern = /OU=(DoD|GSA|DHS|DOJ|Treasury)/i;
  return { valid: pivPattern.test(dn), dn };
}

export function requirePiv(request: Request): Response | null {
  const { valid } = validatePivHeader(request);
  if (!valid) {
    return new Response('IA-2: PIV/CAC authentication required', { status: 401,
      headers: { 'WWW-Authenticate': 'Certificate realm="FederalPKI"' }
    });
  }
  return null;
}
```

---

## 4. Continuous Monitoring (CA-7) — Health Check & ConMon Evidence Export

FISMA CA-7 mandates continuous monitoring of security controls. Export a structured status snapshot to KV for ISSO review.

```typescript
// src/conmon-snapshot.ts
interface ConMonRecord {
  snapshotAt: string;
  controlsChecked: string[];
  openFindings: number;
  systemStatus: 'operational' | 'degraded' | 'outage';
}

export async function publishConMonSnapshot(
  kv: KVNamespace,
  findings: number,
  status: ConMonRecord['systemStatus']
): Promise<void> {
  const record: ConMonRecord = {
    snapshotAt: new Date().toISOString(),
    controlsChecked: ['AC-3', 'AU-2', 'AU-9', 'IA-2', 'SC-8', 'SI-3'],
    openFindings: findings,
    systemStatus: status,
  };
  // TTL 90 days — FISMA requires ConMon records retained ≥ 3 years; archive to R2 separately
  await kv.put('conmon:latest', JSON.stringify(record), { expirationTtl: 90 * 86400 });
  await kv.put(`conmon:${record.snapshotAt}`, JSON.stringify(record), {
    expirationTtl: 90 * 86400,
    metadata: { reportType: 'FISMA-ConMon' }
  });
}
```

---

## 5. System & Communications Protection (SC-8) — TLS Enforcement

FISMA SC-8 requires transmission confidentiality. Workers should reject non-TLS connections and enforce HSTS.

```typescript
// src/tls-enforcement.ts
export function enforceTls(request: Request): Response | null {
  // Cloudflare always terminates TLS; check the forwarded protocol
  const proto = request.headers.get('X-Forwarded-Proto') ?? 'https';
  if (proto !== 'https') {
    const url = new URL(request.url);
    url.protocol = 'https:';
    return Response.redirect(url.toString(), 301);
  }
  return null;
}

export function addHstsHeader(response: Response): Response {
  const headers = new Headers(response.headers);
  // FISMA moderate baseline: min 1 year, includeSubDomains
  headers.set('Strict-Transport-Security', 'max-age=31536000; includeSubDomains; preload');
  return new Response(response.body, { status: response.status, headers });
}
```

---

## Anti-patterns

- **Storing audit logs in D1 without WAL + replication** — D1 is mutable; pair with R2 for immutable archival (AU-9).
- **Using symmetric JWT secrets for IA** — FISMA IA-7 requires NIST-approved cryptographic mechanisms; use RS256 or ES256.
- **Skipping POA&M linkage** — every finding must be tracked in the Plan of Action & Milestones; log a `findingId` field in audit events.
- **Hardcoding agency lists** — maintain the role matrix in KV or D1 to allow updates without redeployment.

---

## Gotchas

- FISMA impact level drives the required control baseline; confirm the system's FIPS 199 categorisation before mapping controls.
- Cloudflare Workers do not run inside a FedRAMP-authorised boundary by default; check whether your Cloudflare account is on the GovCloud or FedRAMP Moderate offering.
- `node:crypto` in Workers requires `compatibility_flags = ["nodejs_compat"]` in `wrangler.toml`.
- FISMA does not prescribe specific technologies; the obligation is to *select and implement* controls from the 800-53 baseline — documentation is evidence.

---

## Verification

```bash
# Confirm TLS enforcement
curl -I http://example.gov/ | grep -i location

# Check HSTS header
curl -I https://example.gov/ | grep Strict-Transport

# Inspect ConMon snapshot in KV
wrangler kv key get --binding KV_NAMESPACE conmon:latest

# List R2 audit objects for a date
wrangler r2 object list AUDIT_BUCKET --prefix "audit/GSA/$(date +%Y-%m-%d)/"
```

---

## Related

- `fedramp-compliance.md`
- `fedramp-authorization-basics.md`
- `nist-800-53-control-families.md`
- `nist-csf-2-mapping.md`
- `soc2-cc6-logical-access-controls.md`

---

## Sources

- FISMA 2014 — 44 U.S.C. §§ 3551–3558 — https://www.congress.gov/113/plaws/publ283/PLAW-113publ283.pdf
- NIST SP 800-53 Rev 5 — https://doi.org/10.6028/NIST.SP.800-53r5
- NIST SP 800-37 Rev 2 (RMF) — https://doi.org/10.6028/NIST.SP.800-37r2
- Cloudflare Workers R2 — https://developers.cloudflare.com/r2/
- Cloudflare Workers KV — https://developers.cloudflare.com/kv/
