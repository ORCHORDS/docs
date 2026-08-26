# HSTS Preload List Submission and Management in Cloudflare Workers

- **Date:** 2026-08-23
- **Author:** example.com
- **Status:** production

## Symptom / Use-case

Your domain serves HTTPS but browsers still allow a first-visit HTTP connection before the `Strict-Transport-Security` header is seen. This window is exploitable by SSL-strip attacks on untrusted networks. You want to join the HSTS preload list so browsers hard-code your domain as HTTPS-only before any connection is ever made, and you need to manage the header requirements from Cloudflare Workers without breaking subdomains you haven't yet migrated.

## Context

HSTS preloading (hstspreload.org, shipped in browsers via Chromium's transport_security_state_static.json) requires `Strict-Transport-Security: max-age=31536000; includeSubDomains; preload` on the root HTTPS response. Cloudflare Workers let you inject or rewrite this header on every response, audit compliance across environments, and gracefully stage the rollout by environment. Removal from the preload list is slow (months); understand the commitment before enabling.

## 1. Baseline HSTS Header for Preload Eligibility

```typescript
// src/hsts.ts
export interface HSTSConfig {
  maxAge: number;          // minimum 31536000 (1 year) for preload
  includeSubDomains: boolean; // must be true for preload
  preload: boolean;        // must be true to signal intent
}

export function buildHSTSHeader(cfg: HSTSConfig): string {
  const parts = [`max-age=${cfg.maxAge}`];
  if (cfg.includeSubDomains) parts.push("includeSubDomains");
  if (cfg.preload) parts.push("preload");
  return parts.join("; ");
}

// Production-ready, preload-eligible
export const PRELOAD_HSTS = buildHSTSHeader({
  maxAge: 31_536_000,
  includeSubDomains: true,
  preload: true,
});

// Staging: short max-age, no preload, safe for subdomain rollout
export const STAGING_HSTS = buildHSTSHeader({
  maxAge: 300,
  includeSubDomains: false,
  preload: false,
});
```

## 2. Attaching HSTS in the Worker

```typescript
// src/index.ts
import { PRELOAD_HSTS, STAGING_HSTS } from "./hsts";

interface Env {
  ENVIRONMENT: string; // "production" | "staging"
  HSTS_OVERRIDE?: string; // custom value from wrangler secret
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    // Redirect bare HTTP to HTTPS before HSTS header matters
    const url = new URL(request.url);
    if (url.protocol === "http:") {
      url.protocol = "https:";
      return Response.redirect(url.toString(), 301);
    }

    const response = await fetch(request);
    const mutable = new Response(response.body, response);

    const hstsValue =
      env.HSTS_OVERRIDE ??
      (env.ENVIRONMENT === "production" ? PRELOAD_HSTS : STAGING_HSTS);

    // Only set on HTTPS; never overwrite a downstream preload directive
    mutable.headers.set("Strict-Transport-Security", hstsValue);
    return mutable;
  },
};
```

## 3. Auditing All Routes for HSTS Compliance

```typescript
// src/audit.ts — call from a Cron Trigger before submitting to hstspreload.org
interface Env {
  AUDIT_DOMAINS: string; // comma-separated domains to audit
  DB: D1Database;
}

async function auditDomain(domain: string): Promise<{
  domain: string;
  eligible: boolean;
  reason: string | null;
  hsts: string | null;
}> {
  const url = `https://${domain}/`;
  let resp: Response;
  try {
    resp = await fetch(url, { redirect: "manual" });
  } catch (e) {
    return { domain, eligible: false, reason: String(e), hsts: null };
  }

  const hsts = resp.headers.get("strict-transport-security") ?? "";
  const maxAgeMatch = hsts.match(/max-age=(\d+)/i);
  const maxAge = maxAgeMatch ? parseInt(maxAgeMatch[1], 10) : 0;
  const hasIncludeSubDomains = /includeSubDomains/i.test(hsts);
  const hasPreload = /preload/i.test(hsts);

  if (maxAge < 31_536_000) {
    return { domain, eligible: false, reason: `max-age too short: ${maxAge}`, hsts };
  }
  if (!hasIncludeSubDomains) {
    return { domain, eligible: false, reason: "missing includeSubDomains", hsts };
  }
  if (!hasPreload) {
    return { domain, eligible: false, reason: "missing preload directive", hsts };
  }

  return { domain, eligible: true, reason: null, hsts };
}

export async function runAudit(env: Env): Promise<void> {
  const domains = env.AUDIT_DOMAINS.split(",").map((d) => d.trim());
  const results = await Promise.all(domains.map(auditDomain));

  const stmt = env.DB.prepare(
    `INSERT INTO hsts_audit (domain, eligible, reason, hsts_value, checked_at)
     VALUES (?, ?, ?, ?, ?)`
  );
  await env.DB.batch(
    results.map((r) =>
      stmt.bind(r.domain, r.eligible ? 1 : 0, r.reason, r.hsts, new Date().toISOString())
    )
  );
}
```

## 4. Cron Trigger for Ongoing Compliance

```typescript
// src/index.ts (extended)
import { runAudit } from "./audit";

export default {
  async fetch(request: Request, env: Env): Promise<Response> { /* ... */ },

  async scheduled(_event: ScheduledEvent, env: Env): Promise<void> {
    // Runs daily via wrangler.toml: [triggers] crons = ["0 8 * * *"]
    await runAudit(env);
  },
};
```

```toml
# wrangler.toml
[triggers]
crons = ["0 8 * * *"]

[[d1_databases]]
binding = "DB"
database_name = "security-audit"
database_id = "YOUR_D1_ID"
```

## 5. Staged Rollout: Ramp max-age Before Preload

```typescript
// Rollout phases — change HSTS_PHASE env var per deployment
const PHASES: Record<string, string> = {
  "1": "max-age=300",                                           // 5 minutes — smoke test
  "2": "max-age=86400",                                        // 1 day
  "3": "max-age=604800",                                       // 1 week
  "4": "max-age=2592000",                                      // 30 days
  "5": "max-age=31536000; includeSubDomains",                  // 1 year
  "6": "max-age=31536000; includeSubDomains; preload",         // preload-eligible
};

const phase = PHASES[env.HSTS_PHASE ?? "1"] ?? PHASES["1"];
mutable.headers.set("Strict-Transport-Security", phase);
```

## 6. Graceful Removal Preparation

```typescript
// When you need to remove from preload list: start with max-age ramp-down
// DO NOT remove includeSubDomains before you redirect all subdomains to HTTPS
// Minimum removal process: submit removal at hstspreload.org, then wait ~3–12 months
// Meanwhile keep at least: max-age=31536000; includeSubDomains (no preload token)
const REMOVAL_HSTS = "max-age=31536000; includeSubDomains";
// Keep serving this for 1+ year after removal is confirmed
```

## Anti-patterns

- **Adding `preload` before migrating all subdomains.** `includeSubDomains` + `preload` means every subdomain must serve HTTPS—including internal and staging subdomains.
- **Setting `max-age=0` to "disable" HSTS.** This tries to clear cached HSTS but browsers on the preload list ignore it; only removing from the list has effect.
- **Omitting HTTP→HTTPS redirect before testing.** The HSTS header is ignored over plain HTTP; the redirect must be in place first.
- **Setting HSTS on API subdomains that serve mixed-content.** Confirm every resource the subdomain loads is HTTPS before setting `includeSubDomains`.
- **Not storing your preload submission timestamp.** If something breaks, you need to know exactly when preload propagated to users.

## Gotchas

- Chrome and Firefox ship preload list updates approximately every 6–8 weeks; a new entry won't protect all users immediately.
- Safari uses its own preload list derived from Chromium's but updates less frequently.
- `max-age` resets on every HTTPS visit; users who have never visited see the preload header from the browser binary, not your server.
- Cloudflare itself offers "Always Use HTTPS" and "HSTS" settings at the dashboard level—if both are active, the Worker header and the Cloudflare setting may conflict; disable the dashboard setting when managing HSTS in a Worker.
- The `preload` token has no effect on browsers by itself—it is a signal to operators submitting to hstspreload.org; the browser only enforces it after the domain appears in the baked-in list.

## Verification

```bash
# Check HSTS eligibility programmatically
curl -sI https://www.example.com | grep -i strict-transport

# Verify via hstspreload.org API
curl "https://hstspreload.org/api/v2/status?domain=example.com"

# Query audit history in D1
wrangler d1 execute security-audit --command \
  "SELECT domain, eligible, reason, checked_at FROM hsts_audit ORDER BY checked_at DESC LIMIT 10;"
```

## Related

- `http-security-headers-hsts.md`
- `tls-certificate-lifecycle-management.md`
- `security-headers-comprehensive.md`
- `clickjacking-defense.md`
- `mobile-certificate-pinning-vs-cloudflare-tls.md`

## Sources

- HSTS Preload List — https://hstspreload.org/
- RFC 6797 HTTP Strict Transport Security — https://datatracker.ietf.org/doc/html/rfc6797
- Chromium transport_security_state_static — https://chromium.googlesource.com/chromium/src/+/refs/heads/main/net/http/transport_security_state_static.json
- Cloudflare HSTS documentation — https://developers.cloudflare.com/ssl/edge-certificates/additional-options/http-strict-transport-security/
- Cloudflare Workers Cron Triggers — https://developers.cloudflare.com/workers/configuration/cron-triggers/
