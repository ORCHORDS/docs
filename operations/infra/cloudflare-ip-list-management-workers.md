# Cloudflare IP List Management via Workers Cron

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case
You maintain WAF rules that reference Cloudflare IP Lists (allow-lists, block-lists) and need those lists refreshed automatically from external threat feeds, internal CMDB exports, or CDN origin IP ranges — without a deploy pipeline involved.

## Context
Cloudflare account-level IP Lists can contain up to 1,000 items each and are referenced in WAF Ruleset Engine expressions as `$list_name`. A Workers Cron Trigger can fetch external feeds on a schedule and call the Cloudflare API to perform atomic list replacements, keeping WAF rules current without any human intervention. The Worker runs inside the Cloudflare network; the Cloudflare API is a short TLS hop away and does not egress to the public internet.

## Creating the IP List and Worker Binding

```toml
# wrangler.toml
name = "ip-list-manager"
main = "src/index.ts"
compatibility_date = "2025-10-01"
compatibility_flags = ["nodejs_compat"]

[vars]
CF_ACCOUNT_ID = "your-account-id"
ALLOW_LIST_ID = "your-allowlist-uuid"
BLOCK_LIST_ID  = "your-blocklist-uuid"

[triggers]
crons = ["0 */6 * * *"]   # every 6 hours

# Bind the Cloudflare API token as a secret:
# wrangler secret put CF_API_TOKEN
```

## Fetching and Replacing List Items

```typescript
// src/index.ts
export interface Env {
  CF_API_TOKEN: string;
  CF_ACCOUNT_ID: string;
  ALLOW_LIST_ID: string;
  BLOCK_LIST_ID: string;
}

interface CfListItem {
  ip: string;
  comment?: string;
}

// Fetch a newline-delimited IP list from a threat feed or internal source
async function fetchIpFeed(url: string): Promise<string[]> {
  const res = await fetch(url, {
    headers: { "User-Agent": "cloudflare-ip-list-manager/1.0" },
    cf: { cacheTtl: 300 },  // cache at edge for 5 min to reduce origin load
  });
  if (!res.ok) throw new Error(`Feed fetch failed: ${res.status} ${url}`);
  const text = await res.text();
  return text
    .split("\n")
    .map((l) => l.trim())
    .filter((l) => l && !l.startsWith("#"));  // strip comments and blanks
}

// Replace all items in a Cloudflare IP List atomically (PUT replaces the list)
async function replaceListItems(
  accountId: string,
  listId: string,
  ips: string[],
  apiToken: string
): Promise<void> {
  const items: CfListItem[] = ips.map((ip) => ({
    ip,
    comment: `synced ${new Date().toISOString()}`,
  }));

  // Cloudflare's PUT endpoint replaces the entire list in one atomic operation
  const res = await fetch(
    `https://api.cloudflare.com/client/v4/accounts/${accountId}/rules/lists/${listId}/items`,
    {
      method: "PUT",
      headers: {
        Authorization: `Bearer ${apiToken}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify(items),
    }
  );

  if (!res.ok) {
    const err = await res.text();
    throw new Error(`List replace failed (${res.status}): ${err}`);
  }

  const data = await res.json<{ result: { operation_id: string } }>();
  // PUT is async on the Cloudflare side; poll the operation until it completes
  await pollOperation(accountId, data.result.operation_id, apiToken);
}

async function pollOperation(
  accountId: string,
  operationId: string,
  apiToken: string,
  maxAttempts = 20
): Promise<void> {
  for (let i = 0; i < maxAttempts; i++) {
    await scheduler.wait(2000);  // Workers scheduler API
    const res = await fetch(
      `https://api.cloudflare.com/client/v4/accounts/${accountId}/rules/lists/bulk_operations/${operationId}`,
      { headers: { Authorization: `Bearer ${apiToken}` } }
    );
    const data = await res.json<{ result: { status: string; error?: string } }>();
    if (data.result.status === "completed") return;
    if (data.result.status === "failed") {
      throw new Error(`Operation failed: ${data.result.error}`);
    }
  }
  throw new Error("Operation did not complete in time");
}

export default {
  async scheduled(_event: ScheduledEvent, env: Env, _ctx: ExecutionContext): Promise<void> {
    const [allowIps, blockIps] = await Promise.all([
      // Internal allow-list: CI egress IPs, office NAT, monitoring agents
      fetchIpFeed("https://internal.example.com/feeds/allow-ips.txt"),
      // Threat feed: compromised IP ranges (publicly available lists)
      fetchIpFeed("https://feodotracker.abuse.ch/downloads/ipblocklist.txt"),
    ]);

    console.log(`Refreshing allow list: ${allowIps.length} IPs`);
    console.log(`Refreshing block list: ${blockIps.length} IPs`);

    await Promise.all([
      replaceListItems(env.CF_ACCOUNT_ID, env.ALLOW_LIST_ID, allowIps, env.CF_API_TOKEN),
      replaceListItems(env.CF_ACCOUNT_ID, env.BLOCK_LIST_ID, blockIps, env.CF_API_TOKEN),
    ]);

    console.log("IP lists refreshed successfully");
  },
};
```

## Referencing Lists in WAF Rules

```typescript
// In a Pulumi or Terraform WAF custom ruleset, reference lists by name:
// Cloudflare auto-creates the $list_name variable when the list exists in the account.

const wafRules = [
  {
    description: "Allow known-good IPs through WAF",
    // List name in the account dashboard maps to $allow_ips in expressions
    expression: `(ip.src in $allow_ips)`,
    action: "skip",
    actionParameters: { ruleset: "current" },
  },
  {
    description: "Block threat-feed IPs at edge",
    expression: `(ip.src in $block_ips)`,
    action: "block",
  },
];

// The WAF expression uses the list *name* (not ID) prefixed with $.
// List names must be lowercase with underscores; hyphens are not allowed.
```

## Handling Large Lists (> 1,000 Items)

```typescript
// Cloudflare IP Lists cap at 1,000 items. For larger feeds, deduplicate and
// prioritise by threat score, or split across multiple lists and OR them in WAF.
function deduplicateAndTrim(ips: string[], max: number): string[] {
  const unique = [...new Set(ips)];
  if (unique.length > max) {
    console.warn(`Feed has ${unique.length} IPs; truncating to ${max}`);
  }
  return unique.slice(0, max);
}
```

## Anti-patterns
- Using `PATCH` (item-level updates) instead of `PUT` (full replace) for scheduled syncs — partial updates accumulate stale entries that are never removed
- Storing the API token in `[vars]` plaintext — use `wrangler secret put CF_API_TOKEN` so it is encrypted at rest
- Polling the bulk operation in a tight loop without delay — hammers the API; use `scheduler.wait(2000)` between polls
- Using a single over-scoped token — scope the API token to `Rules: Edit` and `Account Filter Lists: Edit` only
- Firing the cron more frequently than the feed updates — check the feed's `Last-Modified` header and skip the PUT if unchanged

## Gotchas
- The `PUT /rules/lists/{id}/items` endpoint is asynchronous; it returns an `operation_id` you must poll — it does not guarantee completion before the HTTP response
- List names (not IDs) are what WAF expressions use; renaming a list breaks all referencing WAF rules silently
- Workers `scheduled()` has a 30-second CPU time limit; a large feed fetch + two list replacements with polling can exceed this — use `ctx.waitUntil()` to extend the deadline
- Cloudflare IP Lists are account-scoped, not zone-scoped; one list can be referenced in WAF rules across all zones in the account
- An empty `PUT` (zero items) is valid and will clear the list entirely — validate feed response length before calling replace

## Verification
```bash
# List all IP lists in the account
curl -s "https://api.cloudflare.com/client/v4/accounts/$CF_ACCOUNT_ID/rules/lists" \
  -H "Authorization: Bearer $CF_API_TOKEN" | jq '.result[] | {id, name, kind, num_items}'

# Check current items in a list
curl -s "https://api.cloudflare.com/client/v4/accounts/$CF_ACCOUNT_ID/rules/lists/$LIST_ID/items" \
  -H "Authorization: Bearer $CF_API_TOKEN" | jq '.result | length, .[0:3]'

# Trigger a manual cron run (Wrangler dev)
wrangler dev --test-scheduled
curl "http://localhost:8787/__scheduled?cron=*+*+*+*+*"
```

## Related
- `pulumi-cloudflare-waf-custom-rules.md` — consuming IP lists in WAF rulesets via Pulumi
- `cloudflare-waf-custom-ruleset-terraform.md` — Terraform WAF ruleset referencing IP lists
- `terraform-cloudflare-rate-limiting-rules.md` — combining IP lists with rate limiting
- `workers-subrequest-budget-management.md` — staying within the 50-subrequest budget per Worker invocation

## Sources
- https://developers.cloudflare.com/waf/tools/lists/
- https://developers.cloudflare.com/api/operations/lists-get-list-items
- https://developers.cloudflare.com/workers/configuration/cron-triggers/
- https://developers.cloudflare.com/ruleset-engine/rules-language/values/#lists
- https://developers.cloudflare.com/waf/tools/lists/custom-lists/
