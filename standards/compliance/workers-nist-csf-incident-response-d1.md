# NIST CSF Respond Function: Incident Detection and Containment with Workers and D1

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

The NIST Cybersecurity Framework (CSF) 2.0 Respond function requires organisations to detect anomalies, log incident details, execute containment actions, and notify stakeholders — all with documented, repeatable processes. Implementing these steps inside Cloudflare Workers gives you sub-millisecond containment (KV block-list) and a tamper-evident D1 incident log without managing any server infrastructure.

## Context

- Runtime: Cloudflare Workers (TypeScript)
- Durable incident log: Cloudflare D1
- Containment signal: Cloudflare KV (block-list)
- Notification: Cloudflare Queues (async email/PagerDuty)
- NIST CSF 2.0 functions covered: DE.AE (Anomaly detection), RS.AN (Incident analysis), RS.MI (Incident mitigation)

---

## Section 1: D1 Incident Log Schema

```sql
-- migrations/0002_incident_log.sql
CREATE TABLE IF NOT EXISTS incident_log (
  id            INTEGER PRIMARY KEY AUTOINCREMENT,
  detected_at   TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
  resolved_at   TEXT,
  severity      TEXT NOT NULL CHECK(severity IN ('LOW','MEDIUM','HIGH','CRITICAL')),
  category      TEXT NOT NULL,  -- ANOMALY | BRUTE_FORCE | DATA_EXFIL | ...
  source_ip     TEXT NOT NULL,
  user_id       TEXT,
  description   TEXT NOT NULL,
  containment   TEXT,           -- action taken
  status        TEXT NOT NULL DEFAULT 'OPEN' CHECK(status IN ('OPEN','CONTAINED','RESOLVED'))
);

CREATE INDEX IF NOT EXISTS idx_incident_status ON incident_log(status, detected_at);
```

```bash
npx wrangler d1 migrations apply INCIDENT_DB --remote
```

---

## Section 2: Anomaly Detection Middleware

Detect brute-force attempts by counting failed authentication events in a KV sliding window.

```typescript
// src/middleware/anomalyDetect.ts
import { Env } from '../types';

const THRESHOLD   = 10;   // failures before flagging
const WINDOW_SECS = 300;  // 5-minute window

export async function checkAnomalyThreshold(
  env: Env,
  ip: string
): Promise<{ blocked: boolean; count: number }> {
  const key   = `fail:${ip}`;
  const raw   = await env.BLOCK_KV.get(key);
  const count = raw ? parseInt(raw, 10) : 0;
  return { blocked: count >= THRESHOLD, count };
}

export async function recordFailure(
  env: Env,
  ip: string
): Promise<number> {
  const key     = `fail:${ip}`;
  const raw     = await env.BLOCK_KV.get(key);
  const current = raw ? parseInt(raw, 10) : 0;
  const next    = current + 1;
  await env.BLOCK_KV.put(key, String(next), { expirationTtl: WINDOW_SECS });
  return next;
}

export async function clearFailures(env: Env, ip: string): Promise<void> {
  await env.BLOCK_KV.delete(`fail:${ip}`);
}
```

---

## Section 3: Incident Creation and Containment

```typescript
// src/incident/createIncident.ts
import { Env } from '../types';

export interface IncidentPayload {
  severity: 'LOW' | 'MEDIUM' | 'HIGH' | 'CRITICAL';
  category: string;
  source_ip: string;
  user_id?: string;
  description: string;
  containment?: string;
}

export async function createIncident(
  env: Env,
  payload: IncidentPayload
): Promise<number> {
  const result = await env.INCIDENT_DB
    .prepare(
      `INSERT INTO incident_log
         (severity, category, source_ip, user_id, description, containment)
       VALUES (?, ?, ?, ?, ?, ?)`
    )
    .bind(
      payload.severity,
      payload.category,
      payload.source_ip,
      payload.user_id ?? null,
      payload.description,
      payload.containment ?? null
    )
    .run();

  return result.meta.last_row_id as number;
}

// Automated containment: add IP to KV block-list with a 24h TTL
export async function containByBlockingIP(
  env: Env,
  ip: string,
  incidentId: number
): Promise<void> {
  await env.BLOCK_KV.put(
    `block:${ip}`,
    JSON.stringify({ incidentId, blockedAt: new Date().toISOString() }),
    { expirationTtl: 86_400 }   // 24 hours
  );
}
```

---

## Section 4: Notification Queue

```typescript
// src/incident/notify.ts
import { Env } from '../types';

export interface IncidentAlert {
  incidentId: number;
  severity: string;
  category: string;
  source_ip: string;
  description: string;
  detectedAt: string;
}

export async function enqueueAlert(
  env: Env,
  alert: IncidentAlert
): Promise<void> {
  await env.INCIDENT_QUEUE.send(alert);
}

// Queue consumer (separate Worker or same Worker with queue handler)
export async function handleAlertQueue(
  batch: MessageBatch<IncidentAlert>,
  env: Env
): Promise<void> {
  for (const msg of batch.messages) {
    const a = msg.body;
    // Replace with your notification provider (PagerDuty, Slack, etc.)
    await fetch('https://events.pagerduty.com/v2/enqueue', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Token token=${env.PAGERDUTY_KEY}`,
      },
      body: JSON.stringify({
        routing_key: env.PAGERDUTY_ROUTING_KEY,
        event_action: 'trigger',
        payload: {
          summary:   `[${a.severity}] ${a.category} from ${a.source_ip}`,
          source:    'cloudflare-workers',
          severity:  a.severity.toLowerCase(),
          custom_details: a,
        },
      }),
    });
    msg.ack();
  }
}
```

---

## Section 5: Main Fetch Handler Integration

```typescript
// src/index.ts
import { checkAnomalyThreshold, recordFailure } from './middleware/anomalyDetect';
import { containByBlockingIP, createIncident } from './incident/createIncident';
import { enqueueAlert } from './incident/notify';
import { Env } from './types';

export default {
  async fetch(req: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    const ip = req.headers.get('CF-Connecting-IP') ?? '0.0.0.0';

    // 1. Check KV block-list (containment gate)
    const blocked = await env.BLOCK_KV.get(`block:${ip}`);
    if (blocked) {
      return new Response('Forbidden', { status: 403 });
    }

    const response = await routeRequest(req, env, ctx);

    // 2. On auth failure, update anomaly counter
    if (response.status === 401) {
      const count = await recordFailure(env, ip);
      if (count >= 10) {
        const id = await createIncident(env, {
          severity: 'HIGH',
          category: 'BRUTE_FORCE',
          source_ip: ip,
          description: `${count} failed auth attempts in 5 min window`,
          containment: 'IP blocked via KV for 24h',
        });
        ctx.waitUntil(Promise.all([
          containByBlockingIP(env, ip, id),
          enqueueAlert(env, {
            incidentId: id,
            severity: 'HIGH',
            category: 'BRUTE_FORCE',
            source_ip: ip,
            description: `Brute force detected: ${count} failures`,
            detectedAt: new Date().toISOString(),
          }),
        ]));
      }
    }

    return response;
  },

  async queue(batch: MessageBatch, env: Env) {
    await handleAlertQueue(batch as MessageBatch<IncidentAlert>, env);
  },
};

async function routeRequest(req: Request, env: Env, _ctx: ExecutionContext): Promise<Response> {
  // your existing routing logic
  return new Response('OK');
}
```

---

## Anti-patterns

- Blocking synchronously in the request path — always use `ctx.waitUntil` for D1 writes.
- Storing block-list entries in D1 instead of KV — KV reads are faster and better suited for the hot path.
- Not acknowledging queue messages (`msg.ack()`) — causes infinite redelivery.
- Using a fixed timestamp rather than `strftime('now')` in D1 inserts — clock skew is your enemy in audit trails.
- Setting block-list TTL to 0 (permanent) without a manual review process.

## Gotchas

- KV `get()` returns `null` (not `undefined`) for missing keys; always null-check.
- D1 `last_row_id` is returned as a number in the meta object, but TypeScript types it as `unknown` — cast explicitly.
- Queue messages are batched; if your notification provider rate-limits, add exponential back-off inside the consumer.
- `CF-Connecting-IP` is IPv6-normalised by Cloudflare; store in TEXT without assuming IPv4 format.

---

## Verification

```bash
# Simulate 11 failed auths and check block-list
for i in $(seq 1 11); do
  curl -s -o /dev/null -w "%{http_code}\n" \
    -H "CF-Connecting-IP: 10.0.0.1" \
    https://api.example.com/auth
done

# Should return 403 now
curl -s -o /dev/null -w "%{http_code}\n" \
  -H "CF-Connecting-IP: 10.0.0.1" \
  https://api.example.com/api/data

# Check incident log
npx wrangler d1 execute INCIDENT_DB --remote \
  --command "SELECT * FROM incident_log ORDER BY id DESC LIMIT 5;"

# Check KV block entry
npx wrangler kv key get --binding=BLOCK_KV 'block:10.0.0.1' --remote
```

---

## Related

- `documentation/categories/compliance/workers-iso-27001-access-log-d1.md`
- `documentation/categories/compliance/workers-glba-financial-safeguards-encryption.md`
- `documentation/workers/kv-rate-limiting.md`

## Sources

- https://www.nist.gov/cyberframework (NIST CSF 2.0)
- https://developers.cloudflare.com/queues/
- https://developers.cloudflare.com/kv/
- https://developers.cloudflare.com/d1/
