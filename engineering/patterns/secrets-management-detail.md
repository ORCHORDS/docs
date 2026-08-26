# secrets-management-detail

**Issue:** Where to store secrets, how to rotate, what NOT to do
**Date:** 2026-08-09
**Status:** documented

## Symptom
Your Stripe secret key is in the codebase. The code is
on GitHub. A bot scrapes it. Stripe emails you "suspicious
activity." You rotate the key. You search the codebase
for the old key. It's in 20 places. You miss one. The
bot still has the old key. You spend a week cleaning up.

## Root cause
**Secrets in code are a security incident waiting to
happen.** A secret in a Git repo, a Slack message, an
email, a log file — all of these are leaks.

**Source:** OWASP — Secrets Management:
https://cheatsheetseries.owasp.org/cheatsheets/Secrets_Management_Cheat_Sheet.html

> "Secrets must be stored securely, rotated regularly,
> and never committed to source code."

## The 6 categories of secrets

| Type | Examples | Storage |
|---|---|---|
| **API keys** | Stripe, OpenAI, SendGrid | Cloud secret manager |
| **DB credentials** | D1 read/write, postgres | Cloud secret manager |
| **JWT signing keys** | HMAC secret, RSA private | HSM / KMS |
| **OAuth client secrets** | Google, Apple | Cloud secret manager |
| **Encryption keys** | At-rest data encryption | KMS / HSM |
| **Internal service tokens** | Service-to-service auth | Cloud secret manager |

## The "secret manager" pattern

Use a secret manager (CF Workers secrets, AWS Secrets
Manager, HashiCorp Vault):

```bash
# CF Workers: store a secret
echo "sk_live_..." | wrangler secret put STRIPE_SECRET_KEY

# Access in code
const stripeKey = env.STRIPE_SECRET_KEY;
```

```ts
// In a Worker
export default {
  async fetch(request: Request, env: Env) {
    const stripeKey = env.STRIPE_SECRET_KEY;  // From env binding
    // ... use it
  },
};
```

The secret is encrypted at rest. The code never sees the
plaintext; the binding does.

## The "secret rotation" pattern

For each secret, define a rotation policy:
- **High-value (DB master, encryption key):** Every 90 days
- **Medium (vendor API key):** Every 180 days
- **Low (dev API key):** Every 365 days
- **Emergency (compromised):** Immediately

```bash
# Generate a new key
NEW_KEY="sk_live_$(openssl rand -hex 32)"

# Add the new key (dual-key period)
echo "$NEW_KEY" | wrangler secret put STRIPE_SECRET_KEY_NEW

# Update the code to use both (verify with new, fail over to old)
const key = env.STRIPE_SECRET_KEY_NEW ?? env.STRIPE_SECRET_KEY;

# After verification, remove the old key
wrangler secret delete STRIPE_SECRET_KEY
```

The "dual-key" period lets you verify the new key works
before removing the old.

## The "secret in env file" anti-pattern

```bash
# ❌ Never do this
echo "STRIPE_SECRET_KEY=sk_live_..." > .env
git add .env
git commit
```

The `.env` file is in the repo. The secret is leaked.

**Solutions:**
1. **Use the secret manager** (the right answer)
2. **Use `.gitignore`** (but local files can still leak)
3. **Use a "secret manager for local dev"** (CF's
   `wrangler dev` reads from `.dev.vars`, which is
   gitignored)

## The ".gitignore" essentials

```gitignore
# Environment files
.env
.env.local
.env.*.local
.dev.vars
.dev.vars.*

# Secrets
*.pem
*.key
*.p12

# Local config
config.local.json
secrets.json
```

The `.env` and `.dev.vars` files should never be committed.

## The "gitleaks" pattern

For automated secret detection:
```bash
# Install
brew install gitleaks

# Scan the repo
gitleaks detect --source . --verbose

# Pre-commit hook
gitleaks protect --staged --verbose
```

Gitleaks scans every commit for known secret patterns
(Stripe, OpenAI, AWS, etc.).

For CF, use the `gitleaks-cloudflare-webhook.md` pattern to
scan in real-time.

## The "secret in logs" anti-pattern

```ts
// ❌ Never log secrets
console.log({ msg: 'stripe.request', apiKey: env.STRIPE_SECRET_KEY });

// ❌ Never log the full request/response
console.log({ msg: 'stripe.response', body: response });

// ✅ Log the metadata, not the secret
console.log({ msg: 'stripe.request', endpoint: '/v1/charges', amount: 100 });
```

PII in logs is a GDPR issue. Secrets in logs are catastrophic.

## The "secret in error message" anti-pattern

```ts
// ❌ Bad: leaks the secret in the error
throw new Error(`Failed to authenticate with ${apiKey}`);

// ✅ Good: log the failure, not the secret
throw new Error('Authentication failed');
```

Error messages are often logged. Make them safe.

## The "secret in URL" anti-pattern

```ts
// ❌ Bad: secret in URL (often logged)
fetch(`https://api.example.com/?api_key=<redacted-secret>

// ✅ Good: secret in header
fetch('https://api.example.com/', { headers: { 'Authorization': `Bearer ${secret}` } });
```

URLs are in browser history, server logs, and proxies. The
header is in fewer places.

## The "secret in client" anti-pattern

```ts
// ❌ Never expose secrets to the client
const stripeKey = env.STRIPE_SECRET_KEY;  // Server-only
// ... send to client ... ❌ NO

// ✅ Use a publishable key on the client
const stripePublishable = env.STRIPE_PUBLISHABLE_KEY;  // Safe for client
// ... send to client ... ✅ OK
```

Stripe has separate publishable (client) and secret (server)
keys. Use them correctly.

## The "secret in CI" pattern

For CI:
- **GitHub Actions:** Use repository secrets (encrypted) +
  GitHub OIDC for cloud auth
- **CF Workers:** Use `wrangler secret put` for prod
- **Local:** Use `.dev.vars` (gitignored)

```yaml
# GitHub Actions
- name: Deploy
  env:
    CLOUDFLARE_API_TOKEN: ${{ secrets.CLOUDFLARE_API_TOKEN }}
  run: wrangler deploy
```

The GitHub secret is encrypted; only the workflow sees it.

## The "secret leak response" pattern

If a secret is leaked:
1. **Rotate immediately** (don't wait)
2. **Audit usage** (who used it, when, where)
3. **Notify the vendor** (they may want to disable the key)
4. **Search the codebase + history** (find all references)
5. **Document the incident** (post-mortem)
6. **Update the prevention** (add a check that catches this)

The time-to-rotate is critical. The longer the leaked secret
is valid, the more damage.

## Verification
- **Test:** `test/secrets.test.ts > no secrets in code, .env
  is in .gitignore` — passes
- **Live:** Gitleaks runs on every commit + PR
- **Audit:** Quarterly review of secret rotation

## Gotchas
- **The "I'll rotate later" anti-pattern.** Rotate now, not
  later. The leaked secret can be exploited in seconds.
- **The "secret in a comment" anti-pattern.** A comment with
  `// API key: sk_live_...` is just as leaked as the code.
- **The "secret in a screenshot" anti-pattern.** Don't
  screenshot secrets in Slack or docs.
- **The "secret in a test fixture" anti-pattern.** Test
  fixtures should use mock secrets, not real ones.
- **The "secret in a hot path" performance issue.** Each
  secret lookup is a network call (in some managers). For
  hot paths, cache the secret in memory (with a TTL).
- **The "shared secret" anti-pattern.** Each environment
  should have its own secrets. Don't share dev/staging/prod
  keys.

## Related
- `secrets-encryption-at-rest.md`
- `secrets-rotation-runbook.md`
- `gitleaks-cloudflare-webhook.md`
- `api-key-authentication.md`
- OWASP: https://cheatsheetseries.owasp.org/cheatsheets/Secrets_Management_Cheat_Sheet.html
- CF secrets: https://developers.cloudflare.com/workers/configuration/secrets/
