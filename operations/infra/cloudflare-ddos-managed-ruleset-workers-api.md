# Programmatic DDoS Ruleset Management: Cloudflare Rulesets API via Workers Scheduled Job

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

During traffic anomalies detected by Cloudflare Analytics Engine, you want to automatically tighten or relax DDoS managed ruleset sensitivity without manual dashboard intervention. A Workers Cron Trigger queries Analytics Engine for traffic spikes, then calls the Rulesets API to adjust the DDoS ruleset override sensitivity level in real time.

## Context

- Cloudflare DDoS Managed Rulesets (free feature, available on all plans for L7)
- Cloudflare Rulesets API for programmatic override management
- Cloudflare Analytics Engine for real-time traffic data (Workers Analytics Engine binding)
- Workers Cron Trigger runs the evaluation every 5 minutes
- Stack: TypeScript Workers, Analytics Engine, Rulesets API, Wrangler v3

---

## Section 1: Wrangler Config — Cron Trigger + Analytics Engine

```toml
# wrangler.toml
name = "ddos-auto-tuner"
main = "src/index.ts"
compatibility_date = "2024-09-23"

[triggers]
crons = ["*/5 * * * *"] # Run every 5 minutes

[[analytics_engine_datasets]]
binding = "TRAFFIC_AE"
dataset = "traffic_metrics"

[vars]
ZONE_ID = "<your-zone-id>"
CF_ACCOUNT_ID = "<your-account-id>"
# Sensitive values in Wrangler secrets:
# CF_API_TOKEN — zone-level Firewall/DDoS write permission
```

---

## Section 2: Query Analytics Engine for Traffic Anomalies

```typescript
// src/analytics.ts

export interface Env {
  TRAFFIC_AE: AnalyticsEngineDataset;
  CF_ACCOUNT_ID: string;
  CF_API_TOKEN: string;
  ZONE_ID: string;
}

interface AEQueryResult {
  data: Array<{
    dimensions: string[];
    metrics: number[];
  }>;
  meta: Array<{ name: string; type: string }>;
  rows: number;
  rows_before_limit_at_least: number;
}

// Traffic thresholds for sensitivity changes
const HIGH_TRAFFIC_RPS_THRESHOLD = 50_000; // requests/min
const NORMAL_TRAFFIC_RPS_THRESHOLD = 10_000;

export async function queryTrafficAnomaly(env: Env): Promise<{
  currentRPM: number;
  isAnomaly: boolean;
  suggestedSensitivity: "low" | "medium" | "high" | "essentially_off";
}> {
  // Analytics Engine SQL API
  const query = `
    SELECT
      sum(_sample_interval) AS total_requests,
      blob1 AS endpoint
    FROM traffic_metrics
    WHERE timestamp > now() - INTERVAL '5' MINUTE
    GROUP BY endpoint
    ORDER BY total_requests DESC
    LIMIT 10
  `;

  const res = await fetch(
    `https://api.cloudflare.com/client/v4/accounts/${env.CF_ACCOUNT_ID}/analytics_engine/sql`,
    {
      method: "POST",
      headers: {
        Authorization: `Bearer ${env.CF_API_TOKEN}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ query }),
    }
  );

  if (!res.ok) {
    throw new Error(`Analytics Engine query failed: ${await res.text()}`);
  }

  const result = await res.json() as AEQueryResult;
  const totalRequests = result.data.reduce(
    (sum, row) => sum + (row.metrics[0] ?? 0), 0
  );

  let suggestedSensitivity: "low" | "medium" | "high" | "essentially_off";
  let isAnomaly = false;

  if (totalRequests > HIGH_TRAFFIC_RPS_THRESHOLD) {
    suggestedSensitivity = "high";
    isAnomaly = true;
  } else if (totalRequests > NORMAL_TRAFFIC_RPS_THRESHOLD) {
    suggestedSensitivity = "medium";
    isAnomaly = false;
  } else {
    suggestedSensitivity = "essentially_off";
    isAnomaly = false;
  }

  return { currentRPM: totalRequests, isAnomaly, suggestedSensitivity };
}

// Write a custom traffic metric from any Worker for ingestion:
export function writeTrafficMetric(ae: AnalyticsEngineDataset, endpoint: string, statusCode: number) {
  ae.writeDataPoint({
    blobs: [endpoint, String(statusCode)],
    doubles: [1],
    indexes: [endpoint],
  });
}
```

---

## Section 3: Adjust DDoS Managed Ruleset Sensitivity via Rulesets API

```typescript
// src/ruleset-manager.ts

const CF_API = "https://api.cloudflare.com/client/v4";

// Cloudflare managed DDoS ruleset IDs (these are global, not account-specific)
const HTTP_DDOS_RULESET_ID = "4d21379b4f9f4bb088e0729962c8b3cf"; // cf.http.dos_mitigation

interface RulesetOverride {
  sensitivity_level: "essentially_off" | "low" | "medium" | "high";
  action: "block" | "challenge" | "js_challenge" | "log";
}

interface ZoneRuleset {
  id: string;
  phase: string;
  rules: Array<{
    id: string;
    action: string;
    action_parameters?: {
      overrides?: {
        sensitivity_level?: string;
        action?: string;
      };
    };
  }>;
}

export async function setDDoSSensitivity(
  zoneId: string,
  apiToken: string,
  override: RulesetOverride
): Promise<void> {
  // Step 1: Get the current ddos_l7 phase ruleset for the zone
  const getRes = await fetch(
    `${CF_API}/zones/${zoneId}/rulesets/phases/ddos_l7/entrypoint`,
    { headers: { Authorization: `Bearer ${apiToken}` } }
  );

  if (!getRes.ok) {
    throw new Error(`Failed to fetch zone ruleset: ${await getRes.text()}`);
  }

  const currentRuleset = await getRes.json() as { result: ZoneRuleset };
  const rulesetId = currentRuleset.result.id;

  // Step 2: Find the existing override rule for the HTTP DDoS managed ruleset
  const existingRules = currentRuleset.result.rules ?? [];
  const overrideRule = existingRules.find(
    (r) => r.action === "execute" &&
    r.action_parameters?.overrides !== undefined
  );

  // Step 3: PUT the updated ruleset with the new sensitivity override
  const rules = [
    {
      action: "execute",
      expression: "true",
      description: "Auto-tuned DDoS sensitivity override",
      action_parameters: {
        id: HTTP_DDOS_RULESET_ID,
        overrides: {
          sensitivity_level: override.sensitivity_level,
          action: override.action,
        },
      },
    },
  ];

  const putRes = await fetch(
    `${CF_API}/zones/${zoneId}/rulesets/${rulesetId}`,
    {
      method: "PUT",
      headers: {
        Authorization: `Bearer ${apiToken}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ rules }),
    }
  );

  if (!putRes.ok) {
    throw new Error(`Failed to update ruleset: ${await putRes.text()}`);
  }

  console.log(
    `DDoS sensitivity set to ${override.sensitivity_level} / action: ${override.action}`
  );
}
```

---

## Section 4: Scheduled Worker Entry Point

```typescript
// src/index.ts

import { queryTrafficAnomaly, type Env } from "./analytics";
import { setDDoSSensitivity } from "./ruleset-manager";

export default {
  // Cron trigger handler
  async scheduled(event: ScheduledEvent, env: Env, ctx: ExecutionContext): Promise<void> {
    console.log(`DDoS auto-tuner running at ${new Date().toISOString()}`);

    const { currentRPM, isAnomaly, suggestedSensitivity } =
      await queryTrafficAnomaly(env);

    console.log(`Current RPM: ${currentRPM}, Anomaly: ${isAnomaly}, Suggested: ${suggestedSensitivity}`);

    // Only update ruleset if sensitivity change is warranted
    if (isAnomaly) {
      await setDDoSSensitivity(env.ZONE_ID, env.CF_API_TOKEN, {
        sensitivity_level: suggestedSensitivity,
        action: "block",
      });
    } else {
      // Relax back to normal during low traffic
      await setDDoSSensitivity(env.ZONE_ID, env.CF_API_TOKEN, {
        sensitivity_level: "medium",
        action: "block",
      });
    }
  },

  // Optional: HTTP handler for manual trigger
  async fetch(request: Request, env: Env): Promise<Response> {
    if (request.method !== "POST") return new Response("POST only", { status: 405 });
    await this.scheduled({} as ScheduledEvent, env, {} as ExecutionContext);
    return new Response("Triggered", { status: 200 });
  },
} satisfies ExportedHandler<Env>;
```

---

## Anti-patterns

- Do not set sensitivity to `essentially_off` in production — use `low` as the minimum floor to maintain basic DDoS protection.
- Do not call the Rulesets API on every request — use Cron Triggers with appropriate intervals to avoid rate limits.
- Do not use an account-level API token with all permissions; scope the token to `Zone:Firewall Services:Edit` only.
- Do not bypass the GET + PUT flow with a PATCH assuming partial updates — the Rulesets API requires the full rules array on PUT.

## Gotchas

- The `ddos_l7` phase entrypoint ruleset ID is zone-specific; always GET it before PUT.
- Analytics Engine SQL has eventual consistency — data may be 1-2 minutes behind real time.
- The Rulesets API `PUT /zones/<id>/rulesets/<id>` replaces all rules; preserve existing rules you did not intend to remove.
- Rate limits on the Rulesets API: max ~1200 requests/5min per token; the cron at `*/5 * * * *` is well within limits.
- `ScheduledEvent` does not have a `request` object — do not attempt to read request headers in the `scheduled()` handler.

## Verification

```bash
# Test cron trigger locally
wrangler dev --test-scheduled
# In another terminal:
curl -X POST "http://localhost:8787/__scheduled?cron=*%2F5+*+*+*+*"

# Check current zone ruleset phase
curl -s \
  "https://api.cloudflare.com/client/v4/zones/${ZONE_ID}/rulesets/phases/ddos_l7/entrypoint" \
  -H "Authorization: Bearer ${CF_API_TOKEN}" | jq '.result.rules[].action_parameters.overrides'

# Verify Analytics Engine dataset ingestion
curl -s -X POST \
  "https://api.cloudflare.com/client/v4/accounts/${CF_ACCOUNT_ID}/analytics_engine/sql" \
  -H "Authorization: Bearer ${CF_API_TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{"query": "SELECT count() FROM traffic_metrics WHERE timestamp > now() - INTERVAL 10 MINUTE"}' | jq .
```

## Related

- `documentation/categories/infra/workers-waiting-room-queue-bypass-kv.md`
- `documentation/categories/infra/workers-for-platforms-dispatch-namespace.md`

## Sources

- https://developers.cloudflare.com/ddos-protection/managed-rulesets/
- https://developers.cloudflare.com/ruleset-engine/rulesets-api/
- https://developers.cloudflare.com/analytics/analytics-engine/
- https://developers.cloudflare.com/workers/configuration/cron-triggers/
