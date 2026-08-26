# feature-jit-licensing

**Issue:** Software licensing + entitlement — local, server, hybrid
**Date:** 2026-08-09
**Status:** documented

## Symptom
You build a feature that requires a license. The user
clicks "Activate." You send a request to your server. The
server returns a license key. The user enters the key. The
feature works. The user is offline. The feature stops
working. The user is frustrated.

## Root cause
**License management is hard.** Online-only, offline-only,
and hybrid all have tradeoffs.

**Source:** Various licensing guides.

## The 3 licensing models

### Online-only
- **What:** The app checks the server on every use
- **Pros:** Easy to revoke; full control
- **Cons:** No offline; latency; server dependency

### Offline-only
- **What:** The license is stored locally; checked locally
- **Pros:** Works offline; no server dependency
- **Cons:** Hard to revoke; easy to pirate

### Hybrid (online + offline)
- **What:** Online for activation; offline for use
- **Pros:** Works offline; revocable on next online check
- **Cons:** Complex; needs a heartbeat

## The "online-only" pattern

```ts
async function checkLicense(licenseKey: string, env: Env): Promise<{ valid: boolean; features: string[] }> {
  const response = await fetch(`https://license.example.com/check/${licenseKey}`);
  if (!response.ok) return { valid: false, features: [] };
  return response.json();
}

// Usage
if (!await checkLicense(licenseKey, env)) {
  return new Response('License invalid', { status: 403 });
}
```

The server is the source of truth. The check is per-request.

## The "offline license" pattern

```ts
// License file (signed)
{
  "key": "ABC-123-XYZ",
  "features": ["pro", "export"],
  "expiresAt": "2027-01-01",
  "signature": "base64-encoded-rsa-signature"
}

// Verification
import { verify } from 'crypto';

function verifyLicense(license: License): boolean {
  const data = JSON.stringify({ key: license.key, features: license.features, expiresAt: license.expiresAt });
  return verify('RSA-SHA256', data, publicKey, Buffer.from(license.signature, 'base64'));
}
```

The license is signed; the signature is verified locally.

## The "license server" pattern

For server-side license checks:
```sql
CREATE TABLE licenses (
  id TEXT PRIMARY KEY,
  user_id TEXT NOT NULL,
  key TEXT UNIQUE NOT NULL,
  plan TEXT NOT NULL,
  features TEXT,  -- JSON
  expires_at TEXT,
  revoked_at TEXT,
  created_at TEXT DEFAULT CURRENT_TIMESTAMP
);
```

```ts
async function activateLicense(key: string, userId: string, env: Env): Promise<License> {
  const license = await env.DB!.prepare(
    `SELECT * FROM licenses WHERE key = ? AND revoked_at IS NULL`
  ).bind(key).first<License>();

  if (!license) throw new Error('Invalid license');
  if (license.user_id && license.user_id !== userId) throw new Error('License already used');
  if (new Date(license.expires_at) < new Date()) throw new Error('License expired');

  // Bind to user
  await env.DB!.prepare(
    `UPDATE licenses SET user_id = ? WHERE id = ?`
  ).bind(userId, license.id).run();

  return license;
}
```

The license is bound to the user; can't be reused.

## The "license revocation" pattern

For revocable licenses, use a "license check" endpoint:
```ts
// On every feature use
async function isFeatureLicensed(userId: string, feature: string, env: Env): Promise<boolean> {
  const license = await env.DB!.prepare(
    `SELECT * FROM licenses WHERE user_id = ? AND revoked_at IS NULL AND expires_at > ?`
  ).bind(userId, new Date().toISOString()).first<License>();

  if (!license) return false;

  const features = JSON.parse(license.features ?? '[]');
  return features.includes(feature);
}
```

The check is per-request; revocation is immediate.

## The "license caching" pattern

For performance, cache the license:
```ts
class LicenseCache {
  private cache = new Map<string, { license: License; expiresAt: number }>();

  async isFeatureLicensed(userId: string, feature: string, env: Env): Promise<boolean> {
    const cached = this.cache.get(userId);
    if (cached && cached.expiresAt > Date.now()) {
      return JSON.parse(cached.license.features).includes(feature);
    }

    const license = await fetchLicense(userId, env);
    if (license) {
      this.cache.set(userId, { license, expiresAt: Date.now() + 5 * 60_000 });
      return JSON.parse(license.features).includes(feature);
    }
    return false;
  }

  invalidate(userId: string) {
    this.cache.delete(userId);
  }
}
```

The cache is 5 min; revocation is delayed up to 5 min.

## The "offline grace period" pattern

For users who are sometimes offline, allow a grace period:
```ts
async function isFeatureLicensedWithGrace(userId: string, feature: string, env: Env): Promise<boolean> {
  const lastCheck = await env.KV.get(`last-license-check:${userId}`);
  const daysSinceLastCheck = lastCheck ? (Date.now() - parseInt(lastCheck)) / (24 * 60 * 60 * 1000) : 0;

  if (daysSinceLastCheck > 7) {
    // More than 7 days offline; verify the license
    const valid = await checkLicenseOnline(userId, env);
    if (!valid) return false;
    await env.KV.put(`last-license-check:${userId}`, String(Date.now()));
  }

  return true;
}
```

The user has 7 days of offline grace; after that, the
license is re-verified.

## The "feature entitlement" pattern

For fine-grained entitlements, store features per user:
```sql
CREATE TABLE user_features (
  user_id TEXT NOT NULL,
  feature TEXT NOT NULL,
  granted_at TEXT DEFAULT CURRENT_TIMESTAMP,
  expires_at TEXT,
  PRIMARY KEY (user_id, feature)
);
```

```ts
async function grantFeature(userId: string, feature: string, env: Env): Promise<void> {
  await env.DB!.prepare(
    `INSERT INTO user_features (user_id, feature) VALUES (?, ?)
     ON CONFLICT (user_id, feature) DO NOTHING`
  ).bind(userId, feature).run();
}

async function hasFeature(userId: string, feature: string, env: Env): Promise<boolean> {
  const row = await env.DB!.prepare(
    `SELECT 1 FROM user_features WHERE user_id = ? AND feature = ? AND (expires_at IS NULL OR expires_at > ?)`
  ).bind(userId, feature, new Date().toISOString()).first();
  return !!row;
}
```

The entitlements are per-user, per-feature.

## The "trial period" pattern

For trial users, set an expiration:
```ts
async function startTrial(userId: string, env: Env): Promise<void> {
  const expiresAt = new Date(Date.now() + 14 * 24 * 60 * 60 * 1000);  // 14 days
  await env.DB!.prepare(
    `INSERT INTO user_features (user_id, feature, expires_at) VALUES (?, 'pro', ?)
     ON CONFLICT (user_id, feature) DO UPDATE SET expires_at = ?`
  ).bind(userId, expiresAt.toISOString(), expiresAt.toISOString()).run();
}
```

The trial is automatic; the user gets pro features for 14
days.

## The "license server" provider

For managed license servers:
- **Cryptlex:** https://cryptlex.com/
- **Paddle:** https://paddle.com/
- **Gumroad:** https://gumroad.com/
- **Keygen:** https://keygen.sh/

For most apps, the entitlement is stored in your DB; the
billing is handled by Stripe/Paddle; the license is just
"is the user paying?"

## The "license" anti-patterns

### 1. License in client code
- **Symptom:** The license check is in JavaScript; users
  can modify it
- **Fix:** The check is on the server; the client is just
  a display

### 2. License as a boolean
- **Symptom:** `if (user.isLicensed)` — too coarse
- **Fix:** Per-feature entitlements

### 3. License without expiration
- **Symptom:** A license is forever; no trial, no renewal
- **Fix:** Always have an expiration

### 4. License without audit
- **Symptom:** You don't know who has which license
- **Fix:** Audit log for every grant + revocation

## Verification
- **Test:** License activation + check works
- **Test:** Expired license is rejected
- **Test:** Revoked license is rejected
- **Audit:** Annual review of license usage

## Gotchas
- **The "license check in the client" anti-pattern.** Always
  verify on the server.
- **The "no expiration" anti-pattern.** Always have an
  expiration; renew on payment.
- **The "no audit" anti-pattern.** Log every license event.
- **The "offline without grace" anti-pattern.** The user
  will be offline; plan for it.
- **The "revocation delay" anti-pattern.** A 5-min cache
  delay is usually OK; a 24-hour delay is too long.

## Related
- `feature-gating-implementation.md`
- `subscription-management.md` (later)
- `audit-log-as-product.md`
- `rate-limiting-strategies.md`
- Cryptlex: https://cryptlex.com/
- Keygen: https://keygen.sh/
