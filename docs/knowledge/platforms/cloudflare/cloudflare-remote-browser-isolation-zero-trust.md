# Cloudflare Remote Browser Isolation (RBI) for Zero Trust

Date: 2026-08-23
Author: example.com
Status: production

## Symptom / Use-case

Employees visiting risky websites, using personal SaaS applications, or running
unmanaged third-party portals expose endpoints to drive-by downloads, credential
harvesting, and clipboard exfiltration. Traditional endpoint AV and URL filtering catch
known threats but fail against novel zero-days embedded in legitimate sites. You need a
way to let users access these sites safely without blocking productivity.

Cloudflare Remote Browser Isolation (RBI) renders web content in a hardened Chromium
instance on Cloudflare's network and streams only the visual output to the user's
browser — no web content (HTML, JS, CSS, plugins) ever executes locally.

## Context

Cloudflare RBI is part of the **Zero Trust Network Access** product suite, available
under Cloudflare One. It integrates with:

- **Cloudflare Gateway HTTP policies** — trigger isolation on URL categories, domains,
  or content inspection rules
- **Cloudflare Access** — optionally isolate specific internal applications accessed
  via Access without requiring device posture
- **WARP client** — routes user traffic through Gateway when enabled; no WARP required
  for clientless RBI via a Browser-Rendered URL

RBI modes:
| Mode | What executes locally | Use-case |
|------|----------------------|----------|
| **Remote** | Nothing (pure pixel stream) | Highest security; known-risky sites |
| **Remote with local rendering** | HTML/CSS (no JS) | Balanced; productivity SaaS |
| **Clientless** | Normal browser (isolated URL prefix) | Contractors without WARP |

## Enabling RBI via Gateway HTTP Policy

RBI is activated through a Gateway HTTP policy action set to `Isolate`:

### Step 1: Create an Isolation Profile

In the Cloudflare Zero Trust Dashboard (one.cloudflare.com):

1. Go to **Settings → Browser Isolation**
2. Under **Remote Browser** settings:
   - Enable **Disable Copy/Paste** for DLP-sensitive categories
   - Enable **Disable Printing** for confidential content
   - Enable **Disable File Downloads** for high-risk sites
   - Enable **Disable Keyboard Input** for read-only review sessions
3. Optionally enable **Disable Clipboard Upload** to prevent data exfiltration via paste

Multiple isolation profiles can be created and referenced in different HTTP policies,
allowing tiered isolation (risky sites fully locked down, productivity SaaS with
copy-paste allowed).

### Step 2: Gateway HTTP Policy for Automatic Isolation

```
# Gateway HTTP Policy — configure via Dashboard or Terraform

Policy name: "Isolate Risky Categories"
When: [
  Matches "Security Risks" URL category       OR
  Matches "Newly Registered Domains" category OR
  Host matches regex: ".*\\.xyz$"
]
Then: Isolate
  Profile: "Strict Isolation"
  (Disable download, paste, print)
```

Terraform equivalent:

```hcl
resource "cloudflare_teams_rule" "isolate_risky" {
  account_id  = var.account_id
  name        = "Isolate Risky Categories"
  description = "Remote browser isolation for high-risk content"
  precedence  = 100
  action      = "isolate"
  enabled     = true

  filters = ["http"]

  traffic = <<-EOT
    (http.request.uri.category in {"Security Risks" "Newly Registered Domains"})
    or
    (http.request.host matches ".*\\.xyz$")
  EOT

  rule_settings {
    browser_isolation {
      url_browser_isolation_enabled = true
    }
    # Optionally reference an isolation profile by ID
  }
}

resource "cloudflare_teams_rule" "allow_known_good" {
  account_id = var.account_id
  name       = "Allow Known Good Sites"
  precedence = 50   # evaluated before the isolate rule
  action     = "allow"
  enabled    = true
  filters    = ["http"]

  traffic = "http.request.host in {\"github.com\" \"npmjs.com\" \"pypi.org\"}"
}
```

### Step 3: Clientless Isolation for Contractors

For users without the WARP client (contractors, BYOD), Cloudflare provides a
**clientless RBI URL** in the format:

```
https://<team-name>.cloudflareaccess.com/browser/<URL>
```

Example:
```
https://myorg.cloudflareaccess.com/browser/https://vendorportal.example.com
```

Wrap this in an Access application so only authenticated identities can launch
the clientless session:

```hcl
resource "cloudflare_access_application" "vendor_portal_isolated" {
  account_id       = var.account_id
  name             = "Vendor Portal (Isolated)"
  domain           = "myorg.cloudflareaccess.com/browser/https://vendorportal.example.com"
  type             = "self_hosted"
  session_duration = "8h"

  # Restrict to vendor group
}

resource "cloudflare_access_policy" "vendor_group" {
  application_id = cloudflare_access_application.vendor_portal_isolated.id
  account_id     = var.account_id
  name           = "Vendors Only"
  precedence     = 1
  decision       = "allow"

  include {
    group = [var.vendor_access_group_id]
  }
}
```

## Workers Integration: Injecting Context into Isolated Sessions

A Cloudflare Worker can run as an **Access Service Token** proxy in front of an
internally-hosted site before it is delivered to the RBI browser. This allows
injecting tenant context, stripping PII from responses, or watermarking pages:

```typescript
// src/rbi-context-injector.ts
// Deployed as an Access-protected Worker that sits in front of an internal app.
// The RBI browser accesses the Worker; the Worker fetches the real app via Tunnel.

export interface Env {
  // Tunnel-accessible internal app
  INTERNAL_APP_URL: string;
  // D1 for audit logging of accessed URLs
  AUDIT_DB: D1Database;
}

export default {
  async fetch(request: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    // Cloudflare Access injects the verified user identity
    const userEmail = request.headers.get('Cf-Access-Authenticated-User-Email') ?? 'unknown';
    const userJWT   = request.headers.get('Cf-Access-Jwt-Assertion');

    // Audit log the access (fire-and-forget)
    ctx.waitUntil(
      env.AUDIT_DB.prepare(
        'INSERT INTO access_log (user_email, url, accessed_at) VALUES (?, ?, datetime("now"))'
      ).bind(userEmail, request.url).run()
    );

    // Forward to internal app
    const internalURL = new URL(request.url);
    internalURL.hostname = new URL(env.INTERNAL_APP_URL).hostname;

    const internalRequest = new Request(internalURL.toString(), {
      method: request.method,
      headers: request.headers,
      body: request.body,
    });

    const response = await fetch(internalRequest);
    const ct = response.headers.get('content-type') ?? '';

    // Inject watermark into HTML responses
    if (ct.includes('text/html')) {
      const text = await response.text();
      const watermark = `
        <div style="position:fixed;bottom:4px;right:8px;opacity:0.4;font-size:11px;
                    color:#999;pointer-events:none;z-index:99999;font-family:monospace">
          ${userEmail} · ${new Date().toISOString().slice(0, 10)}
        </div>`;
      const watermarked = text.replace('</body>', `${watermark}</body>`);

      return new Response(watermarked, {
        status: response.status,
        headers: { ...Object.fromEntries(response.headers), 'Content-Type': 'text/html; charset=utf-8' },
      });
    }

    return response;
  },
};
```

## Anti-patterns

- **Using RBI as your only security control** — RBI prevents client-side code execution
  but does not prevent a user from *photographing their screen* with a phone, or from
  typing data into a web form that exfiltrates it to a server. Pair with DLP policies
  and Access group restrictions.
- **Isolating all traffic by default** — RBI adds ~50-100 ms of latency and some
  rendering overhead. Applying it to `*` will degrade productivity for known-safe sites.
  Use category-based policies targeting high-risk groups (newly registered domains,
  security threats, uncategorized).
- **Relying on URL categories without also adding custom domains** — Category databases
  lag behind new phishing sites. Supplement with a custom blocklist or Gateway's DNS
  inspection for zero-day domains.
- **Disabling paste for productivity SaaS** — Disabling clipboard in isolation profiles
  for tools like Notion or Confluence will cause user frustration and workarounds.
  Create separate, less-restrictive profiles for productivity-tier SaaS and full
  isolation profiles for unknown/risky sites.

## Gotchas

- **WebSockets in isolated sessions** — As of 2026, RBI supports WebSocket connections
  inside isolated pages. However, real-time collaborative features (e.g. Figma live
  cursors) may experience higher latency due to the pixel-streaming relay.
- **File uploads from isolated sessions** — File uploads from the local disk are blocked
  by default (to prevent data exfiltration). Users needing to upload must use a separate
  non-isolated upload path or a specific Allow policy exception.
- **Copy-paste DLP scope** — The `Disable Copy/Paste` setting prevents clipboard
  exchange between the isolated page and the local OS. It does not prevent copy-paste
  *within* the isolated session itself (e.g., pasting from one field to another on the
  same page).
- **Browser extensions do not run in RBI** — Password managers (1Password, Bitwarden)
  will not autofill in isolated sessions. Users must type credentials or use a
  passkey/SSO flow. Communicate this limitation in your rollout.
- **Clientless RBI requires Cloudflare Access** — The `/browser/` URL prefix is gated
  behind Access authentication. Anonymous users cannot reach it.
- **RBI is available on Zero Trust Gateway Business and Enterprise plans** — It is not
  included in the Zero Trust free tier or the standard Gateway plan.

## Verification

```bash
# 1. Navigate to a test phishing domain in a browser enrolled in WARP
#    (check if it opens in isolated mode — the address bar shows a Cloudflare banner)
open https://phishtank.org/phi...   # category: Security Risks → should isolate

# 2. Verify Gateway log entry shows "Isolate" action
# Dashboard → Zero Trust → Gateway → Activity log → filter by action=isolate

# 3. Test clientless URL (without WARP)
open "https://myorg.cloudflareaccess.com/browser/https://example.com"
# Should prompt Access login, then render example.com in isolated browser

# 4. Confirm file download is blocked (if disabled in profile)
# In the isolated browser, try downloading a file → should see block message

# 5. Check audit log via Workers D1
wrangler d1 execute my-app-prod \
  --command "SELECT user_email, url, accessed_at FROM access_log ORDER BY accessed_at DESC LIMIT 10"
```

Expected: Gateway activity log shows `action=isolate` for matched traffic; clientless
URL prompts Access login; file downloads blocked per profile; audit log records entries.

## Related

- `zero-trust-access.md` — Access application configuration
- `zero-trust-device-posture.md` — combining RBI with device posture checks
- `cloudflare-teams-gateway.md` — Gateway HTTP, DNS, and Network policies
- `cloudflare-access-jwt-validation.md` — validating `Cf-Access-Jwt-Assertion` in Workers
- `cloudflare-tunnel-private-service-ingress.md` — routing RBI-accessed internal apps via Tunnel
- `warp-connector-site-to-site-zero-trust.md` — WARP deployment for automatic Gateway enrollment

## Sources

- Cloudflare Remote Browser Isolation: https://developers.cloudflare.com/cloudflare-one/policies/browser-isolation/
- Gateway HTTP Policies (Isolate action): https://developers.cloudflare.com/cloudflare-one/policies/gateway/http-policies/
- Clientless RBI: https://developers.cloudflare.com/cloudflare-one/policies/browser-isolation/setup/clientless-browser-isolation/
- Isolation profiles: https://developers.cloudflare.com/cloudflare-one/policies/browser-isolation/isolation-policies/
- Cloudflare One pricing: https://www.cloudflare.com/plans/zero-trust-services/
