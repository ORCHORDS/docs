# feature-cookbook-secret-management

**Issue:** Secret management — API keys, tokens, encryption
**Date:** 2026-08-09
**Status:** documented

## Symptom
You commit an API key to the repo. GitHub detects it.
You rotate the key. The team's CI is broken because
they pulled the repo. The breach notification says
"your key was exposed for 3 days."

## Root cause
**Secrets in code are exposed.** Use a secret manager.

**Source:** OWASP — Secrets Management Cheat Sheet:
https://cheatsheetseries.owasp.org/cheatsheets/Secrets_Management_Cheat_Sheet.html

## The "secret manager" pattern

For secrets, use a secret manager:
- **CF Workers:** Environment variables / secrets
- **AWS Secrets Manager:** Managed secrets
- **GCP Secret Manager:** Managed secrets
- **HashiCorp Vault:** Self-hosted
- **1Password:** Team secrets

For most apps, **CF env vars / secrets** is enough.

## The "CF Workers secret" pattern

For CF Workers, use `wrangler secret`:
```bash
# Set
wrangler secret put STRIPE_API_KEY

# Get (in the code)
const apiKey = env.STRIPE_API_KEY;
```

The secret is in CF, not in code.

## The "wrangler.toml" anti-pattern

Don't put secrets in `wrangler.toml`:
```toml
# ❌ Bad: secret in the file
[vars]
STRIPE_API_KEY = "sk_live_abc123"
```

`wrangler.toml` is committed. Use `wrangler secret` for
secrets.

## The "secret rotation" pattern

For secret rotation:
1. **Generate:** New key in the vendor
2. **Add:** Add the new key to the secret manager
3. **Deploy:** Deploy with both keys
4. **Migrate:** Switch reads to the new key
5. **Remove:** Remove the old key
6. **Audit:** Verify only the new key is in use

```ts
// Phase 1: dual-key
const apiKey = env.STRIPE_API_KEY_PRIMARY ?? env.STRIPE_API_KEY_SECONDARY;

// Phase 2: new only
const apiKey = env.STRIPE_API_KEY_PRIMARY;
```

The secret is rotated without downtime.

## The "secret scope" pattern

For secret scope:
- **Global:** Used everywhere (e.g. analytics key)
- **Per-environment:** dev, staging, prod
- **Per-tenant:** Each tenant has their own secrets

```bash
# Per-env
wrangler secret put STRIPE_API_KEY --env production
wrangler secret put STRIPE_API_KEY --env staging
```

The scope is enforced.

## The "secret audit" pattern

For an audit:
- **Who has access?** List of users
- **When was it last used?** Last access time
- **Is it still needed?** Yes / no
- **When was it last rotated?** Date

```ts
async function auditSecrets(env: Env): Promise<void> {
  const secrets = await listSecrets(env);
  for (const secret of secrets) {
    const lastUsed = await getLastUsed(secret.name, env);
    const lastRotated = await getLastRotated(secret.name, env);
    const daysSinceRotated = (Date.now() - lastRotated) / (24 * 60 * 60 * 1000);

    if (daysSinceRotated > 90) {
      logEvent('secret.rotation_overdue', 'warn', { name: secret.name, daysSinceRotated });
    }
  }
}
```

The audit catches the issue.

## The "secret in code" detection

For detection, use gitleaks / trufflehog:
```bash
# .gitleaks.toml
[extend]
useDefault = true

# Detect on pre-commit
pre-commit run gitleaks --all-files
```

The detection catches leaks before commit.

## The "secret leak" response

For a leak:
1. **Rotate:** Immediately
2. **Revoke:** Old key
3. **Audit:** Was the key used? Where?
4. **Notify:** Affected users / vendor
5. **Post-mortem:** How did it leak?

```ts
async function onSecretLeak(secret: string, env: Env): Promise<void> {
  await logEvent('secret.leaked', 'critical', { secret: <redacted-secret> 8) + '***' });
  await pageOnCall({ severity: 'critical', message: `Secret leaked: ${secret}` });
}
```

The response is fast.

## The "encryption" pattern

For encryption at rest:
- **AES-256-GCM:** Symmetric, fast
- **RSA / EC:** Asymmetric, for key exchange
- **libsodium:** Modern crypto library

```ts
import nacl from 'tweetnacl';

const key = nacl.randomBytes(32);  // 256-bit key
const nonce = nacl.randomBytes(24);
const ciphertext = nacl.secretbox(message, nonce, key);
```

The encryption is at rest.

## The "key derivation" pattern

For key derivation:
- **PBKDF2:** Password-based, slow (max 100k iter)
- **Argon2id:** Modern, slow, memory-hard
- **scrypt:** Memory-hard, slower than PBKDF2

For new apps, **Argon2id** is the standard.

```ts
import { hash, verify } from '@noble/hashes/argon2';

const hashed = await hash(password, { t: 3, m: 65536, p: 1 });
const valid = await verify(hashed, password);
```

The password is hashed.

## The "encryption key" pattern

For the encryption key:
- **Generate:** 256-bit random
- **Store:** In a secret manager
- **Rotate:** Every 90 days
- **Backup:** With a different vendor

```ts
// Generate
const key = crypto.getRandomValues(new Uint8Array(32));

// Store
await env.SECRETS.put('encryption_key', base64Encode(key));

// Use
const encryptionKey = base64Decode(await env.SECRETS.get('encryption_key')!);
```

The key is in the secret manager.

## The "secret anti-pattern" anti-patterns

### 1. Secret in code
- **Issue:** Git history has the secret forever
- **Fix:** Use a secret manager

### 2. Secret in wrangler.toml
- **Issue:** Committed to the repo
- **Fix:** Use `wrangler secret`

### 3. No rotation
- **Issue:** A leaked secret is valid forever
- **Fix:** Rotate every 90 days

### 4. Shared secret
- **Issue:** One team's leak affects all
- **Fix:** Per-team / per-tenant secrets

### 5. No audit
- **Issue:** Stale secrets accumulate
- **Fix:** Audit + alert on stale

### 6. Plaintext at rest
- **Issue:** DB compromise leaks all secrets
- **Fix:** Encrypt at rest

## Verification
- **Test:** No secret in code
- **Test:** Secret rotation works
- **Test:** Audit catches stale secrets
- **Live:** Secret usage is logged
- **Audit:** Quarterly secret review

## Gotchas
- **The "secret in code" anti-pattern.** Use a secret
  manager.
- **The "no rotation" anti-pattern.** Rotate every 90
  days.
- **The "shared secret" anti-pattern.** Per-team /
  per-tenant secrets.
- **The "plaintext at rest" anti-pattern.** Encrypt at
  rest.

## Related
- `secrets-rotation-runbook.md`
- `secrets-encryption-at-rest.md`
- `encryption-at-rest-detail.md`
- `password-storage-argon2.md`
- `gitleaks-cloudflare-webhook.md`
- `feature-cookbook-auth.md`
- `cloudflare/secret-management.md` (planned)
- OWASP: https://cheatsheetseries.owasp.org/cheatsheets/Secrets_Management_Cheat_Sheet.html
