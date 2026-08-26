# Email Alias Routing with KV and Email Workers

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

You operate multiple email aliases (`info@`, `support@`, `billing@`) that should forward to different internal addresses. You also need a wildcard catch-all for unknown aliases, and unknown addresses that match no rule should be rejected with a proper SMTP error. All routing rules must be editable without redeploying the Worker.

## Context

A KV namespace `ALIAS_MAP` stores routing entries keyed as `alias:<address>`. On each inbound message the Email Worker reads the recipient alias from KV, calls `message.forward()` to the resolved real address, or falls back to a wildcard entry keyed as `alias:*@<domain>`. Unknown aliases are rejected with SMTP code `5.1.1`. An admin API Worker provides CRUD endpoints for the KV alias map, protected by a bearer token.

Requirements:
- Email Worker with `email` event handler
- KV namespace bound as `ALIAS_MAP`
- Admin API Worker with `fetch` handler
- `ADMIN_TOKEN` secret

## KV Key Convention

```
alias:info@yourdomain.com      -> "real@internal.com"
alias:support@yourdomain.com   -> "helpdesk@internal.com"
alias:*@yourdomain.com         -> "catchall@internal.com"   (wildcard)
```

## Email Worker — Alias Resolution and Forwarding

```typescript
import type { EmailMessage } from 'cloudflare:email';

export interface Env {
  ALIAS_MAP: KVNamespace;
}

export default {
  async email(message: EmailMessage, env: Env): Promise<void> {
    const toAddr = message.to.toLowerCase().trim();
    const domain = toAddr.split('@')[1] ?? '';

    // 1. Exact alias lookup
    let destination = await env.ALIAS_MAP.get(`alias:${toAddr}`);

    // 2. Wildcard fallback for the domain
    if (!destination) {
      destination = await env.ALIAS_MAP.get(`alias:*@${domain}`);
    }

    if (!destination) {
      // 3. Reject unknown aliases with SMTP 5.1.1
      message.setReject('5.1.1 The email account that you tried to reach does not exist.');
      console.warn(`[alias-routing] No route found for ${toAddr} — rejected`);
      return;
    }

    // Forward to the resolved real address
    await message.forward(destination);
    console.info(`[alias-routing] Forwarded ${toAddr} -> ${destination}`);
  },
};
```

## Admin API Worker — Alias CRUD

```typescript
// admin/src/index.ts
export interface AdminEnv {
  ALIAS_MAP: KVNamespace;
  ADMIN_TOKEN: string;
}

export default {
  async fetch(request: Request, env: AdminEnv): Promise<Response> {
    // Verify bearer token
    const auth = request.headers.get('Authorization') ?? '';
    if (auth !== `Bearer ${env.ADMIN_TOKEN}`) {
      return new Response('Unauthorized', { status: 401 });
    }

    const url = new URL(request.url);
    const alias = url.searchParams.get('alias'); // e.g. info@yourdomain.com or *@yourdomain.com

    if (!alias) return new Response('Missing alias param', { status: 400 });

    const kvKey = `alias:${alias.toLowerCase()}`;

    switch (request.method) {
      case 'GET': {
        const value = await env.ALIAS_MAP.get(kvKey);
        if (!value) return new Response('Not Found', { status: 404 });
        return Response.json({ alias, destination: value });
      }

      case 'PUT': {
        const { destination } = await request.json<{ destination: string }>();
        if (!destination) return new Response('Missing destination', { status: 400 });
        await env.ALIAS_MAP.put(kvKey, destination);
        return Response.json({ alias, destination, status: 'created' });
      }

      case 'DELETE': {
        await env.ALIAS_MAP.delete(kvKey);
        return new Response('Deleted', { status: 200 });
      }

      default:
        return new Response('Method Not Allowed', { status: 405 });
    }
  },
};
```

## wrangler.toml Configuration

```toml
name = "alias-routing-worker"
main = "src/index.ts"
compatibility_date = "2024-09-23"

[[kv_namespaces]]
binding = "ALIAS_MAP"
id = "<your-kv-id>"

[vars]
# ADMIN_TOKEN is set as a secret: wrangler secret put ADMIN_TOKEN
```

## Seeding Initial Alias Map via CLI

```bash
# Add exact aliases
wrangler kv key put --namespace-id <your-kv-id> 'alias:info@yourdomain.com' 'real@internal.com'
wrangler kv key put --namespace-id <your-kv-id> 'alias:support@yourdomain.com' 'helpdesk@internal.com'

# Add wildcard catch-all
wrangler kv key put --namespace-id <your-kv-id> 'alias:*@yourdomain.com' 'catchall@internal.com'

# List all alias entries
wrangler kv key list --namespace-id <your-kv-id> --prefix 'alias:'
```

## Managing Aliases via the Admin API

```bash
# Create or update an alias
curl -X PUT 'https://admin.yourdomain.com/?alias=billing@yourdomain.com' \
  -H 'Authorization: Bearer <token>' \
  -H 'Content-Type: application/json' \
  -d '{"destination":"finance@internal.com"}'

# Read an alias
curl 'https://admin.yourdomain.com/?alias=billing@yourdomain.com' \
  -H 'Authorization: Bearer <token>'

# Delete an alias
curl -X DELETE 'https://admin.yourdomain.com/?alias=billing@yourdomain.com' \
  -H 'Authorization: Bearer <token>'
```

## Anti-patterns

- Do not hardcode alias mappings in Worker source code; that requires a full redeploy on every routing change.
- Do not use a single global catch-all without logging; you lose visibility into which unknown aliases are being contacted.
- Do not skip normalizing `message.to` to lowercase before KV lookup; addresses are case-insensitive per RFC 5321 local-part conventions.
- Do not expose the admin API without authentication; the ALIAS_MAP controls all inbound routing.

## Gotchas

- KV reads are eventually consistent; a newly added alias may not be visible on all edge nodes for up to 60 seconds.
- `message.setReject()` must be the final action; you cannot call `message.forward()` after a rejection.
- Wildcard matching is implemented manually in the Worker; KV does not support glob key lookups natively.
- The `ADMIN_TOKEN` must be stored as a Worker secret (`wrangler secret put`), not in `[vars]` in wrangler.toml.

## Verification

```bash
# Confirm alias resolution via wrangler tail during a test send
wrangler tail alias-routing-worker --format pretty

# List all KV alias entries
wrangler kv key list --namespace-id <your-kv-id> --prefix 'alias:'

# Test rejection by sending to an unmapped address and checking SMTP bounce
# The bounce should include: "5.1.1 The email account that you tried to reach does not exist."
```

## Related

- `email-forwarding-loop-detection-d1-workers.md`
- `email-auto-responder-out-of-office-d1-workers.md`
- [Cloudflare Email Workers docs](https://developers.cloudflare.com/email-routing/email-workers/)
- [Cloudflare KV docs](https://developers.cloudflare.com/workers/runtime-apis/kv/)

## Sources

- https://developers.cloudflare.com/email-routing/email-workers/
- https://developers.cloudflare.com/workers/runtime-apis/kv/
- https://www.rfc-editor.org/rfc/rfc5321
