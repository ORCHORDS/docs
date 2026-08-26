# Cloudflare WAF Custom Rules Workers API Integration

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

You need to programmatically manage Cloudflare WAF Custom Rules from within Workers —
auto-blocking abusive IPs discovered at runtime, dynamically adjusting rate-limit
expressions based on D1 data, or syncing threat intelligence feeds into WAF rules
without touching the dashboard or a CI pipeline.

Separately, you want Workers to inspect WAF metadata on inbound requests (threat score,
matched rule ID) and apply application-level logic on top.

---

## Context

Cloudflare WAF Custom Rules live in a **Ruleset** under the `http_request_firewall_custom`
phase. Each rule has a `description`, an `expression` (Wireshark-style filter language),
and an `action` (`block`, `challenge`, `js_challenge`, `managed_challenge`, `log`, `skip`).

WAF rules are managed via the Cloudflare Rulesets API:

```
GET/PUT  /client/v4/zones/{zone_id}/rulesets/phases/http_request_firewall_custom/entrypoint
```

Workers can call this API using a scoped API token (minimum permissions:
`Zone » Zone WAF » Edit`). Best practice: store the token in **Workers Secrets** and
call the API from a privileged internal Worker (never expose WAF management endpoints
to the public internet).

example project platform uses this pattern to:
- Auto-block IPs that trigger > 50 failed auth attempts/minute (detected via Analytics Engine)
- Sync CIDR blocklists from a threat intelligence D1 table into WAF expressions
- Create temporary "soft block" (managed challenge) rules for flash-sale bot traffic

---

## Reading Current WAF Custom Rules

```typescript
// src/lib/waf-api.ts
const CF_API_BASE = 'https://api.cloudflare.com/client/v4';

export interface WafRule {
  id?: string;
  description: string;
  expression: string;
  action: 'block' | 'challenge' | 'js_challenge' | 'managed_challenge' | 'log' | 'skip';
  enabled: boolean;
}

export interface WafRuleset {
  id: string;
  rules: WafRule[];
}

export async function getCustomRuleset(env: Env): Promise<WafRuleset> {
  const resp = await fetch(
    `${CF_API_BASE}/zones/${env.CF_ZONE_ID}/rulesets/phases/http_request_firewall_custom/entrypoint`,
    {
      headers: {
        Authorization: `Bearer ${env.CF_WAF_TOKEN}`,
        'Content-Type': 'application/json',
      },
    },
  );

  if (!resp.ok) {
    const body = await resp.text();
    throw new Error(`WAF ruleset GET failed ${resp.status}: ${body}`);
  }

  const data = await resp.json<{ result: WafRuleset }>();
  return data.result;
}
```

---

## Adding an IP Block Rule Programmatically

```typescript
// src/lib/waf-api.ts (continued)
export async function blockIp(ip: string, reason: string, env: Env): Promise<void> {
  const ruleset = await getCustomRuleset(env);

  // Check if a block for this IP already exists
  const alreadyBlocked = ruleset.rules.some(r =>
    r.expression.includes(`"${ip}"`) && r.action === 'block',
  );
  if (alreadyBlocked) return;

  // Prepend the new block rule (WAF rules are evaluated in order; highest priority first)
  const newRule: WafRule = {
    description: `Auto-block ${ip}: ${reason}`,
    expression: `ip.src eq ${ip}`,
    action: 'block',
    enabled: true,
  };

  const updatedRules: WafRule[] = [newRule, ...ruleset.rules];

  await putCustomRuleset(ruleset.id, updatedRules, env);
}

export async function putCustomRuleset(
  rulesetId: string,
  rules: WafRule[],
  env: Env,
): Promise<void> {
  const resp = await fetch(
    `${CF_API_BASE}/zones/${env.CF_ZONE_ID}/rulesets/${rulesetId}`,
    {
      method: 'PUT',
      headers: {
        Authorization: `Bearer ${env.CF_WAF_TOKEN}`,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ rules }),
    },
  );

  if (!resp.ok) {
    const body = await resp.text();
    throw new Error(`WAF ruleset PUT failed ${resp.status}: ${body}`);
  }
}
```

---

## Auto-Block from Analytics Engine Abuse Detection

```typescript
// src/scheduled/abuse-detector.ts
// Runs every 5 minutes via cron; queries Analytics Engine for abuse patterns,
// then pushes block rules to WAF for confirmed abusers.

export default {
  async scheduled(_event: ScheduledEvent, env: Env, ctx: ExecutionContext): Promise<void> {
    ctx.waitUntil(runAbuseDetection(env));
  },
};

async function runAbuseDetection(env: Env): Promise<void> {
  // Query Analytics Engine SQL API for IPs with excessive failed logins
  const query = `
    SELECT blob1 AS ip, SUM(double1) AS fail_count
    FROM ${env.AE_DATASET}
    WHERE blob2 = 'auth_fail'
      AND timestamp > NOW() - INTERVAL '5' MINUTE
    GROUP BY ip
    HAVING fail_count > 50
    ORDER BY fail_count DESC
    LIMIT 20
  `;

  const resp = await fetch(
    `https://api.cloudflare.com/client/v4/accounts/${env.CF_ACCOUNT_ID}/analytics_engine/sql`,
    {
      method: 'POST',
      headers: { Authorization: `Bearer ${env.CF_WAF_TOKEN}` },
      body: query,
    },
  );

  if (!resp.ok) return;

  const result = await resp.json<{ data: { ip: string; fail_count: number }[] }>();

  for (const row of result.data) {
    try {
      await blockIp(row.ip, `auth_fail count=${row.fail_count}`, env);
      console.log(`[waf] blocked ${row.ip} (fail_count=${row.fail_count})`);
    } catch (err) {
      console.error(`[waf] failed to block ${row.ip}:`, err);
    }
  }
}
```

---

## Bulk CIDR Blocklist from D1

```typescript
// src/scheduled/cidr-sync.ts
// Synchronizes a D1-managed blocklist into a single WAF rule using ip.src in {...}

export async function syncCidrBlocklist(env: Env): Promise<void> {
  const rows = await env.DB.prepare(
    `SELECT cidr FROM blocklisted_cidrs WHERE active = 1 LIMIT 1000`,
  ).all<{ cidr: string }>();

  if (rows.results.length === 0) return;

  // Build a WAF expression: ip.src in {1.2.3.0/24 5.6.7.0/24 ...}
  const cidrList = rows.results.map(r => r.cidr).join(' ');
  const expression = `ip.src in {${cidrList}}`;

  const ruleset = await getCustomRuleset(env);

  // Find or replace the CIDR blocklist rule by its stable description tag
  const RULE_TAG = '[auto] cidr-blocklist';
  const filtered = ruleset.rules.filter(r => r.description !== RULE_TAG);

  const cidrRule: WafRule = {
    description: RULE_TAG,
    expression,
    action: 'block',
    enabled: true,
  };

  // Place the CIDR rule first for fastest evaluation
  await putCustomRuleset(ruleset.id, [cidrRule, ...filtered], env);
  console.log(`[waf] synced ${rows.results.length} CIDRs to blocklist rule`);
}
```

---

## Reading WAF Metadata on Inbound Requests

Workers can read WAF results from incoming requests via `cf` properties:

```typescript
// src/workers/waf-aware-handler.ts
export default {
  async fetch(req: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    const cf = req.cf as CfProperties | undefined;

    if (cf) {
      // Threat score from Cloudflare's IP reputation (0=clean, 100=malicious)
      const threatScore = cf.threatScore ?? 0;

      // Bot management score if Enterprise Bot Management is enabled
      const botScore = (cf as any).botManagement?.score ?? 100;

      // Log suspicious-but-not-blocked requests for tuning
      if (threatScore > 20 || botScore < 30) {
        ctx.waitUntil(
          env.ANALYTICS.writeDataPoint({
            blobs: ['suspicious_request', req.url, cf.country ?? 'XX'],
            doubles: [threatScore, botScore],
            indexes: ['waf_monitoring'],
          }),
        );
      }

      // Hard-block at application layer as a defense-in-depth measure
      if (threatScore > 80) {
        return new Response('Blocked', {
          status: 403,
          headers: { 'CF-Chl-Bypass': '0' },
        });
      }
    }

    return fetch(req);
  },
};
```

---

## Temporary "Soft Block" for Flash Sale Protection

```typescript
// Create a managed_challenge rule scoped to a specific path during a sale event
export async function enableFlashSaleProtection(
  pathPrefix: string,
  durationMinutes: number,
  env: Env,
): Promise<void> {
  const ruleset = await getCustomRuleset(env);

  const expiresAt = new Date(Date.now() + durationMinutes * 60_000).toISOString();
  const rule: WafRule = {
    description: `[flash-sale] challenge bots on ${pathPrefix} until ${expiresAt}`,
    expression: `http.request.uri.path starts_with "${pathPrefix}" and cf.bot_management.score lt 30`,
    action: 'managed_challenge',
    enabled: true,
  };

  await putCustomRuleset(ruleset.id, [rule, ...ruleset.rules], env);

  // Schedule auto-removal via a Durable Object alarm or Workflow
  await env.DB.prepare(
    `INSERT INTO scheduled_waf_removals (description_tag, remove_at)
     VALUES (?1, datetime(?2))`,
  ).bind(rule.description, expiresAt).run();
}
```

---

## Anti-patterns

- **Calling the WAF API on every inbound request** — this makes your Worker as slow as
  an API round-trip (hundreds of ms). Manage rules from scheduled Workers or admin
  endpoints only; read WAF data from `req.cf` inline.
- **Storing the WAF API token in wrangler.toml** — tokens go in `[vars]` (plaintext)
  accidentally. Always use `wrangler secret put CF_WAF_TOKEN`.
- **Overwriting the full ruleset without a read-modify-write cycle** — a PUT without
  first GETting the current state discards all existing rules including manually
  created ones.
- **Building IP expressions via string concatenation without sanitization** — an IP
  from an untrusted source could inject WAF expression syntax. Validate IPs with a
  regex before inserting into the expression.
- **Accumulating stale block rules** — auto-added rules that are never cleaned up slow
  down ruleset evaluation and hit the rule limit (default 100 custom rules per zone).

---

## Gotchas

- The Rulesets API PUT replaces the **entire** ruleset. Concurrent PUT calls from two
  Workers can overwrite each other. Use a Durable Object or D1 mutex around WAF writes.
- WAF expression length limit is **4 096 characters** per rule. A large CIDR list may
  exceed this; split into multiple rules.
- `ip.src in {CIDR}` supports IPv4 CIDRs and individual IPv6 addresses but not IPv6
  CIDR ranges in the firewall expression language — use `ip.src.in.list` for large
  IPv6 sets.
- Rule changes take effect globally within ~30 seconds. There is no atomic cut-over;
  a brief window exists where some PoPs have the old ruleset.
- The `CF_WAF_TOKEN` needs the **Zone » Zone WAF » Edit** permission — not the full
  `Zone » Zone Settings » Edit`. Use the least-privilege scope.

---

## Verification

```bash
# Confirm the custom ruleset after an update
curl -s "https://api.cloudflare.com/client/v4/zones/$CF_ZONE_ID/rulesets/phases/http_request_firewall_custom/entrypoint" \
  -H "Authorization: Bearer $CF_WAF_TOKEN" \
  | jq '.result.rules[] | {description, expression, action, enabled}'

# Test that a blocked IP receives 403
curl -si --resolve "example.com:443:1.2.3.4" "https://example.com/api/health" \
  | head -5
```

```typescript
// Integration test: verify blockIp adds a rule
import { describe, it, expect, vi } from 'vitest';
import { blockIp } from './waf-api';

describe('blockIp', () => {
  it('adds a block rule for a new IP', async () => {
    const putSpy = vi.fn().mockResolvedValue(undefined);
    vi.mock('./waf-api', async (importOriginal) => {
      const mod = await importOriginal<typeof import('./waf-api')>();
      return { ...mod, putCustomRuleset: putSpy };
    });

    const mockEnv = { CF_ZONE_ID: 'z', CF_WAF_TOKEN: 't' } as any;
    // Provide a mock getCustomRuleset that returns empty rules
    vi.spyOn(await import('./waf-api'), 'getCustomRuleset').mockResolvedValue({
      id: 'rs1', rules: [],
    });

    await blockIp('1.2.3.4', 'test reason', mockEnv);

    expect(putSpy).toHaveBeenCalledWith(
      'rs1',
      expect.arrayContaining([
        expect.objectContaining({ expression: 'ip.src eq 1.2.3.4', action: 'block' }),
      ]),
      mockEnv,
    );
  });
});
```

---

## Related

- `waf-best-practices.md`
- `waf-rate-limiting-deep-dive.md`
- `waf-managed-rules-exception-order-and-future-rule-drift.md`
- `cloudflare-workers-analytics-engine-custom-metrics.md`
- `durable-objects-distributed-lock-leader-election.md`
- `api-token-least-privilege-and-rotation-governance.md`

---

## Sources

- https://developers.cloudflare.com/waf/custom-rules/
- https://developers.cloudflare.com/ruleset-engine/rulesets-api/
- https://developers.cloudflare.com/ruleset-engine/rules-language/
- https://developers.cloudflare.com/api/resources/rulesets/
- https://developers.cloudflare.com/workers/runtime-apis/request/#incomingrequestcfproperties
