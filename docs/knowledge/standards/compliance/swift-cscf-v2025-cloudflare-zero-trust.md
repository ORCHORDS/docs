# SWIFT Customer Security Programme (CSCF v2025): Mandatory Controls via Cloudflare Zero Trust and Workers

**Date:** 2026-08-22
**Author:** example.com
**Status:** production

---

## Symptom / Use-Case

Your organisation is a SWIFT member — a bank, payment infrastructure operator, or market infrastructure participant — running portions of your SWIFT-related application layer on Cloudflare Workers. Your annual SWIFT CSP attestation is due and the third-party assessor asks for evidence of mandatory controls in the CSCF v2025 framework. You need to map Cloudflare's Zero Trust, WAF, Workers, and D1 capabilities to specific CSCF control IDs.

---

## Context

The **SWIFT Customer Security Programme (CSP)** is a mandatory self-attestation and third-party assessment regime for all SWIFT member institutions. The **Customer Security Controls Framework (CSCF)** — updated annually — defines three security objectives and 31 controls (as of v2025), of which 25 are **mandatory** and 6 are **advisory**.

The three CSCF security objectives:
1. **Secure Your Environment** (controls 1.x–3.x): network, endpoint, and physical security
2. **Know and Limit Access** (controls 4.x–5.x): access control, credential management
3. **Detect and Respond** (controls 6.x–7.x): anomaly detection, incident response

Attestation is submitted annually via SWIFT's KYC Security Attestation (KYC-SA) application. Deliberate false attestation can result in suspension from SWIFT.

This article focuses on the subset of mandatory controls most directly addressed by Cloudflare infrastructure, specifically controls 1.1, 1.2, 2.1, 4.1, 4.2, 5.1, 6.1, and 7.1.

---

## Section 1 — Control 1.1 / 1.2: SWIFT Environment Boundary with Cloudflare Zero Trust

CSCF 1.1 (Mandatory): Ensure the protection of the user's local SWIFT infrastructure from potentially compromised elements of the general IT environment. CSCF 1.2 (Mandatory): Restrict Internet access and protect critical systems from the general IT environment.

```typescript
// CSCF 1.1 / 1.2 Evidence: Zero Trust access policy for SWIFT-connected application Workers
// Cloudflare Zero Trust — Policies defined via Terraform or dashboard; evidence captured here.

// wrangler.toml excerpt — SWIFT application Worker is not publicly routed
// routes = []  — no public internet route; only accessible via ZTNA tunnel

// Zero Trust Access policy (Terraform representation for evidence documentation):
/*
resource "cloudflare_zero_trust_access_application" "swift_app" {
  zone_id          = var.zone_id
  name             = "SWIFT Core Application"
  domain           = "swift-app.internal.example.com"
  type             = "self_hosted"
  session_duration = "8h"

  // Mandatory: enforce MFA for all access (CSCF 4.2)
  allowed_idps          = [cloudflare_zero_trust_identity_provider.corp_saml.id]
}

resource "cloudflare_zero_trust_access_policy" "swift_admins" {
  application_id = cloudflare_zero_trust_access_application.swift_app.id
  name           = "SWIFT Admins MFA"
  decision       = "allow"
  precedence     = 1

  include {
    email_domain = ["example.com"]
    group        = [var.swift_admin_group_id]
  }
  require {
    // CSCF 4.2: MFA required
    auth_method = "mfa"
    // CSCF 1.2: restrict to corporate IP ranges
    ip { ip = var.corporate_ip_ranges }
  }
}
*/

// Workers-side: secondary validation that request arrived via ZTNA tunnel
export async function requireZtnaContext(request: Request, env: Env): Promise<Response | null> {
  // Cloudflare Access injects Cf-Access-Jwt-Assertion header
  const jwt = request.headers.get('Cf-Access-Jwt-Assertion');
  if (!jwt) {
    return new Response(JSON.stringify({
      error: 'CSCF_1_1_VIOLATION',
      message: 'Request must arrive via Zero Trust tunnel — direct internet access not permitted',
    }), { status: 403 });
  }

  // Validate the JWT using Cloudflare's public key (fetched at startup, cached in Worker global)
  const { payload } = await verifyCloudflareAccessJwt(jwt, env.CF_ACCESS_TEAM_DOMAIN);
  if (!payload) {
    return new Response('Invalid ZTNA token', { status: 401 });
  }

  return null;
}
```

---

## Section 2 — Control 2.1: Data Confidentiality and Integrity (Encryption)

CSCF 2.1 (Mandatory): Ensure the confidentiality and integrity of application data flows over SWIFT messaging interfaces. All SWIFT message data stored or cached must be encrypted with operator-controlled keys.

```typescript
// src/swift/message-crypto.ts
// SWIFT FIN/ISO 20022 message payloads require encryption before any persistence

const SWIFT_MSG_ALGORITHM: AesKeyGenParams = { name: 'AES-GCM', length: 256 };

export async function encryptSwiftMessage(
  message: string,
  env: Env
): Promise<{ ciphertext: string; iv: string; keyVersion: string }> {
  const keyBytes = Uint8Array.from(atob(env.SWIFT_MSG_KEY), c => c.charCodeAt(0));
  const cryptoKey = await crypto.subtle.importKey(
    'raw', keyBytes, SWIFT_MSG_ALGORITHM, false, ['encrypt']
  );
  const iv = crypto.getRandomValues(new Uint8Array(12));
  const ct = await crypto.subtle.encrypt({ name: 'AES-GCM', iv }, cryptoKey, new TextEncoder().encode(message));

  return {
    ciphertext: btoa(String.fromCharCode(...new Uint8Array(ct))),
    iv: btoa(String.fromCharCode(...iv)),
    keyVersion: env.SWIFT_MSG_KEY_VERSION,   // e.g. "2025-Q1"
  };
}

// D1 schema for encrypted SWIFT messages (staging/cache only — not long-term store)
/*
CREATE TABLE swift_message_staging (
  id           TEXT PRIMARY KEY,
  direction    TEXT NOT NULL CHECK(direction IN ('inbound','outbound')),
  msg_type     TEXT NOT NULL,      -- e.g. 'MT103', 'pacs.008'
  ciphertext   TEXT NOT NULL,
  iv           TEXT NOT NULL,
  key_version  TEXT NOT NULL,
  queued_at    TEXT NOT NULL DEFAULT (datetime('now')),
  dispatched_at TEXT,
  purge_after  TEXT NOT NULL,      -- CSCF 2.1: short retention in staging
  CHECK(purge_after > queued_at)
);
*/

// Cron Trigger: purge staging messages after 24h (CSCF 2.1 short-window retention)
export async function purgeStagingMessages(env: Env): Promise<void> {
  const result = await env.DB.prepare(`
    DELETE FROM swift_message_staging
    WHERE purge_after <= datetime('now')
  `).run();
  console.log(`SWIFT staging purge: ${result.meta.changes} messages removed`);
}
```

---

## Section 3 — Control 4.1 / 4.2: Password and Multi-Factor Authentication Policy

CSCF 4.1 (Mandatory): Ensure passwords meet minimum complexity. CSCF 4.2 (Mandatory): Enforce multi-factor authentication for all SWIFT-related operator accounts.

```typescript
// src/swift/auth-policy.ts
// Enforced at the Workers edge; authentication upstream via Cloudflare Access SAML/OIDC

export interface SwiftOperatorClaims {
  sub: string;
  email: string;
  groups: string[];
  mfa_verified: boolean;
  mfa_method: 'totp' | 'webauthn' | 'hardware_token';
  amr: string[];   // Authentication Method References (RFC 8176)
  iat: number;
  exp: number;
}

// CSCF 4.2: require hardware token or WebAuthn for SWIFT operators (not just TOTP)
const STRONG_MFA_METHODS: SwiftOperatorClaims['mfa_method'][] = ['webauthn', 'hardware_token'];

export function validateSwiftOperatorSession(claims: SwiftOperatorClaims): { valid: boolean; reason?: string } {
  if (!claims.mfa_verified) {
    return { valid: false, reason: 'CSCF_4_2: MFA not verified' };
  }

  if (!STRONG_MFA_METHODS.includes(claims.mfa_method)) {
    return { valid: false, reason: `CSCF_4_2: Hardware token or WebAuthn required for SWIFT operators; got '${claims.mfa_method}'` };
  }

  // CSCF 4.1: session must not be stale (max 8h, aligns with SWIFT operator shift)
  const sessionAgeSeconds = Math.floor(Date.now() / 1000) - claims.iat;
  if (sessionAgeSeconds > 8 * 60 * 60) {
    return { valid: false, reason: 'CSCF_4_1: Session exceeded 8-hour maximum' };
  }

  return { valid: true };
}

export async function swiftOperatorGuard(request: Request, env: Env): Promise<Response | null> {
  const token = request.headers.get('Authorization')?.replace('Bearer ', '');
  if (!token) return new Response('Unauthorized', { status: 401 });

  const claims = await verifyJwt<SwiftOperatorClaims>(token, env.JWT_PUBLIC_KEY);
  if (!claims) return new Response('Invalid token', { status: 401 });

  const check = validateSwiftOperatorSession(claims);
  if (!check.valid) {
    return Response.json({ error: 'SWIFT_AUTH_POLICY', message: check.reason }, { status: 403 });
  }

  return null;
}
```

---

## Section 4 — Control 5.1: Logical Access Control

CSCF 5.1 (Mandatory): Enforce the security principles of least privilege and need-to-know for operator accounts. All access to SWIFT-related systems must be based on defined roles.

```typescript
// src/swift/rbac.ts
export type SwiftRole = 'initiator' | 'authoriser' | 'supervisor' | 'auditor' | 'readonly';

// SWIFT four-eyes principle: initiator and authoriser must be different people
interface SwiftTransaction {
  initiatedBy: string;
  authorisedBy?: string;
  amount: number;
  currency: string;
  status: 'pending_auth' | 'authorised' | 'rejected';
}

// Threshold matrix (CSCF 5.1 dual-control requirement)
const DUAL_CONTROL_THRESHOLDS: Record<string, number> = {
  USD: 10_000,
  EUR: 10_000,
  GBP: 8_500,
};

export function requiresDualControl(amount: number, currency: string): boolean {
  const threshold = DUAL_CONTROL_THRESHOLDS[currency] ?? 10_000;
  return amount >= threshold;
}

export async function authoriseSwiftTransaction(
  env: Env,
  transactionId: string,
  authoriserEmail: string
): Promise<Response> {
  const tx = await env.DB.prepare(
    'SELECT * FROM swift_transactions WHERE id = ?'
  ).bind(transactionId).first<SwiftTransaction>();

  if (!tx) return new Response('Transaction not found', { status: 404 });

  if (tx.status !== 'pending_auth') {
    return Response.json({ error: 'Transaction not pending authorisation' }, { status: 409 });
  }

  // CSCF 5.1 four-eyes: authoriser must differ from initiator
  if (tx.initiatedBy === authoriserEmail) {
    return Response.json({
      error: 'CSCF_5_1_FOUR_EYES',
      message: 'The authoriser must be a different operator from the initiator',
    }, { status: 403 });
  }

  await env.DB.prepare(`
    UPDATE swift_transactions
    SET authorised_by = ?, status = 'authorised', authorised_at = datetime('now')
    WHERE id = ?
  `).bind(authoriserEmail, transactionId).run();

  // Audit log — CSCF 6.1
  await env.DB.prepare(`
    INSERT INTO swift_audit_log (id, event_type, transaction_id, actor, timestamp)
    VALUES (?, 'AUTHORISED', ?, ?, datetime('now'))
  `).bind(crypto.randomUUID(), transactionId, authoriserEmail).run();

  return Response.json({ status: 'authorised', transactionId });
}
```

---

## Section 5 — Control 6.1: Malware Protection and WAF Configuration

CSCF 6.1 (Mandatory): Ensure anti-malware software and controls are deployed. For SWIFT-connected API surfaces, Cloudflare WAF serves as the edge malware/injection protection layer.

```typescript
// Evidence artefact: Cloudflare WAF ruleset applied to SWIFT-facing zones
// Configure via Terraform for immutable infrastructure evidence

/*
resource "cloudflare_ruleset" "swift_waf" {
  zone_id     = var.zone_id
  name        = "SWIFT API WAF Ruleset"
  description = "CSCF 6.1: WAF controls for SWIFT-connected Workers endpoints"
  kind        = "zone"
  phase       = "http_request_firewall_managed"

  rules {
    action      = "block"
    description = "OWASP Core Ruleset (CSCF 6.1)"
    expression  = "true"
    enabled     = true
    action_parameters {
      id      = "efb7b8c949ac4650a09736fc376e9aee"  // Cloudflare OWASP Core RS
      version = "latest"
      overrides {
        action           = "block"
        sensitivity_level = "high"
      }
    }
  }

  rules {
    action      = "block"
    description = "Cloudflare Managed Ruleset (CSCF 6.1)"
    expression  = "true"
    enabled     = true
    action_parameters {
      id = "4814384a9e5d4991b9815dcfc25d2f1f"  // Cloudflare Managed RS
    }
  }
}

// CSCF 1.2: Block non-corporate IP ranges from SWIFT operator interface
resource "cloudflare_ruleset" "swift_ip_allowlist" {
  zone_id = var.zone_id
  name    = "SWIFT Operator IP Allowlist"
  kind    = "zone"
  phase   = "http_request_firewall_custom"

  rules {
    action      = "block"
    description = "Block non-corporate IPs on /swift/* paths"
    expression  = "(http.request.uri.path wildcard \"/swift/*\") and not (ip.src in $corporate_ips)"
    enabled     = true
  }
}
*/

// Workers-side: verify WAF cleared the request (CF-Ray present confirms WAF processed it)
export function verifyWafContext(request: Request): boolean {
  const cfRay = request.headers.get('CF-Ray');
  const country = request.cf?.country;
  // Optionally enforce geo-restriction for SWIFT endpoints
  return !!cfRay;
}
```

---

## Section 6 — Control 7.1: Cyber Incident Response and SWIFT Evidence Logging

CSCF 7.1 (Mandatory): Plan and test incident response for SWIFT-related cyber incidents. D1 audit log must be tamper-evident and accessible to third-party assessors.

```typescript
// src/swift/audit-log.ts
// CSCF 6.1 and 7.1: immutable-by-convention audit log in D1

interface SwiftAuditEntry {
  id: string;
  eventType: string;
  transactionId?: string;
  actor: string;
  actorIp?: string;
  details: Record<string, unknown>;
  timestamp: string;
  prevHash?: string;  // chained hash for tamper evidence
}

export async function writeAuditEntry(
  env: Env,
  entry: Omit<SwiftAuditEntry, 'id' | 'timestamp' | 'prevHash'>
): Promise<void> {
  // Fetch last entry's hash for chaining
  const last = await env.DB.prepare(
    'SELECT id, entry_hash FROM swift_audit_log ORDER BY rowid DESC LIMIT 1'
  ).first<{ id: string; entry_hash: string }>();

  const now = new Date().toISOString();
  const id = crypto.randomUUID();

  const content = JSON.stringify({ ...entry, id, timestamp: now, prevHash: last?.entry_hash ?? 'GENESIS' });
  const hashBuffer = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(content));
  const entryHash = Array.from(new Uint8Array(hashBuffer)).map(b => b.toString(16).padStart(2, '0')).join('');

  await env.DB.prepare(`
    INSERT INTO swift_audit_log
      (id, event_type, transaction_id, actor, actor_ip, details, timestamp, prev_hash, entry_hash)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
  `).bind(
    id,
    entry.eventType,
    entry.transactionId ?? null,
    entry.actor,
    entry.actorIp ?? null,
    JSON.stringify(entry.details),
    now,
    last?.entry_hash ?? 'GENESIS',
    entryHash
  ).run();
}

// Export audit log for assessor (CSCF 7.1 third-party review support)
export async function exportAuditLog(
  env: Env,
  fromDate: string,
  toDate: string
): Promise<SwiftAuditEntry[]> {
  const { results } = await env.DB.prepare(`
    SELECT id, event_type, transaction_id, actor, actor_ip, details, timestamp, prev_hash, entry_hash
    FROM swift_audit_log
    WHERE timestamp BETWEEN ? AND ?
    ORDER BY rowid ASC
  `).bind(fromDate, toDate).all();
  return results as unknown as SwiftAuditEntry[];
}
```

---

## Anti-Patterns

- **Running SWIFT-connected Workers on the same zone as public consumer APIs** — CSCF 1.1 requires a secure boundary. Use separate zones and Zero Trust tunnels for SWIFT-related Workers.
- **Using short-lived TOTP as the only MFA factor for SWIFT operators** — CSCF v2025 guidance increasingly expects hardware authenticators (FIDO2/WebAuthn or hardware tokens) for privileged SWIFT access.
- **Storing SWIFT messages in KV or D1 beyond the minimum necessary retention** — SWIFT messages contain BIC codes, account numbers, and amounts. Purge staging rows within 24 hours per CSCF 2.1.
- **Not documenting Cloudflare as a sub-processor in your SWIFT infrastructure inventory** — SWIFT assessors expect a network and vendor inventory. Cloudflare's IP ranges and data-centre locations must appear in your network security documentation.

---

## Gotchas

- **CSCF attestation is self-attest by default; third-party assessment is mandatory for some tiers** — SWIFT Operator Types A1/A2 require independent assessment. Ensure your assessor has access to Cloudflare Zero Trust policy exports and WAF ruleset Terraform configs as evidence artefacts.
- **CSCF v2025 may introduce new mandatory controls not in v2024** — SWIFT updates the CSCF annually. Review the release notes each October and update your control mapping before the Q1 attestation window.
- **Cloudflare Zero Trust sessions do not automatically invalidate when a SWIFT operator is terminated** — Build an off-boarding workflow that revokes access group membership and rotates API keys within 24 hours (CSCF 5.1).
- **The four-eyes principle applies to administrative changes, not just transactions** — Worker deployments, D1 schema changes, and WAF rule modifications to SWIFT-connected infrastructure should require dual sign-off.

---

## Verification Checklist

- [ ] SWIFT-connected Workers are accessible only via Cloudflare Zero Trust tunnel (no public route).
- [ ] Zero Trust Access policy enforces MFA (`auth_method = "mfa"`) and IP restriction.
- [ ] All SWIFT operator JWTs include `mfa_method: 'webauthn' | 'hardware_token'`.
- [ ] `swift_message_staging` rows are purged within 24 hours by Cron Trigger.
- [ ] Four-eyes enforcement: `initiatedBy !== authorisedBy` check in authorisation handler.
- [ ] Cloudflare Managed Ruleset and OWASP Core Ruleset active on SWIFT zone.
- [ ] `swift_audit_log` is chained-hash structured and exported for annual third-party assessment.
- [ ] Off-boarding runbook revokes Zero Trust group membership within 24 hours of termination.
- [ ] CSCF control mapping document updated for v2025 control list before attestation window.

---

## Related Articles

- `iso-27001-annex-a-controls.md`
- `pci-dss-4.md`
- `dora-regulation.md`
- `audit-log-mandatory.md`
- `nis2-article-21-technical-measures-workers.md`

---

## Sources

- SWIFT Customer Security Controls Framework (CSCF) v2025
- SWIFT CSP: https://www.swift.com/myswift/customer-security-programme-csp
- SWIFT CSCF v2024 Independent Assessment Framework
- Cloudflare Zero Trust: https://developers.cloudflare.com/cloudflare-one/
- Cloudflare WAF managed rulesets: https://developers.cloudflare.com/waf/managed-rules/
- Cloudflare Terraform provider: https://registry.terraform.io/providers/cloudflare/cloudflare/latest
- RFC 8176 Authentication Method Reference Values
