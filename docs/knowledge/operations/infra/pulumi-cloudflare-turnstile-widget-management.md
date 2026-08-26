# Pulumi: Cloudflare Turnstile Widget Management

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case
You need to provision and rotate Cloudflare Turnstile widgets (CAPTCHA-replacement) programmatically across multiple environments and domains, and want the site keys and secret keys surfaced as stack outputs for consumption by application config.

## Context
Cloudflare Turnstile replaces traditional CAPTCHAs with a privacy-preserving challenge that runs in the browser. Each widget is scoped to one or more hostnames and has a configurable mode (`managed`, `non-interactive`, `invisible`). Pulumi's `@pulumi/cloudflare` SDK (v5+) exposes `cloudflare.TurnstileWidget` for full lifecycle management. Secret keys must never be committed to version control; Pulumi ESC or stack secrets are the correct storage.

## Defining Widgets per Environment

```typescript
import * as pulumi from "@pulumi/pulumi";
import * as cloudflare from "@pulumi/cloudflare";

const config = new pulumi.Config();
const accountId = config.require("accountId");
const stack = pulumi.getStack(); // "staging" | "production"

const isProd = stack === "production";

// Managed widget for the login page — applies interactive challenge when needed
const loginWidget = new cloudflare.TurnstileWidget("login-widget", {
  accountId,
  name: `login-${stack}`,
  domains: isProd
    ? ["example.com", "www.example.com"]
    : [`${stack}.example.com`],
  mode: "managed",
  // botFightMode is mutually exclusive with invisible mode
  offlabel: false,
  region: "world",
});

// Invisible widget for checkout — challenge runs silently in the background
const checkoutWidget = new cloudflare.TurnstileWidget("checkout-widget", {
  accountId,
  name: `checkout-${stack}`,
  domains: isProd
    ? ["example.com"]
    : [`${stack}.example.com`],
  mode: "invisible",
  offlabel: false,
  region: "world",
});
```

## Exporting Keys as Stack Secrets

```typescript
// Site keys are public; secret keys must be treated as sensitive
export const loginSiteKey = loginWidget.id;
export const loginSecretKey = pulumi.secret(loginWidget.secret);

export const checkoutSiteKey = checkoutWidget.id;
export const checkoutSecretKey = pulumi.secret(checkoutWidget.secret);

// Write keys to Cloudflare Workers secrets via the Workers secrets resource
// so the validation Worker can read them at runtime without any env-var injection
const loginSecretWorkerSecret = new cloudflare.WorkerSecret(
  "login-turnstile-secret",
  {
    accountId,
    name: "TURNSTILE_SECRET_KEY",
    scriptName: `auth-worker-${stack}`,
    secretText: loginWidget.secret,
  }
);
```

## Validating Tokens in a Cloudflare Worker

```typescript
// auth-worker/src/index.ts — runs at edge, validates Turnstile token server-side
export interface Env {
  TURNSTILE_SECRET_KEY: string;
}

interface TurnstileResponse {
  success: boolean;
  "error-codes": string[];
  challenge_ts: string;
  hostname: string;
  action?: string;
  cdata?: string;
}

async function verifyTurnstileToken(
  token: string,
  ip: string,
  secretKey: string
): Promise<TurnstileResponse> {
  const body = new URLSearchParams({
    secret: secretKey,
    response: token,
    remoteip: ip,
  });

  const res = await fetch(
    "https://challenges.cloudflare.com/turnstile/v0/siteverify",
    {
      method: "POST",
      body,
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
    }
  );

  if (!res.ok) {
    throw new Error(`Turnstile API error: ${res.status}`);
  }
  return res.json<TurnstileResponse>();
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    if (request.method !== "POST") {
      return new Response("Method Not Allowed", { status: 405 });
    }

    const { token } = await request.json<{ token: string }>();
    if (!token) {
      return Response.json({ error: "missing_token" }, { status: 400 });
    }

    const ip = request.headers.get("CF-Connecting-IP") ?? "";
    let result: TurnstileResponse;

    try {
      result = await verifyTurnstileToken(token, ip, env.TURNSTILE_SECRET_KEY);
    } catch (err) {
      return Response.json({ error: "verification_failed" }, { status: 502 });
    }

    if (!result.success) {
      return Response.json(
        { error: "challenge_failed", codes: result["error-codes"] },
        { status: 403 }
      );
    }

    return Response.json({ verified: true, ts: result.challenge_ts });
  },
};
```

## Rotating the Secret Key

```typescript
// Force a secret key rotation by toggling the `rotation` meta-argument pattern.
// Cloudflare generates a new secret when the widget is deleted and recreated,
// or when you call the rotation API. Use a Pulumi Command resource for in-place rotation.
import * as command from "@pulumi/command";

const rotateTurnstile = new command.local.Command("rotate-login-widget", {
  create: pulumi.interpolate`curl -s -X POST \
    "https://api.cloudflare.com/client/v4/accounts/${accountId}/challenges/widgets/${loginWidget.id}/rotate_secret" \
    -H "Authorization: Bearer $CF_API_TOKEN" \
    -H "Content-Type: application/json" \
    -d '{"invalidate_immediately": false}'`,
  // Only run when explicitly triggered; do not run on every `pulumi up`
  // Trigger via: pulumi up --target 'urn:...rotate-login-widget'
});
```

## Anti-patterns
- Storing the Turnstile secret key in plaintext stack config — always wrap with `pulumi.secret()` or use Pulumi ESC
- Validating the Turnstile token client-side — the `siteverify` endpoint must be called server-side; client-side bypass is trivial
- Reusing one widget across staging and production — different `domains` lists mean a production token cannot be forged using a staging secret
- Omitting `remoteip` in `siteverify` — weakens replay-attack protection; always pass the `CF-Connecting-IP` header value
- Using `mode: "invisible"` on sensitive actions where a visible challenge signals to users that security checks are active

## Gotchas
- `loginWidget.id` is the public site key (the value you pass to the browser JS); `loginWidget.secret` is the private key for server-side verification — they are separate fields
- Adding a hostname to `domains` that is not served through Cloudflare will not cause a Pulumi error but Turnstile will reject tokens from those hostnames at runtime
- Deleting a `TurnstileWidget` resource immediately invalidates all outstanding tokens — plan rotations with `invalidate_immediately: false` to allow drain time
- The `offlabel` field controls the Turnstile branding badge; setting it to `true` requires a paid Cloudflare plan
- Widget names are display-only in the dashboard; uniqueness is not enforced by the API, so use stack name suffixes to avoid confusion

## Verification
```bash
# List all Turnstile widgets in the account
curl -s "https://api.cloudflare.com/client/v4/accounts/$CF_ACCOUNT_ID/challenges/widgets" \
  -H "Authorization: Bearer $CF_API_TOKEN" | jq '.result[] | {sitekey, name, domains, mode}'

# Smoke-test server-side verification with a dummy token (returns success:false, expected)
curl -s -X POST "https://challenges.cloudflare.com/turnstile/v0/siteverify" \
  -d "secret=$TURNSTILE_SECRET_KEY&response=DUMMY_TOKEN" | jq '.success, .["error-codes"]'

# Check Pulumi stack outputs
pulumi stack output --show-secrets | grep -E 'SiteKey|SecretKey'
```

## Related
- `cloudflare-turnstile-terraform-management.md` — Terraform equivalent for Turnstile widget provisioning
- `pulumi-cloudflare-workers-infrastructure-as-code.md` — Workers infrastructure with Pulumi
- `pulumi-cloudflare-workers-secrets-store.md` — secret injection into Workers via Pulumi
- `pulumi-esc-secrets-config-management.md` — Pulumi ESC for secure secret storage

## Sources
- https://developers.cloudflare.com/turnstile/
- https://developers.cloudflare.com/turnstile/get-started/server-side-validation/
- https://www.pulumi.com/registry/packages/cloudflare/api-docs/turnstilewidget/
- https://developers.cloudflare.com/turnstile/reference/api/
- https://developers.cloudflare.com/turnstile/concepts/widget-types/
