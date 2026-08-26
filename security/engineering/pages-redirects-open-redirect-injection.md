# Open Redirect Injection via Cloudflare Pages _redirects File

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

A Cloudflare Pages site uses a `_redirects` file for URL management. An attacker who can
influence the content of that file — through a compromised CI pipeline, a pull-request that
auto-deploys to a preview URL, or a misconfigured build step that writes dynamic redirects —
can plant open-redirect rules that send legitimate-looking links to attacker-controlled
destinations.

Additionally, engineers unfamiliar with the Pages redirect syntax inadvertently create wildcard
or splat rules that swallow entire path trees and forward them to arbitrary external URLs,
turning the entire domain into a phishing relay.

---

## Context

Cloudflare Pages evaluates `_redirects` at the edge before any Function or origin response.
Rules are matched top-to-bottom; the first match wins. The syntax is:

```
/source   /destination   [status]
```

Splat (`*`) and placeholder (`:name`) expansions in the destination use the captured values
verbatim. When the destination is a fully-qualified URL (starts with `http`), Pages issues
an HTTP 301/302 to that external location.

Risk surface:

| Vector | Description |
|---|---|
| Malicious PR | Preview deployment includes attacker `_redirects` with offsite redirect |
| Build-time generation | Script writes external URL from unvalidated config or env var |
| Supply-chain | Compromised build dependency inserts redirect rule before static copy |
| Wildcard splat abuse | Engineer writes `/* https://partner.com/:splat` to alias a partner domain |

---

## Code sections

### 1. Dangerous wildcard rule — inadvertent phishing relay

```
# DO NOT commit this pattern
/*  https://evil.example.com/:splat  301
```

Any request to `https://yoursite.com/login?next=/dashboard` becomes a redirect to
`https://evil.example.com/login?next=/dashboard`. The attacker distributes
`https://yoursite.com/verify-account?token=abc` in a phishing email; victims trust the
legitimate domain.

### 2. Splat capture injected into external URL

```
# Appears to alias one path to another site — but captures arbitrary user input
/docs/*  https://docs.partner.com/:splat  302
```

Attacker navigates to `/docs/../../../../evil.site/%2Fphish`. After Pages normalises the
path, `:splat` may expand to a path that alters the effective destination. Always validate
that splat values do not begin with `//` or contain `@`.

### 3. Worker middleware to validate _redirects at deploy time

Use a Pages Function or a CI script to parse and gate the `_redirects` file before it ships.

```typescript
// scripts/validate-redirects.ts  (run in CI, not a Worker)
import { readFileSync } from "fs";

const ALLOWED_EXTERNAL_PREFIXES = [
  "https://docs.example.com/",
  "https://status.example.com/",
];

function validateRedirects(filePath: string): void {
  const lines = readFileSync(filePath, "utf-8")
    .split("\n")
    .map((l) => l.trim())
    .filter((l) => l && !l.startsWith("#"));

  const errors: string[] = [];

  for (const line of lines) {
    const parts = line.split(/\s+/);
    if (parts.length < 2) continue;

    const destination = parts[1];

    if (!destination.startsWith("/")) {
      // External redirect — require explicit allow-list
      const allowed = ALLOWED_EXTERNAL_PREFIXES.some((p) =>
        destination.startsWith(p)
      );
      if (!allowed) {
        errors.push(
          `Blocked external redirect: "${line}" — destination not in allow-list`
        );
      }
    }

    // Detect dangerous wildcard-to-external patterns
    const source = parts[0];
    if (
      (source.includes("*") || source.includes(":")) &&
      !destination.startsWith("/")
    ) {
      errors.push(
        `Wildcard splat routing to external URL is prohibited: "${line}"`
      );
    }
  }

  if (errors.length > 0) {
    console.error("_redirects validation failed:\n" + errors.join("\n"));
    process.exit(1);
  }

  console.log(`_redirects OK — ${lines.length} rules validated`);
}

validateRedirects("./public/_redirects");
```

### 4. Pages Function intercepting suspicious redirects at runtime

```typescript
// functions/_middleware.ts
export const onRequest: PagesFunction = async ({ request, next }) => {
  const response = await next();

  // Pages issues 301/302 for _redirects rules
  if (response.status === 301 || response.status === 302) {
    const location = response.headers.get("Location") ?? "";

    // Reject off-origin Location headers not in our allow-list
    const allowed = [
      "https://docs.example.com",
      "https://status.example.com",
    ];

    const isRelative = location.startsWith("/");
    const isAllowed = allowed.some((a) => location.startsWith(a));

    if (!isRelative && !isAllowed) {
      // Log for alerting before returning a safe error
      console.error(`Blocked unexpected external redirect to: ${location}`);
      return new Response("Redirect destination not permitted.", {
        status: 400,
        headers: { "Content-Type": "text/plain" },
      });
    }
  }

  return response;
};
```

### 5. CI GitHub Actions gate

```yaml
# .github/workflows/validate-redirects.yml
name: Validate _redirects

on:
  pull_request:
    paths:
      - "public/_redirects"
      - "scripts/validate-redirects.ts"

jobs:
  validate:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: "22"
      - run: npx ts-node scripts/validate-redirects.ts
```

### 6. Immutable redirect audit via Workers Analytics Engine

```typescript
// Log every redirect trip to Analytics Engine for post-hoc audit
// functions/audit-redirects.ts
import type { AnalyticsEngineDataset } from "@cloudflare/workers-types";

interface Env {
  REDIRECT_AUDIT: AnalyticsEngineDataset;
}

export const onRequest: PagesFunction<Env> = async (ctx) => {
  const response = await ctx.next();

  if (response.status === 301 || response.status === 302) {
    ctx.env.REDIRECT_AUDIT.writeDataPoint({
      blobs: [
        ctx.request.url,
        response.headers.get("Location") ?? "",
        ctx.request.headers.get("CF-Connecting-IP") ?? "",
      ],
      indexes: [String(response.status)],
    });
  }

  return response;
};
```

---

## Anti-patterns

- Committing `_redirects` rules that contain external URLs without a PR review requirement on that specific file.
- Using splat captures (`*` → `:splat`) in external redirect destinations without sanitising the capture.
- Generating `_redirects` dynamically in a build script from environment variables or API responses without escaping or validation.
- Placing a catch-all `/* /index.html 200` (SPA fallback) after an external wildcard rule — the catch-all is never reached, and the wildcard swallows everything.
- Trusting preview deployments to have the same `_redirects` policy as production; preview branches inherit the file from the branch, which attackers control in fork PRs.

---

## Gotchas

- Cloudflare Pages preview deployments get their own `*.pages.dev` subdomain but run the **same** `_redirects` from the PR branch. A malicious contributor submits a PR only to test their phishing link on the preview URL, then closes it — no production impact, but real credential phishing surface.
- `_redirects` is evaluated **before** Pages Functions. A middleware function cannot intercept a redirect that Pages has already decided to issue unless you use the Function pattern above that wraps `next()`.
- The Pages redirect limit is 2,000 rules. A supply-chain attack may pad the file to push a safety rule past the limit, causing it to be ignored.
- Status code `200` rewrites (not redirects) that point to external URLs are blocked by Pages — only `3xx` status codes may use external destinations. Verify this behaviour with each Pages runtime version update.
- HTTP `301` responses are cached by browsers indefinitely. A leaked phishing redirect that shipped even briefly may remain active in user browsers long after the rule is removed.

---

## Verification

```bash
# 1. Run the validator against the repo's _redirects file
npx ts-node scripts/validate-redirects.ts

# 2. Deploy to preview and manually test
wrangler pages deploy ./public --project-name=orchords-staging

# 3. Probe for unexpected external redirect
curl -sI "https://orchords-staging.pages.dev/docs/test" \
  | grep -i location

# 4. Confirm middleware blocks unlisted destinations
curl -sI "https://orchords-staging.pages.dev/verify?token=x" \
  | grep -E "^HTTP|^Location"
# expect: 400, no Location header pointing off-domain

# 5. Check Analytics Engine for redirect log entries
wrangler analytics-engine query REDIRECT_AUDIT \
  --query "SELECT blob2, count() FROM REDIRECT_AUDIT GROUP BY blob2"
```

---

## Related

- `open-redirect-prevention.md`
- `cloudflare-pages-headers-security-file.md`
- `pages-functions-auth-middleware-session.md`
- `workers-analytics-engine-security-telemetry.md`
- `subdomain-takeover-prevention.md`

---

## Sources

- Cloudflare Pages _redirects documentation — https://developers.cloudflare.com/pages/configuration/redirects/
- OWASP: Unvalidated Redirects and Forwards — https://owasp.org/www-project-web-security-testing-guide/v42/4-Web_Application_Security_Testing/11-Client-Side_Testing/04-Testing_for_Client_Side_URL_Redirect
- CWE-601: URL Redirection to Untrusted Site — https://cwe.mitre.org/data/definitions/601.html
- Cloudflare Pages Functions middleware — https://developers.cloudflare.com/pages/functions/middleware/
