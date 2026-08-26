# Automated Secrets Rotation for Cloudflare Workers

- **Date**: 2026-08-22
- **Author**: example.com
- **Status**: production

## Symptom / Use-case

A Workers deployment stores database passwords, API keys, and webhook signing secrets
as Wrangler secrets (encrypted Worker environment variables). When those credentials
need to rotate — because of a breach, a compliance audit, a quarterly policy, or a
third-party provider forcing key expiry — the rotation must happen with zero downtime
and no configuration drift between environments. Without automation, secret rotation is
a manual, error-prone process that gets deferred until an incident forces it.

This article covers the full automated rotation lifecycle for Workers secrets: from
dual-credential support within the Worker itself, through the rotation script, to the
scheduled trigger and verification step. It is distinct from the general
`secrets-rotation-runbook.md` (which is server/VM-centric) and
`vault-dynamic-secrets-cloudflare-workers.md` (which uses Vault as the secrets source).

## Context

Cloudflare Workers secrets are set via the Workers API (or `wrangler secret put`). They
are:

1. **Per-deployment, per-environment** — `wrangler.toml` environments each have their
   own secret set.
2. **Not readable after write** — you cannot retrieve the current value of a secret via
   the API. You can only overwrite it or list which secrets exist.
3. **Immediately active** — after a `wrangler secret put`, the new value is live in the
   next request handled by any isolate in any Cloudflare colo. There is no deploy step
   required.
4. **Zero-downtime rotation requires dual-credential support** — the Worker must accept
   both old and new credentials simultaneously during the rotation window, then drop the
   old credential once the external service has been updated.

The Workers REST API endpoint for secrets is:

```
PUT /accounts/{account_id}/workers/scripts/{script_name}/secrets
```

## Dual-credential pattern

Design your Worker to accept an array of signing secrets or API keys, not a single value.
This enables rotation without any downtime:

```typescript
// src/auth.ts
export interface Env {
  // Comma-separated list of accepted API keys
  // "key1" during normal operation
  // "key1,key2" during rotation window
  // "key2" after rotation completes
  ACCEPTED_API_KEYS: string;

  // Same pattern for webhook signing secrets
  WEBHOOK_SIGNING_SECRETS: string;
}

export function validateApiKey(request: Request, env: Env): boolean {
  const providedKey = request.headers.get("x-api-key") ?? "";
  const acceptedKeys = env.ACCEPTED_API_KEYS.split(",").map(k => k.trim());
  return acceptedKeys.includes(providedKey);
}

export async function validateWebhookSignature(
  request: Request,
  env: Env,
  body: string
): Promise<boolean> {
  const signature = request.headers.get("x-hub-signature-256") ?? "";
  const secrets   = env.WEBHOOK_SIGNING_SECRETS.split(",").map(s => s.trim());

  for (const secret of secrets) {
    const key    = await crypto.subtle.importKey(
      "raw", new TextEncoder().encode(secret),
      { name: "HMAC", hash: "SHA-256" }, false, ["sign"]
    );
    const mac    = await crypto.subtle.sign("HMAC", key, new TextEncoder().encode(body));
    const hex    = Array.from(new Uint8Array(mac)).map(b => b.toString(16).padStart(2, "0")).join("");
    const expected = `sha256=${hex}`;
    if (signature === expected) return true;
  }
  return false;
}
```

## Rotation script

The rotation script uses the Cloudflare REST API to write updated secrets without
`wrangler` CLI — making it automation-friendly (runnable from CI, a cron Worker, or
a scheduled Lambda/Cloud Run job):

```python
#!/usr/bin/env python3
# scripts/rotate-secrets.py
"""
Rotate ACCEPTED_API_KEYS for a Cloudflare Worker.

Steps:
  1. Generate a new API key.
  2. Read the current secret value from a local state file (or Vault).
  3. Write old+new as the ACCEPTED_API_KEYS secret (dual-credential window).
  4. Call the external service to update its stored key to the new value.
  5. Sleep for the propagation window (60–120 s).
  6. Write only the new key as ACCEPTED_API_KEYS (close the window).
  7. Record the new key in state storage.
"""

import os, secrets, time, requests, json

ACCOUNT_ID   = os.environ["CF_ACCOUNT_ID"]
API_TOKEN    = os.environ["CF_API_TOKEN"]
SCRIPT_NAME  = os.environ["WORKER_SCRIPT_NAME"]   # e.g. "platform-api-production"
STATE_FILE   = "/var/run/secrets/current-api-key"  # or Vault path
EXTERNAL_API = os.environ["EXTERNAL_API_BASE_URL"]

CF_API = f"https://api.cloudflare.com/client/v4/accounts/{ACCOUNT_ID}/workers/scripts/{SCRIPT_NAME}/secrets"
HEADERS = {"Authorization": f"Bearer {API_TOKEN}", "Content-Type": "application/json"}


def set_secret(name: str, value: str) -> None:
    resp = requests.put(CF_API, headers=HEADERS,
                        json={"name": name, "text": value, "type": "secret_text"})
    resp.raise_for_status()
    print(f"[ok] set secret {name}")


def get_current_key() -> str:
    with open(STATE_FILE) as f:
        return f.read().strip()


def save_current_key(key: str) -> None:
    with open(STATE_FILE, "w") as f:
        f.write(key)


def update_external_service(new_key: str) -> None:
    resp = requests.post(f"{EXTERNAL_API}/rotate-key",
                         headers={"Authorization": f"Bearer {new_key}"},
                         json={"new_key": new_key})
    resp.raise_for_status()
    print("[ok] external service updated")


def main():
    current_key = get_current_key()
    new_key     = secrets.token_urlsafe(32)

    print(f"[1/5] generated new API key: {new_key[:8]}...")

    # Step 2: enable dual-credential window
    set_secret("ACCEPTED_API_KEYS", f"{current_key},{new_key}")
    print("[2/5] dual-credential window open")

    # Step 3: update the external service to use the new key
    update_external_service(new_key)
    print("[3/5] external service updated")

    # Step 4: wait for propagation and external service deployment
    wait_secs = int(os.environ.get("ROTATION_WAIT_SECS", "90"))
    print(f"[4/5] waiting {wait_secs}s for propagation...")
    time.sleep(wait_secs)

    # Step 5: close the window — only new key accepted
    set_secret("ACCEPTED_API_KEYS", new_key)
    print("[5/5] rotation complete, old key revoked")

    save_current_key(new_key)
    print("[done]")


if __name__ == "__main__":
    main()
```

## Scheduled rotation via GitHub Actions

```yaml
# .github/workflows/rotate-secrets.yml
name: Rotate Worker Secrets

on:
  schedule:
    - cron: "0 3 1 * *"   # 03:00 UTC on the 1st of each month
  workflow_dispatch:        # allow manual trigger

jobs:
  rotate:
    runs-on: ubuntu-latest
    environment: production   # uses GitHub environment protection rules
    steps:
      - uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.12"

      - name: Install dependencies
        run: pip install requests

      - name: Rotate secrets
        env:
          CF_ACCOUNT_ID:       ${{ secrets.CF_ACCOUNT_ID }}
          CF_API_TOKEN:        ${{ secrets.CF_API_TOKEN }}
          WORKER_SCRIPT_NAME:  platform-api-production
          EXTERNAL_API_BASE_URL: ${{ secrets.EXTERNAL_API_BASE_URL }}
          ROTATION_WAIT_SECS:  "90"
        run: python scripts/rotate-secrets.py

      - name: Notify on failure
        if: failure()
        uses: slackapi/slack-github-action@v2
        with:
          payload: |
            {"text": "Secret rotation FAILED for ${{ env.WORKER_SCRIPT_NAME }}. Investigate immediately."}
        env:
          SLACK_WEBHOOK_URL: ${{ secrets.SLACK_ROTATION_WEBHOOK }}
```

## Rotating multiple environments

When you have `staging` and `production` Workers, rotate staging first and validate
before rotating production:

```bash
# scripts/rotate-all-envs.sh
set -euo pipefail

ENVS=("staging" "production")

for env in "${ENVS[@]}"; do
  export WORKER_SCRIPT_NAME="platform-api-${env}"
  echo "=== Rotating ${env} ==="
  python scripts/rotate-secrets.py

  echo "=== Smoke-testing ${env} ==="
  STATUS=$(curl -sf -o /dev/null -w "%{http_code}" \
    -H "x-api-key: $(cat /var/run/secrets/current-api-key)" \
    "https://api-${env}.example.com/health")
  if [[ "$STATUS" != "200" ]]; then
    echo "SMOKE TEST FAILED for ${env}: HTTP ${STATUS}"
    exit 1
  fi
  echo "=== ${env} OK ==="
done
```

## Listing and auditing secrets

```bash
# List all secrets defined on a Worker (names only — values are not returned)
curl -s "https://api.cloudflare.com/client/v4/accounts/$CF_ACCOUNT_ID/workers/scripts/$SCRIPT_NAME/secrets" \
  -H "Authorization: Bearer $CF_API_TOKEN" | jq '[.result[] | .name]'

# Example output:
# ["ACCEPTED_API_KEYS", "DB_PASSWORD", "WEBHOOK_SIGNING_SECRETS"]
```

Use this in a weekly audit job to verify all expected secrets are present and alert on
unexpected additions or removals.

## Deleting stale secrets

After rotation, clean up any obsolete secret names:

```bash
curl -X DELETE \
  "https://api.cloudflare.com/client/v4/accounts/$CF_ACCOUNT_ID/workers/scripts/$SCRIPT_NAME/secrets/OLD_SECRET_NAME" \
  -H "Authorization: Bearer $CF_API_TOKEN"
```

## Anti-patterns

- Storing the current secret value in the rotation script itself — the script should
  read the current value from a secrets manager (Vault, GitHub Actions secrets, AWS
  Secrets Manager) or a secure state file, never hardcode it.
- Single-credential swap without a dual-credential window — any request in-flight during
  the swap will fail if it carries the old credential. The dual-credential window must
  remain open long enough for all active sessions to drain.
- Rotating without a rollback path — before revoking the old credential, confirm the
  external service has accepted the new one. Always have a script that can re-enable the
  old credential in under 60 seconds.
- Using `wrangler secret put` interactively in a CI pipeline — interactive prompts cause
  pipelines to hang. Use the REST API or `echo "value" | wrangler secret put NAME` for
  automation.
- Setting `ROTATION_WAIT_SECS` too short (< 60 s) — Cloudflare Worker isolates are
  cached globally; a new secret value propagates to all colos within seconds, but
  external services caching the old key may need up to 120 s to refresh.

## Gotchas

- The Workers Secrets API requires the `Workers Scripts: Edit` API token permission. The
  minimum-privilege token for rotation scripts should include only this permission scope,
  not a blanket account-level token.
- Cloudflare does not emit an event or webhook when a secret is updated. Build rotation
  confirmation by querying the secret list (names only) and verifying the expected key
  exists.
- If a Worker is in a CI/CD pipeline that deploys via `wrangler deploy`, running
  `wrangler deploy` after `wrangler secret put` will NOT reset secrets — `wrangler deploy`
  preserves existing secrets unless you re-specify them. However, using `wrangler deploy
  --config wrangler.toml` with secrets in the `vars` block (plain text, not secrets) will
  overwrite them and expose values in VCS. Always use the secrets API, not `vars`.
- The `text` field in the secrets PUT payload is the plaintext secret value. It is
  transmitted over HTTPS and encrypted at rest by Cloudflare, but it is visible in your
  rotation script's process environment and in CI logs if you echo it.
- Deleting a secret that a Worker references causes the Worker to throw a runtime error
  when it reads that binding. Always update the Worker code to stop referencing a secret
  before deleting it.

## Verification

```bash
# After rotation, verify the old key is rejected and the new key is accepted
NEW_KEY=$(cat /var/run/secrets/current-api-key)
OLD_KEY="<previous key>"

STATUS_NEW=$(curl -sf -o /dev/null -w "%{http_code}" \
  -H "x-api-key: $NEW_KEY" https://api.example.com/health)
STATUS_OLD=$(curl -sf -o /dev/null -w "%{http_code}" \
  -H "x-api-key: $OLD_KEY" https://api.example.com/health)

echo "New key HTTP: $STATUS_NEW"   # Expected: 200
echo "Old key HTTP: $STATUS_OLD"   # Expected: 401

# Verify secrets list still contains the expected names
curl -s "https://api.cloudflare.com/client/v4/accounts/$CF_ACCOUNT_ID/workers/scripts/$SCRIPT_NAME/secrets" \
  -H "Authorization: Bearer $CF_API_TOKEN" | jq '[.result[] | .name] | sort'
# Expected: ["ACCEPTED_API_KEYS", "DB_PASSWORD", "WEBHOOK_SIGNING_SECRETS"]
```

## Related

- secrets-rotation-runbook.md
- vault-dynamic-secrets-cloudflare-workers.md
- secrets-management-comparison.md
- cloudflare-workers-limits-resource-planning.md
- wrangler-toml-multi-environment-config.md

## Sources

- https://developers.cloudflare.com/workers/configuration/secrets/
- https://developers.cloudflare.com/api/resources/workers/subresources/scripts/subresources/secrets/
- https://developers.cloudflare.com/fundamentals/api/get-started/create-token/
- https://docs.github.com/en/actions/security-for-github-actions/security-guides/using-secrets-in-github-actions
- https://cheatsheetseries.owasp.org/cheatsheets/Secrets_Management_Cheat_Sheet.html
