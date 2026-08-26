# Email Forwarding Alias Management with Cloudflare Workers and D1

Date: 2026-08-23 / Author: example.com / Status: production

## Symptom / Use-case

A product offers disposable or catch-all email aliases: users create `anything@customer.example.com`, set a destination, enable/disable without DNS changes, and audit delivery history — all via API. Cloudflare Email Routing handles the MX layer; Workers serve the CRUD API and mutate routing rules programmatically; D1 is the source of truth for alias state, owner mapping, and history.

---

## Context

Cloudflare Email Routing exposes a REST API to manage address rules. A Worker acts as the orchestration layer: it validates ownership, writes to D1, then calls the Cloudflare API to create or delete routing rules. The inbound email path goes: MX → Cloudflare Email Routing → Email Worker → forward to verified destination.

Catch-all aliases (wildcard rules) differ from explicit address rules: a single wildcard routing rule covers all unclaimed addresses, while explicit rules take priority. The Worker routes based on D1 lookup before falling back to catch-all logic.

---

## D1 Schema

```sql
CREATE TABLE aliases (
  id              TEXT PRIMARY KEY,           -- ulid
  local_part      TEXT NOT NULL,              -- e.g. "support" in support@example.com
  domain          TEXT NOT NULL,
  owner_id        TEXT NOT NULL,
  destination     TEXT NOT NULL,
  status          TEXT NOT NULL DEFAULT 'active'
                  CHECK(status IN ('active','disabled','deleted')),
  cf_rule_tag     TEXT,                       -- Cloudflare routing rule tag
  created_at      INTEGER NOT NULL,
  updated_at      INTEGER NOT NULL,
  UNIQUE(local_part, domain)
);

CREATE INDEX idx_alias_owner  ON aliases(owner_id, status);
CREATE INDEX idx_alias_domain ON aliases(domain, local_part);

CREATE TABLE alias_events (
  id          TEXT PRIMARY KEY,
  alias_id    TEXT NOT NULL,
  event_type  TEXT NOT NULL,   -- 'created'|'disabled'|'enabled'|'deleted'|'received'
  detail      TEXT,
  created_at  INTEGER NOT NULL,
  FOREIGN KEY (alias_id) REFERENCES aliases(id)
);
```

---

## CRUD API Worker

```typescript
// src/api/aliases.ts
import { Env } from '../types';
import { ulid } from 'ulid';

const CF_API = 'https://api.cloudflare.com/client/v4';

// POST /aliases — create a new forwarding alias
export async function createAlias(
  request: Request,
  env: Env,
  ownerId: string
): Promise<Response> {
  const { localPart, domain, destination } = await request.json<{
    localPart: string;
    domain: string;
    destination: string;
  }>();

  if (!/^[a-z0-9._+-]+$/.test(localPart)) {
    return new Response('Invalid local part', { status: 400 });
  }

  const id = ulid();
  const now = Date.now();

  // Create routing rule in Cloudflare
  const cfRule = await createCfRoutingRule(env, `${localPart}@${domain}`, destination);
  if (!cfRule.success) {
    return new Response('Failed to create routing rule', { status: 502 });
  }

  await env.DB.batch([
    env.DB.prepare(`
      INSERT INTO aliases
        (id, local_part, domain, owner_id, destination, status, cf_rule_tag, created_at, updated_at)
      VALUES (?, ?, ?, ?, ?, 'active', ?, ?, ?)
    `).bind(id, localPart, domain, ownerId, destination, cfRule.result.tag, now, now),

    env.DB.prepare(`
      INSERT INTO alias_events (id, alias_id, event_type, detail, created_at)
      VALUES (?, ?, 'created', ?, ?)
    `).bind(ulid(), id, JSON.stringify({ destination }), now),
  ]);

  return Response.json({ id, localPart, domain, destination, status: 'active' }, { status: 201 });
}

// PATCH /aliases/:id — enable or disable
export async function toggleAlias(
  aliasId: string,
  status: 'active' | 'disabled',
  env: Env,
  ownerId: string
): Promise<Response> {
  const alias = await env.DB.prepare(`
    SELECT * FROM aliases WHERE id = ? AND owner_id = ?
  `).bind(aliasId, ownerId).first<{
    cf_rule_tag: string; status: string; local_part: string; domain: string; destination: string;
  }>();

  if (!alias) return new Response('Not found', { status: 404 });
  if (alias.status === 'deleted') return new Response('Cannot modify deleted alias', { status: 410 });

  const now = Date.now();

  if (status === 'disabled' && alias.cf_rule_tag) {
    await deleteCfRoutingRule(env, alias.cf_rule_tag);
  } else if (status === 'active') {
    const cfRule = await createCfRoutingRule(
      env,
      `${alias.local_part}@${alias.domain}`,
      alias.destination
    );
    if (!cfRule.success) return new Response('Failed to re-enable routing rule', { status: 502 });

    await env.DB.prepare(`
      UPDATE aliases SET cf_rule_tag = ?, updated_at = ? WHERE id = ?
    `).bind(cfRule.result.tag, now, aliasId).run();
  }

  await env.DB.batch([
    env.DB.prepare(`
      UPDATE aliases SET status = ?, updated_at = ? WHERE id = ?
    `).bind(status, now, aliasId),
    env.DB.prepare(`
      INSERT INTO alias_events (id, alias_id, event_type, created_at) VALUES (?, ?, ?, ?)
    `).bind(ulid(), aliasId, status === 'active' ? 'enabled' : 'disabled', now),
  ]);

  return Response.json({ id: aliasId, status });
}

// DELETE /aliases/:id — hard delete
export async function deleteAlias(
  aliasId: string,
  env: Env,
  ownerId: string
): Promise<Response> {
  const alias = await env.DB.prepare(`
    SELECT cf_rule_tag FROM aliases WHERE id = ? AND owner_id = ? AND status != 'deleted'
  `).bind(aliasId, ownerId).first<{ cf_rule_tag: string }>();

  if (!alias) return new Response('Not found', { status: 404 });

  if (alias.cf_rule_tag) {
    await deleteCfRoutingRule(env, alias.cf_rule_tag);
  }

  const now = Date.now();
  await env.DB.batch([
    env.DB.prepare(`
      UPDATE aliases SET status = 'deleted', cf_rule_tag = NULL, updated_at = ? WHERE id = ?
    `).bind(now, aliasId),
    env.DB.prepare(`
      INSERT INTO alias_events (id, alias_id, event_type, created_at) VALUES (?, ?, 'deleted', ?)
    `).bind(ulid(), aliasId, now),
  ]);

  return new Response(null, { status: 204 });
}
```

---

## Cloudflare Routing Rule Helpers

```typescript
// src/cf-routing.ts
interface CfRoutingResult {
  success: boolean;
  result: { tag: string };
}

export async function createCfRoutingRule(
  env: Env,
  address: string,
  destination: string
): Promise<CfRoutingResult> {
  const res = await fetch(
    `${CF_API}/zones/${env.CF_ZONE_ID}/email/routing/rules`,
    {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${env.CF_API_TOKEN}`,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        name: `alias-${address}`,
        enabled: true,
        matchers: [{ type: 'literal', field: 'to', value: address }],
        actions: [{ type: 'forward', value: [destination] }],
        priority: 10,
      }),
    }
  );
  return res.json<CfRoutingResult>();
}

export async function deleteCfRoutingRule(
  env: Env,
  ruleTag: string
): Promise<void> {
  await fetch(
    `${CF_API}/zones/${env.CF_ZONE_ID}/email/routing/rules/${ruleTag}`,
    {
      method: 'DELETE',
      headers: { 'Authorization': `Bearer ${env.CF_API_TOKEN}` },
    }
  );
}
```

---

## Inbound Worker: Logging Received Emails

```typescript
// src/email-worker.ts — bound to Cloudflare Email Worker
import type { EmailMessage, ForwardableEmailMessage } from 'cloudflare:email';
import { ulid } from 'ulid';

export default {
  async email(message: ForwardableEmailMessage, env: Env): Promise<void> {
    const to = message.to.toLowerCase();
    const [localPart, domain] = to.split('@');

    const alias = await env.DB.prepare(`
      SELECT id, destination, status FROM aliases
      WHERE local_part = ? AND domain = ? AND status = 'active'
    `).bind(localPart, domain).first<{ id: string; destination: string; status: string }>();

    if (!alias) {
      // No active alias found — reject or drop
      message.setReject('No such alias');
      return;
    }

    // Log the received event
    await env.DB.prepare(`
      INSERT INTO alias_events (id, alias_id, event_type, detail, created_at)
      VALUES (?, ?, 'received', ?, ?)
    `).bind(
      ulid(),
      alias.id,
      JSON.stringify({ from: message.from, subject: message.headers.get('subject') }),
      Date.now()
    ).run();

    await message.forward(alias.destination);
  },
};
```

---

## GET: Alias List with Activity Stats

```typescript
export async function listAliases(
  env: Env,
  ownerId: string,
  page = 1,
  pageSize = 20
): Promise<Response> {
  const offset = (page - 1) * pageSize;

  const rows = await env.DB.prepare(`
    SELECT
      a.id, a.local_part, a.domain, a.destination, a.status, a.created_at,
      COUNT(ae.id) FILTER (WHERE ae.event_type = 'received') AS received_count
    FROM aliases a
    LEFT JOIN alias_events ae ON ae.alias_id = a.id
    WHERE a.owner_id = ? AND a.status != 'deleted'
    GROUP BY a.id
    ORDER BY a.created_at DESC
    LIMIT ? OFFSET ?
  `).bind(ownerId, pageSize, offset).all();

  return Response.json({ data: rows.results, page, pageSize });
}
```

---

## Anti-patterns

- **Storing only in D1 without calling the CF API** — Cloudflare Email Routing will not route the address; the alias silently fails to receive mail.
- **Caching alias lookups in KV without invalidation** — a disabled alias may still forward if the Worker reads a stale KV value.
- **Not storing `cf_rule_tag`** — without the rule tag, you cannot delete the routing rule, leaving orphaned rules in Cloudflare that accumulate and eventually hit the rule limit.
- **Re-using local parts after deletion** — a deleted alias re-created with the same address may receive historic mail intended for the old owner if the catch-all is active.

---

## Gotchas

- Cloudflare Email Routing rule priority matters: explicit address rules (priority 10) must be lower-numbered than catch-all wildcard rules (priority 100) or the catch-all fires first.
- The CF Routing API uses a `tag` (UUID-like string) as the rule identifier, not an integer ID; store this in D1 at creation time.
- Cloudflare zone email routing must be enabled and the zone must have MX records pointing to `route1.mx.cloudflare.net` etc. before rules take effect.
- An Email Worker and address routing rules are mutually exclusive per zone — you either use an Email Worker OR rules, not both, unless you use the Email Worker to call `message.forward()` explicitly.

---

## Verification

```bash
# Create an alias
curl -X POST https://workers.example.com/aliases \
  -H "Authorization: Bearer $USER_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"localPart":"support","domain":"example.com","destination":"team@company.com"}'

# Check CF routing rules exist
curl -s "https://api.cloudflare.com/client/v4/zones/$ZONE_ID/email/routing/rules" \
  -H "Authorization: Bearer $CF_API_TOKEN" | jq '.result[] | {name,enabled,tag}'

# Disable the alias
curl -X PATCH https://workers.example.com/aliases/ALIAS_ID \
  -d '{"status":"disabled"}'

# Confirm D1 state
wrangler d1 execute DB --command "SELECT * FROM aliases WHERE local_part='support'"

# View event history
wrangler d1 execute DB --command \
  "SELECT event_type, detail, datetime(created_at/1000,'unixepoch') FROM alias_events WHERE alias_id='ALIAS_ID'"
```

---

## Related

- `email-alias-routing-kv-workers.md`
- `cloudflare-email-routing-workers.md`
- `email-forwarding-setup.md`
- `email-forwarding-spf-alignment-srs-workers.md`
- `email-forwarding-loop-detection-d1-workers.md`
- `inbound-email-processing.md`

---

## Sources

- Cloudflare Email Routing API: https://developers.cloudflare.com/api/resources/email_routing/
- Cloudflare Email Workers: https://developers.cloudflare.com/email-routing/email-workers/
- Email Routing Rules: https://developers.cloudflare.com/email-routing/setup/email-routing-addresses/
