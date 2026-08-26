# Managing Cloudflare WAF Custom Rulesets Programmatically via Workers

Date: 2026-08-24
Author: example.com
Status: production

---

## Symptom / Use-case

Your WAF rules are clicked together in the Cloudflare dashboard and drift between zones. You need to manage custom WAF rules as code — create, update, reorder, and promote them from a staging zone to production programmatically from a Worker or CI pipeline, with the same rule set applied consistently across all zones.

## Context

Cloudflare WAF custom rulesets live in the **Rulesets API** (`/zones/{zone_id}/rulesets` or the account-level `/accounts/{account_id}/rulesets`). A ruleset contains an ordered list of rules, each with:
- A **filter expression** (Wireshark-style) matching request attributes
- An **action** (`block`, `challenge`, `js_challenge`, `managed_challenge`, `log`, `allow`, `skip`)
- A **priority** position within the ruleset

The zone entry-point ruleset (`http_request_firewall_custom`) is the deployment target. Rules execute top-to-bottom by priority.

Custom WAF rulesets require a **Pro plan** or higher.

## Solution

### 1. API client and authentication

```typescript
const CF_API = "https://api.cloudflare.com/client/v4";

export interface Env {
  CF_WAF_TOKEN: string;    // needs Zone:Firewall Services:Edit
  CF_ZONE_ID:  string;
  CF_ACCOUNT_ID: string;
}

async function cfWaf<T>(
  method: string,
  path: string,
  token: string,
  body?: unknown,
): Promise<T> {
  const res = await fetch(`${CF_API}${path}`, {
    method,
    headers: {
      Authorization:  `Bearer ${token}`,
      "Content-Type": "application/json",
    },
    body: body ? JSON.stringify(body) : undefined,
  });

  if (res.status === 429) {
    const retryAfter = Number(res.headers.get("Retry-After") ?? 5);
    await new Promise(r => setTimeout(r, retryAfter * 1000));
    return cfWaf<T>(method, path, token, body);  // single retry
  }

  const json = await res.json<{ result: T; success: boolean; errors: { message: string }[] }>();
  if (!json.success) {
    throw new Error(`WAF API error: ${json.errors.map(e => e.message).join("; ")}`);
  }
  return json.result;
}
```

### 2. Retrieve the zone entry-point ruleset

```typescript
interface Rule {
  id?:          string;     // set by API after creation
  description?: string;
  expression:   string;     // Wireshark filter syntax
  action:       RuleAction;
  action_parameters?: ActionParameters;
  enabled:      boolean;
  logging?:     { enabled: boolean };
}

type RuleAction = "block" | "challenge" | "js_challenge" | "managed_challenge" | "log" | "allow" | "skip";

interface ActionParameters {
  response?: {              // for action: "block"
    status_code: number;
    content_type: "text/plain" | "application/json";
    content: string;
  };
  ruleset?: "current";     // for action: "skip" (skip remaining rules)
  phases?: string[];       // phases to skip
}

interface Ruleset {
  id:          string;
  name:        string;
  kind:        "zone" | "root" | "custom";
  phase:       string;
  rules:       Rule[];
  last_updated: string;
}

async function getZoneFirewallRuleset(env: Env): Promise<Ruleset> {
  // The zone-level custom WAF ruleset has phase = http_request_firewall_custom
  const rulesets = await cfWaf<Ruleset[]>("GET",
    `/zones/${env.CF_ZONE_ID}/rulesets`, env.CF_WAF_TOKEN);

  const waf = rulesets.find(r => r.phase === "http_request_firewall_custom");
  if (!waf) throw new Error("WAF custom ruleset not found — it may need to be created");
  return cfWaf<Ruleset>("GET",
    `/zones/${env.CF_ZONE_ID}/rulesets/${waf.id}`, env.CF_WAF_TOKEN);
}
```

### 3. Creating custom rules

```typescript
// Block a specific IP range
const blockBadActorRule: Rule = {
  description: "Block known bad actor CIDR",
  expression:  `(ip.src in {203.0.113.0/24 198.51.100.0/24})`,
  action:      "block",
  action_parameters: {
    response: {
      status_code: 403,
      content_type: "application/json",
      content: JSON.stringify({ error: "Forbidden" }),
    },
  },
  enabled: true,
};

// JS challenge for suspicious user agents
const challengeSuspiciousUARule: Rule = {
  description: "JS challenge headless browsers",
  expression:  `(http.user_agent contains "HeadlessChrome" or http.user_agent eq "")`,
  action:      "js_challenge",
  enabled:     true,
};

// Allow internal health check paths
const allowHealthzRule: Rule = {
  description: "Allow internal health checks",
  expression:  `(http.request.uri.path eq "/healthz" and ip.src in {10.0.0.0/8})`,
  action:      "allow",
  enabled:     true,
};
```

### 4. Rule conditions — URI, IP, and header matching

```typescript
// URI matching
`(http.request.uri.path matches "^/admin/.*" and not ip.src in {10.0.0.0/8})`

// HTTP method + URI
`(http.request.method eq "POST" and http.request.uri.path contains "/api/v1/login")`

// Request header value
`(any(http.request.headers["x-api-key"][*] eq "") and http.request.uri.path matches "^/api/")`

// Compound country + URI
`(ip.geoip.country in {"CN" "RU" "KP"} and http.request.uri.path eq "/checkout")`

// Firewall score (Bot Management required for cf.bot_management.score)
`(cf.threat_score gt 10 and http.request.uri.path ne "/healthz")`

// Rate-limit burst (use with WAF action "managed_challenge")
`(http.request.uri.path eq "/api/v1/auth" and cf.threat_score gt 0)`
```

### 5. Rule priority ordering

Rules execute in array order within the ruleset. The first matching rule wins (unless action is `log` or a skip is configured).

```typescript
async function updateRuleset(
  env: Env,
  rulesetId: string,
  rules: Rule[],
): Promise<Ruleset> {
  // PUT replaces the entire rule list — order = priority
  // Rules without `id` are created; rules with `id` are updated.
  return cfWaf<Ruleset>(
    "PUT",
    `/zones/${env.CF_ZONE_ID}/rulesets/${rulesetId}`,
    env.CF_WAF_TOKEN,
    { rules },
  );
}

// Priority order: allow rules first, then blocks, then challenges
const orderedRules: Rule[] = [
  allowHealthzRule,          // 1. Allow internal paths first
  blockBadActorRule,         // 2. Block known bad IPs
  challengeSuspiciousUARule, // 3. Challenge suspicious agents
];

await updateRuleset(env, rulesetId, orderedRules);
```

### 6. Staging vs production ruleset deployment

```typescript
// Strategy: maintain rules as code in a TypeScript module
// Deploy to staging zone first, verify, then promote to prod

const ZONES = {
  staging: "STAGING_ZONE_ID",
  prod:    "PROD_ZONE_ID",
} as const;

async function deployWafRules(
  token: string,
  targetEnv: keyof typeof ZONES,
  rules: Rule[],
): Promise<void> {
  const zoneId = ZONES[targetEnv];

  // 1. Fetch existing ruleset ID
  const rulesets = await cfWaf<Ruleset[]>("GET",
    `/zones/${zoneId}/rulesets`, token);

  let rulesetId: string;
  const existing = rulesets.find(r => r.phase === "http_request_firewall_custom");

  if (existing) {
    rulesetId = existing.id;
  } else {
    // Create the entry-point ruleset if it doesn't exist yet
    const created = await cfWaf<Ruleset>("POST",
      `/zones/${zoneId}/rulesets`, token,
      {
        name:  `custom-waf-${targetEnv}`,
        kind:  "zone",
        phase: "http_request_firewall_custom",
        rules: [],
      },
    );
    rulesetId = created.id;
  }

  // 2. Apply rules
  await cfWaf<Ruleset>("PUT",
    `/zones/${zoneId}/rulesets/${rulesetId}`, token,
    { rules },
  );

  console.log(`WAF rules deployed to ${targetEnv} zone ${zoneId}`);
}

// CI pipeline
await deployWafRules(token, "staging", orderedRules);
// ... run integration tests against staging ...
await deployWafRules(token, "prod",    orderedRules);
```

### 7. Add a single rule without replacing the full set

```typescript
async function appendRule(
  env: Env,
  rulesetId: string,
  rule: Rule,
  position?: { before?: string; after?: string; index?: number },
): Promise<Rule> {
  return cfWaf<Rule>(
    "POST",
    `/zones/${env.CF_ZONE_ID}/rulesets/${rulesetId}/rules`,
    env.CF_WAF_TOKEN,
    { ...rule, position },
  );
}

// Insert before an existing rule ID
await appendRule(env, rulesetId, blockBadActorRule, { before: existingRuleId });
```

## Implementation Details

- Wireshark filter expressions are validated server-side. A syntax error returns a 400 with the error message.
- The token needs `Zone:Firewall Services:Edit` — not the generic `Zone:Edit` token.
- `PUT /rulesets/{id}` is a full replacement. Rules without an `id` are assigned new IDs. Rules with a known `id` are updated in place, preserving their hit counters in analytics.
- Account-level managed rulesets (`/accounts/{id}/rulesets`) propagate to all zones using a zone-level `execute` action that references the account ruleset by ID.
- Log-only rules (`action: "log"`) do not block traffic but appear in Firewall Events — useful for dry-running a new rule before enforcing it.

## Anti-patterns

- Do not deploy directly to production without a staging zone test — a misconfigured WAF rule can block all traffic including your own monitoring.
- Do not use `PUT` on the ruleset from multiple concurrent processes — last write wins and you may lose rules.
- Do not put `allow` rules at the bottom of the list — they must come before `block` rules that would otherwise match the same traffic.
- Do not omit `enabled: false` on experimental rules during staging — disabled rules are deployed but do not execute, letting you toggle them quickly.
- Do not store WAF rule expressions as free-form strings in config files without tests — a typo silently creates an invalid rule that the API rejects at deploy time.

## Gotchas

- `cf.threat_score` and `cf.bot_management.*` fields require specific plan add-ons. Using them on a lower plan returns an expression validation error.
- Rule IDs are zone-specific. You cannot copy a rule ID from staging to prod and use it as a `before`/`after` position reference.
- `action: "skip"` with `ruleset: "current"` skips the remaining rules in the **custom** ruleset only; managed WAF rules still run unless you also specify `phases: ["http_ratelimit", "http_request_firewall_managed"]`.
- The Rulesets API differs from the legacy Firewall Rules API (`/zones/{id}/firewall/rules`). Do not mix them — the legacy API is deprecated.
- Cloudflare applies WAF rules before Workers. A blocked request never reaches your Worker.

## Verification

```bash
# List rulesets on the zone
curl -sS -H "Authorization: Bearer $CF_TOKEN" \
  "https://api.cloudflare.com/client/v4/zones/$ZONE_ID/rulesets" \
  | jq '.result[] | {id, name, phase}'

# Fetch all rules in the custom WAF ruleset
curl -sS -H "Authorization: Bearer $CF_TOKEN" \
  "https://api.cloudflare.com/client/v4/zones/$ZONE_ID/rulesets/$RULESET_ID" \
  | jq '.result.rules[] | {description, action, enabled}'

# Test a block rule
curl -si -H "X-Forwarded-For: 203.0.113.1" https://example.com/ | head -5
# Expected: HTTP/2 403

# Test allow rule (from 10.0.0.0/8)
curl -si https://example.com/healthz | head -5
# Expected: HTTP/2 200
```

## Related

- `documentation/categories/infra/workers-cdn-cache-purge-api.md`
- `documentation/categories/infra/workers-log-drain-r2-archival.md`
- `documentation/categories/infra/workers-load-balancer-health-origins.md`

## Sources

- https://developers.cloudflare.com/waf/custom-rules/
- https://developers.cloudflare.com/ruleset-engine/rulesets-api/
- https://developers.cloudflare.com/ruleset-engine/rules-language/fields/
- https://developers.cloudflare.com/api/operations/zone-rulesets-create-a-zone-ruleset
