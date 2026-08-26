# secrets-rotation-runbook

**Issue:** How to rotate a leaked secret without downtime
**Date:** 2026-08-09
**Status:** documented (runbook)

## Symptom
A token / API key / secret was leaked (committed to git, posted
in chat, etc.). The token has been in multiple places you don't
control. You need to invalidate it without taking the system
down.

## Root cause
Secrets leak. The mitigation is a fast, rehearsed rotation
procedure. Without one, you either:
- Don't rotate (keep using the leaked secret — risky)
- Rotate ad-hoc (forget a step, system goes down for hours)

**Source:** NIST SP 800-57 (Key management recommendations):
https://csrc.nist.gov/publications/detail/sp/800-57-part-1-rev-5/final

## Fix
A 7-step rotation runbook:

### Step 1: Identify the leak scope
- Where was the secret posted? (chat, git, email, ticket)
- Who could have seen it? (1 person, 1 team, public)
- How long was it exposed? (seconds, hours, days)
- What can the secret do? (read-only, read-write, admin)

### Step 2: Generate the new secret
In the source system (GitHub PAT settings, CF API token page, etc.):
- Generate a new secret with the SAME scopes as the old
- (Optional) Tighten the scopes if the old was over-scoped
- Save the new secret in your secret manager (1Password,
  Vault, CF Workers Secrets)

### Step 3: Update the secret in production
For each environment (dev, staging, prod):
- Update the secret in the secret store
- Trigger a redeploy (CF Pages + Workers auto-read secrets at
  isolate init)
- Verify the new secret is in use (`console.log(env.SECRET.slice(0, 4))`)

### Step 4: Update local dev environments
- Update `.env` (gitignored) for each developer
- Update the CI environment (encrypted secrets)
- Update the test fixtures (if any)

### Step 5: Revoke the old secret
- Revoke in the source system (the "Revoke" button)
- Verify the old secret no longer works (`curl` with the old
  secret → 401)
- Document the revocation time in the incident log

### Step 6: Audit usage
- Pull access logs from the source system (GH API audit log, CF
  audit log, etc.)
- Identify any access using the old secret between the leak
  time and the revocation time
- Treat that access as compromised (rotate any downstream
  resources accessed)

### Step 7: Post-incident review
- Why did the leak happen? (gitleaks miss, manual paste, etc.)
- What control would have caught it? (pre-commit hook, CI check,
  better secret manager)
- Add the control + test it
- Update the runbook with any lessons

## Verification
- **Test:** Drill the runbook in staging (not prod) quarterly
- **Live:** Rotation time < 30 minutes for non-critical secrets;
  < 5 minutes for critical (deploy-time)
- **Audit:** Annual review of rotation cadence

## Gotchas
- **Don't reuse secret names.** A new CF token shouldn't have
  the same name as the old — easier to confuse.
- **Don't share secrets across environments.** Dev, staging, prod
  each get their own. Compromise of dev ≠ compromise of prod.
- **Don't put secrets in URLs.** URLs are logged. CF Pages has
  `env.SECRET` for safe storage.
- **CF Workers secrets are encrypted at rest.** Use `wrangler secret put`
  (interactive) or `wrangler secret put --var` (CI) to set them.
  They show up in the dashboard as encrypted.
- **For GH PATs, use the fine-grained PAT** (not the classic).
  Each fine-grained PAT can be scoped to a single repo and a
  specific set of permissions. The blast radius of a leak is
  much smaller.

## Related
- `security/gitleaks-cloudflare-webhook.md` (prevent the leak)
- `github/pat-self-merge-workaround.md` (uses a PAT — rotate after)
- NIST SP 800-57: https://csrc.nist.gov/publications/detail/sp/800-57-part-1-rev-5/final
- GH fine-grained PAT: https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/managing-your-personal-access-tokens
