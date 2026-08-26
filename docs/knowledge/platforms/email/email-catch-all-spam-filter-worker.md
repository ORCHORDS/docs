# Cloudflare Email Routing Catch-All with Worker Spam Filtering

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

You own `example.com` and want to receive email at any address on that domain without pre-defining every address in the Cloudflare Email Routing dashboard. At the same time you need to:

- Reject obvious spam before it reaches your processing logic or inbox
- Route sub-addresses and local-part prefixes to different downstream addresses
- Apply a dynamic routing table that can be updated without redeployment
- Log all rejected messages to D1 for audit and pattern analysis

---

## Context

Cloudflare Email Routing evaluates rules top-to-bottom. Specific address rules are evaluated first; the catch-all fires only for addresses that match nothing above it. A Worker set as the catch-all therefore receives the long tail of every unknown address on the domain.

Routing table entries are stored in Workers KV. A separate admin HTTP Worker lets you add or remove entries without touching the email Worker's code.

---

## wrangler.toml Configuration

```toml
name = "catch-all-filter"
main = "src/index.ts"
compatibility_date = "2024-09-23"

[[email]]
type = "email"
name = "EMAIL"

[[kv_namespaces]]
binding = "ROUTING_KV"
id = "<kv-namespace-id>"

[[d1_databases]]
binding = "AUDIT_DB"
database_name = "catch-all-audit"
database_id = "<d1-database-id>"

[vars]
DEFAULT_FORWARD = "fallback@team.example.com"
SPAM_THRESHOLD = "7"
```

---

## D1 Audit Schema

```sql
CREATE TABLE IF NOT EXISTS rejections (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  from_addr   TEXT NOT NULL,
  to_addr     TEXT NOT NULL,
  subject     TEXT,
  score       INTEGER NOT NULL,
  factors     TEXT NOT NULL,   -- JSON object
  rejected_at TEXT NOT NULL
);

CREATE INDEX idx_rej_from ON rejections(from_addr);
CREATE INDEX idx_rej_date ON rejections(rejected_at);
```

---

## Worker Entry Point: Address Routing

```typescript
import type { EmailMessage } from "cloudflare:email";

interface Env {
  ROUTING_KV: KVNamespace;
  AUDIT_DB: D1Database;
  DEFAULT_FORWARD: string;
  SPAM_THRESHOLD: string;
}

export default {
  async email(message: EmailMessage, env: Env, ctx: ExecutionContext) {
    const localPart = message.to.split("@")[0].toLowerCase();
    const basePart = localPart.split("+")[0];
    const extension = localPart.includes("+") ? localPart.slice(basePart.length + 1) : "";

    // 1. Explicit route by full local-part
    const exactRoute = await env.ROUTING_KV.get(`route:${localPart}`);
    if (exactRoute) {
      await message.forward(exactRoute);
      return;
    }

    // 2. Base-local-part route (handles sub-addresses)
    const baseRoute = await env.ROUTING_KV.get(`route:${basePart}`);
    if (baseRoute) {
      const extraHeaders = new Headers();
      if (extension) extraHeaders.set("X-Address-Extension", extension);
      await message.forward(baseRoute, extraHeaders);
      return;
    }

    // 3. No explicit route — apply spam filter before falling back to default
    await filterAndForward(message, env, ctx);
  },
};
```

---

## Spam Score Evaluation

```typescript
interface SpamFactors {
  authFail: boolean;
  suspectSubject: boolean;
  missingDate: boolean;
  rateLimited: boolean;
}

async function evaluateSpam(
  message: EmailMessage,
  env: Env
): Promise<{ score: number; factors: SpamFactors }> {
  const authResults = message.headers.get("Authentication-Results") ?? "";
  const subject = message.headers.get("Subject") ?? "";
  const senderDomain = message.from.split("@")[1]?.toLowerCase() ?? "";

  const authFail =
    /dmarc=fail/i.test(authResults) ||
    (/spf=fail/i.test(authResults) && /dkim=fail/i.test(authResults));

  const suspectSubject =
    /\b(winner|prize|free money|click here|act now|limited offer|congratulations)\b/i.test(subject) ||
    /!!{2,}/.test(subject);

  const missingDate = !message.headers.get("Date");

  const rlKey = `rl:${senderDomain}`;
  const prevStr = await env.ROUTING_KV.get(rlKey);
  const prev = prevStr ? parseInt(prevStr, 10) : 0;
  await env.ROUTING_KV.put(rlKey, String(prev + 1), { expirationTtl: 3600 });
  const rateLimited = prev >= 20;

  const score =
    (authFail ? 5 : 0) +
    (suspectSubject ? 3 : 0) +
    (missingDate ? 2 : 0) +
    (rateLimited ? 4 : 0);

  return { score, factors: { authFail, suspectSubject, missingDate, rateLimited } };
}
```

---

## Forward or Reject and Log

```typescript
async function filterAndForward(
  message: EmailMessage,
  env: Env,
  ctx: ExecutionContext
): Promise<void> {
  const threshold = parseInt(env.SPAM_THRESHOLD, 10);
  const { score, factors } = await evaluateSpam(message, env);

  if (score >= threshold) {
    ctx.waitUntil(logRejection(message, score, factors, env));
    message.setReject(`5.7.1 Message rejected (score ${score})`);
    return;
  }

  await message.forward(env.DEFAULT_FORWARD);
}

async function logRejection(
  message: EmailMessage,
  score: number,
  factors: SpamFactors,
  env: Env
): Promise<void> {
  await env.AUDIT_DB.prepare(
    `INSERT INTO rejections (from_addr, to_addr, subject, score, factors, rejected_at)
     VALUES (?, ?, ?, ?, ?, ?)`
  )
    .bind(
      message.from,
      message.to,
      message.headers.get("Subject") ?? "(no subject)",
      score,
      JSON.stringify(factors),
      new Date().toISOString()
    )
    .run();
}
```

---

## Admin Routing Table API

```typescript
export const adminFetch = {
  async fetch(request: Request, env: Env): Promise<Response> {
    if (request.method !== "POST") {
      return new Response("Method Not Allowed", { status: 405 });
    }

    const { action, localPart, destination } = await request.json<{
      action: "set" | "delete" | "list";
      localPart?: string;
      destination?: string;
    }>();

    if (action === "set" && localPart && destination) {
      await env.ROUTING_KV.put(`route:${localPart.toLowerCase()}`, destination);
      return Response.json({ ok: true, key: `route:${localPart}`, destination });
    }

    if (action === "delete" && localPart) {
      await env.ROUTING_KV.delete(`route:${localPart.toLowerCase()}`);
      return Response.json({ ok: true });
    }

    if (action === "list") {
      const listed = await env.ROUTING_KV.list({ prefix: "route:" });
      return Response.json({ keys: listed.keys.map((k) => k.name) });
    }

    return Response.json({ error: "Invalid action" }, { status: 400 });
  },
};
```

---

## Anti-patterns

- **Setting the catch-all to forward directly to an inbox without a Worker** — every spam message sent to any address on the domain reaches the destination unchanged.
- **Hard-coding the routing table inside the Worker source** — requires a full deployment to add or change a route. Use KV so routes can be updated via API.
- **Scoring the body for messages you intend to forward** — reading `message.raw` consumes the stream; calling `message.forward()` afterwards throws.
- **Using `message.setReject()` for any unrecognised address** — always fall back to a default forward rather than rejecting unknown local-parts.

---

## Gotchas

- `message.forward()` and `message.setReject()` are mutually exclusive per invocation. Calling either a second time in the same handler throws a runtime error.
- Sub-addresses (`ticket+123@example.com`) arrive at the catch-all only if there is no matching specific routing rule in the Email Routing dashboard for that full address.
- Rate-limit counters in KV are not atomic. Two simultaneous messages from the same sender domain may both read `0` and increment independently. For strict enforcement replace with a Durable Object counter.

---

## Verification

```bash
# Populate routing table
curl -X POST https://catch-all-admin.example.com/admin \
  -H "Content-Type: application/json" \
  -d '{"action":"set","localPart":"support","destination":"help@myteam.example.com"}'

# Test spam rejection
swaks --from spammer@nodns-example.xyz --to anyone@example.com \
  --header "Subject: WINNER click here for FREE MONEY!!!" --server mx.example.com

# Review rejection log
wrangler d1 execute catch-all-audit \
  --command "SELECT from_addr, score, factors, rejected_at FROM rejections ORDER BY id DESC LIMIT 20"
```

---

## Related

- `cloudflare-email-routing-workers.md`
- `workers-inbound-email-spam-filtering-custom-rules.md`
- `email-alias-routing-kv-workers.md`
- `email-catch-all-patterns.md`

---

## Sources

- Cloudflare Email Routing — Catch-all — https://developers.cloudflare.com/email-routing/setup/email-routing-addresses/#catch-all-address
- Cloudflare Email Routing Workers — https://developers.cloudflare.com/email-routing/email-workers/
- Cloudflare Workers KV — https://developers.cloudflare.com/kv/
- Cloudflare D1 — https://developers.cloudflare.com/d1/
