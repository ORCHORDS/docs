# HIPAA Technical Safeguards for Web APIs

**Date:** 2026-08-17
**Author:** the platform team
**Status:** published

## Symptom

A new API endpoint will handle Protected Health Information
(PHI). The team is unsure which 45 CFR Part 164 controls apply
to web-layer code, how to satisfy them on Cloudflare Workers,
and what evidence auditors expect.

## Context

HIPAA's Security Rule (45 CFR §§ 164.302–164.318) requires
covered entities and business associates to implement technical
safeguards for any ePHI system. "Technical safeguard" means
the technology and the policies governing its use to protect
ePHI and control access to it. These obligations apply to
every tier: gateway, application, storage, and transport.

The four safeguard categories are:

| § Reference        | Category           | Implementation spec |
|--------------------|--------------------|---------------------|
| 164.312(a)(1)      | Access control     | Required + Addressable |
| 164.312(b)         | Audit controls     | Required |
| 164.312(c)(1)      | Integrity          | Addressable |
| 164.312(d)         | Person/entity auth | Addressable |
| 164.312(e)(1)      | Transmission sec.  | Addressable |

"Required" specs must be implemented. "Addressable" specs must
be implemented or documented as not reasonable and appropriate
(with an alternative).

## 1. Access Control (§ 164.312(a))

Unique user identification (§ 164.312(a)(2)(i)) requires that
every request to a PHI endpoint be attributable to a specific
user or service identity — shared credentials are prohibited.

Use Cloudflare Access (Zero Trust) as the gateway layer:

```toml
# wrangler.toml – protect a PHI route
[env.production]
routes = [{ pattern = "api.example.com/phi/*", zone_name = "example.com" }]
```

```yaml
# cloudflare-access-policy.yaml (declarative via Terraform)
resource "cloudflare_access_application" "phi_api" {
  zone_id          = var.zone_id
  name             = "PHI API"
  domain           = "api.example.com/phi"
  session_duration = "8h"
  allowed_idps     = [var.okta_idp_id]
  auto_redirect_to_identity = true
}

resource "cloudflare_access_policy" "phi_require_mfa" {
  application_id = cloudflare_access_application.phi_api.id
  precedence     = 1
  decision       = "allow"
  include {
    email_domain = ["example.com"]
    require      = [{ auth_method = "mfa" }]
  }
}
```

Automatic logoff (§ 164.312(a)(2)(iii)): set session
duration to ≤8 hours; service tokens must rotate every
90 days via CI pipeline.

Encryption and decryption (§ 164.312(a)(2)(iv)): D1 and R2
both encrypt data at rest with AES-256 managed by Cloudflare.
For field-level encryption of sensitive columns use the
Web Crypto API inside the Worker before inserting:

```js
// Encrypt a PHI field before D1 insert
async function encryptField(plaintext, keyMaterial) {
  const key = await crypto.subtle.importKey(
    "raw", keyMaterial, { name: "AES-GCM" }, false, ["encrypt"]
  );
  const iv = crypto.getRandomValues(new Uint8Array(12));
  const ciphertext = await crypto.subtle.encrypt(
    { name: "AES-GCM", iv }, key, new TextEncoder().encode(plaintext)
  );
  return { iv: btoa(String.fromCharCode(...iv)),
           data: btoa(String.fromCharCode(...new Uint8Array(ciphertext))) };
}
```

## 2. Audit Controls (§ 164.312(b))

This is a **Required** spec with no alternative. Every system
that touches ePHI must record activity sufficient to detect
and reconstruct security incidents.

Cloudflare Logpush ships Worker logs to a SIEM within
seconds. Configure it so that PHI itself never appears in
log fields — log IDs and access events only.

```bash
# Create a Logpush job for Workers to S3-compatible storage
curl -X POST "https://api.cloudflare.com/client/v4/zones/${ZONE_ID}/logpush/jobs" \
  -H "Authorization: Bearer ${CF_API_TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "phi-audit-trail",
    "destination_conf": "s3://${AUDIT_BUCKET}/phi-logs?region=us-east-1",
    "dataset": "workers_trace_events",
    "logpull_options": "fields=EventTimestampMs,Outcome,ScriptName,WorkerSubrequestCount",
    "enabled": true
  }'
```

PHI minimization rule: strip any field that could contain
a name, DOB, SSN, or diagnosis before the log pipeline.
Implement a `sanitizeLogs` middleware as the first step in
every PHI route handler.

Audit log retention: maintain logs for **6 years** (the
longer of HIPAA's 6-year record retention and your own
policy). Use S3 Object Lock (WORM) or R2 equivalent.

## 3. Integrity Controls (§ 164.312(c))

Verify that ePHI has not been improperly altered or
destroyed in transit or at rest.

At-rest integrity: D1 uses SQLite's page checksum. For
critical records add an HMAC column:

```sql
-- schema: phi_records
CREATE TABLE phi_records (
  id          TEXT PRIMARY KEY,
  payload     TEXT NOT NULL,          -- encrypted ciphertext
  hmac_sha256 TEXT NOT NULL,          -- hex-encoded HMAC
  created_at  DATETIME DEFAULT CURRENT_TIMESTAMP
);
```

In-transit integrity: TLS 1.2+ provides record-layer MAC.
Enforce minimum TLS version in the Cloudflare dashboard
(SSL/TLS → Edge Certificates → Minimum TLS Version = TLS 1.2).

## 4. Transmission Security (§ 164.312(e))

Disable plain-HTTP access at the zone level:

```bash
# Always Use HTTPS (Cloudflare API)
curl -X PATCH "https://api.cloudflare.com/client/v4/zones/${ZONE_ID}/settings/always_use_https" \
  -H "Authorization: Bearer ${CF_API_TOKEN}" \
  -d '{"value":"on"}'

# Minimum TLS 1.2
curl -X PATCH "https://api.cloudflare.com/client/v4/zones/${ZONE_ID}/settings/min_tls_version" \
  -H "Authorization: Bearer ${CF_API_TOKEN}" \
  -d '{"value":"1.2"}'
```

Never pass PHI in URL query strings — HTTP access logs
record full URLs. Use POST bodies over HTTPS.

## 5. Business Associate Agreements

Any cloud provider that stores or processes ePHI on your
behalf is a Business Associate and must sign a BAA before
you route PHI through their infrastructure. Cloudflare
offers a BAA for customers on Business and Enterprise plans.
D1, R2, Workers, and Zero Trust are all covered under the
Cloudflare BAA as of 2025.

Checklist:
- [ ] Signed Cloudflare BAA on file
- [ ] BAA with any downstream analytics or logging vendor
- [ ] BAA reviewed annually or on material scope change
- [ ] BAA register maintained in your vendor risk register

## Anti-patterns

- Logging PHI fields (even "just for debugging") — a log
  containing a patient name is itself ePHI and subject to
  all security-rule controls.
- Using a shared API key across services — violates unique
  user identification.
- Storing ePHI in KV without field-level encryption — KV
  is encrypted at rest by Cloudflare but you must still
  implement application-layer encryption for high-risk data.
- Sending PHI over WebSocket without confirming TLS is
  enforced end-to-end.
- Caching ePHI responses at the Cloudflare edge — mark
  PHI endpoints with `Cache-Control: no-store`.

## Gotchas

- Cloudflare's BAA does **not** cover free-plan accounts.
  Upgrade before routing any ePHI.
- `wrangler tail` in production streams logs to your
  terminal — ensure PHI sanitization is in place before
  enabling tail on a PHI Worker.
- D1 backups are automatic and encrypted but are stored in
  Cloudflare's infrastructure; confirm they are covered
  under the same BAA scope.
- Addressable specs still require a documented risk
  analysis if you choose not to implement them — "we
  couldn't get to it" is not a valid justification.

## Verification

1. Run `curl -I https://api.example.com/phi/test` — confirm
   `Strict-Transport-Security` header present with `max-age`
   ≥ 31536000.
2. Attempt HTTP access — must redirect to HTTPS (301/308).
3. Query Logpush destination bucket — confirm events appear
   within 60 seconds of a Worker invocation.
4. Grep audit logs for any PHI field names
   (`name`, `dob`, `ssn`, `diagnosis`) — must return zero
   results.
5. Verify Cloudflare Access session cookie expires after
   the configured session duration.

## Related

- `/compliance/hipaa-administrative-safeguards.md`
- `/compliance/hipaa-audit-controls.md`
- `/compliance/hipaa-physical-safeguards.md`
- `/compliance/gdpr-data-breach-notification.md`
- `/compliance/iso-27001-annex-a-controls.md`

## Source URLs (verified 2026-08-17)

- https://www.ecfr.gov/current/title-45/subtitle-A/subchapter-C/part-164/subpart-C
- https://www.hhs.gov/hipaa/for-professionals/security/guidance/technical-safeguards/index.html
- https://developers.cloudflare.com/logpush/
- https://developers.cloudflare.com/cloudflare-one/applications/configure-apps/
- https://www.cloudflare.com/cloudflare-customer-dpa/
