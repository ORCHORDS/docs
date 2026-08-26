# Email Header Anomaly Detection in Workers

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case
Inbound email contains spoofed `From` addresses, suspicious `X-` headers injected by compromised relays, or unusual `Received` chain hops that suggest phishing.
A Cloudflare Workers Email handler can inspect all headers before forwarding and reject or quarantine anomalous messages.

## Context
Cloudflare Email Routing exposes a `message.headers` iterable on the `EmailMessage` object, giving access to every header before the message body is processed.
Anomaly rules are stored in KV as JSON so they can be updated without redeployment.
Flagged messages are stored in R2 as `.eml` files for forensic review rather than silently dropped.

---

## Architecture / Setup

```typescript
// wrangler.toml bindings (excerpt)
// kv_namespaces = [{ binding = "ANOMALY_RULES_KV", id = "..." }]
// r2_buckets    = [{ binding = "QUARANTINE_R2",    bucket_name = "email-quarantine" }]
// email = { binding = "FORWARD_TO", destination_address = "inbox@example.com" }

export interface Env {
  ANOMALY_RULES_KV: KVNamespace;
  QUARANTINE_R2: R2Bucket;
  ANALYTICS: AnalyticsEngineDataset;
  FORWARD_ADDRESS: string;   // set as plain-text secret or env var
}
```

## Rule Definition Schema (stored in KV)

```typescript
// Key: "anomaly_rules:v1"
// Value: JSON array of AnomalyRule
interface AnomalyRule {
  id: string;
  description: string;
  // header name to inspect (case-insensitive)
  header: string;
  // one of: "present" | "absent" | "regex" | "value_not_in"
  condition: 'present' | 'absent' | 'regex' | 'value_not_in';
  // used for "regex" and "value_not_in"
  pattern?: string;
  allowed?: string[];
  // "reject" | "quarantine" | "tag"
  action: 'reject' | 'quarantine' | 'tag';
  severity: 'low' | 'medium' | 'high';
}

// Example rules payload pushed to KV:
const EXAMPLE_RULES: AnomalyRule[] = [
  {
    id: 'no-message-id',
    description: 'Legitimate mail always carries a Message-ID',
    header: 'message-id',
    condition: 'absent',
    action: 'quarantine',
    severity: 'medium',
  },
  {
    id: 'forged-reply-to-domain',
    description: 'Reply-To domain differs from envelope From domain — common phishing signal',
    header: 'reply-to',
    condition: 'regex',
    pattern: '@(?!orchords\\.com|trusted-partner\\.com)',
    action: 'tag',
    severity: 'low',
  },
  {
    id: 'suspicious-x-mailer',
    description: 'X-Mailer values associated with spam toolkits',
    header: 'x-mailer',
    condition: 'value_not_in',
    allowed: ['Apple Mail', 'Outlook', 'Thunderbird', 'Gmail'],
    action: 'tag',
    severity: 'low',
  },
  {
    id: 'malformed-date',
    description: 'Date header missing or non-RFC-2822 — forged mail often omits it',
    header: 'date',
    condition: 'absent',
    action: 'quarantine',
    severity: 'high',
  },
  {
    id: 'too-many-received-hops',
    description: 'More than 15 Received headers suggests relay abuse or routing loops',
    header: 'received',
    condition: 'regex',
    // We count occurrences in the handler instead; this entry is a sentinel
    pattern: '__count_gt_15__',
    action: 'quarantine',
    severity: 'high',
  },
];
```

## Email Handler — Header Inspection Engine

```typescript
// src/email-handler.ts
import { EmailMessage } from 'cloudflare:email';

export default {
  async email(message: EmailMessage, env: Env, ctx: ExecutionContext) {
    const rules: AnomalyRule[] = await loadRules(env);

    // Collect all headers into a normalised map
    const headerMap = new Map<string, string[]>();
    for (const [name, value] of message.headers) {
      const key = name.toLowerCase();
      const existing = headerMap.get(key) ?? [];
      existing.push(value);
      headerMap.set(key, existing);
    }

    const findings: Array<{ rule: AnomalyRule; detail: string }> = [];

    for (const rule of rules) {
      const values = headerMap.get(rule.header.toLowerCase()) ?? [];

      let triggered = false;
      let detail = '';

      switch (rule.condition) {
        case 'absent':
          triggered = values.length === 0;
          detail = `Header "${rule.header}" is absent`;
          break;

        case 'present':
          triggered = values.length > 0;
          detail = `Header "${rule.header}" is present: ${values[0]}`;
          break;

        case 'regex': {
          if (rule.pattern === '__count_gt_15__') {
            // Special sentinel — count Received headers
            const count = (headerMap.get('received') ?? []).length;
            triggered = count > 15;
            detail = `Received hop count: ${count}`;
          } else {
            const re = new RegExp(rule.pattern!, 'i');
            const match = values.find((v) => re.test(v));
            triggered = match !== undefined;
            detail = `Header "${rule.header}" matched /${rule.pattern}/: ${match}`;
          }
          break;
        }

        case 'value_not_in': {
          const allowed = rule.allowed ?? [];
          const bad = values.find(
            (v) => !allowed.some((a) => v.toLowerCase().includes(a.toLowerCase()))
          );
          triggered = bad !== undefined;
          detail = `Header "${rule.header}" value not in allowlist: ${bad}`;
          break;
        }
      }

      if (triggered) {
        findings.push({ rule, detail });

        // Emit to Analytics Engine for dashboarding
        env.ANALYTICS.writeDataPoint({
          blobs: [rule.id, rule.severity, message.from, detail],
          doubles: [1],
          indexes: [rule.id],
        });
      }
    }

    // Determine worst action across all findings
    const actionPriority = { reject: 3, quarantine: 2, tag: 1 };
    const worstAction = findings.reduce<AnomalyRule['action'] | null>(
      (acc, { rule }) =>
        acc === null || actionPriority[rule.action] > actionPriority[acc!]
          ? rule.action
          : acc,
      null
    );

    if (worstAction === 'reject') {
      message.setReject('Message rejected: header anomaly detected');
      return;
    }

    if (worstAction === 'quarantine') {
      await quarantineMessage(message, findings, env);
      return;   // Do not forward
    }

    // "tag" — add X-Anomaly-Flags header and forward
    // Note: Workers Email does not support header mutation before forward.
    // Instead log findings and forward; the downstream system reads KV for context.
    if (findings.length > 0) {
      const flagKey = `anomaly:${message.headers.get('message-id') ?? Date.now()}`;
      await env.ANOMALY_RULES_KV.put(
        flagKey,
        JSON.stringify(findings.map((f) => ({ id: f.rule.id, detail: f.detail }))),
        { expirationTtl: 86_400 * 7 }
      );
    }

    await message.forward('inbox@example.com');
  },
};

async function loadRules(env: Env): Promise<AnomalyRule[]> {
  const raw = await env.ANOMALY_RULES_KV.get('anomaly_rules:v1');
  if (!raw) return [];
  try {
    return JSON.parse(raw) as AnomalyRule[];
  } catch {
    return [];
  }
}

async function quarantineMessage(
  message: EmailMessage,
  findings: Array<{ rule: AnomalyRule; detail: string }>,
  env: Env
): Promise<void> {
  const msgId = (message.headers.get('message-id') ?? Date.now().toString())
    .replace(/[<>\s]/g, '');
  const key = `quarantine/${new Date().toISOString().slice(0, 10)}/${msgId}.json`;

  const payload = {
    from: message.from,
    to: message.to,
    receivedAt: new Date().toISOString(),
    findings: findings.map((f) => ({ ruleId: f.rule.id, severity: f.rule.severity, detail: f.detail })),
  };

  await env.QUARANTINE_R2.put(key, JSON.stringify(payload), {
    httpMetadata: { contentType: 'application/json' },
  });
}
```

## Anti-patterns
- Running heavy regex against the full body in the email handler — header inspection only; body scanning belongs in a queue consumer.
- Hard-coding rules in source code — store in KV so security teams can push updates without a Wrangler deploy.
- Silently dropping messages on `quarantine` action — always write to R2 or send an alert; silent drops obscure false-positive rates.
- Trusting `Authentication-Results` headers added upstream — an adversary-controlled MTA can forge them; use DMARC/DKIM verification instead.
- Using overly broad regex patterns that flag legitimate bulk mailers — start with `tag` severity and promote to `quarantine` only after calibration.

## Gotchas
- `message.headers` is iterable but not a plain `Map`; the same header name can appear multiple times (e.g., `Received`) — collect into an array, not a scalar.
- `message.setReject()` must be called synchronously in the same microtask tick as the handler start — do not await anything before a reject if possible.
- Workers Email handlers have a 30-second wall clock limit; keep rule evaluation O(n) in rule count, not O(n²).
- `AnalyticsEngineDataset.writeDataPoint` is fire-and-forget but must be called before the handler returns; wrap in `ctx.waitUntil` if after an `await`.
- R2 key names containing angle brackets or spaces cause 400 errors — sanitize `Message-ID` values before using as keys.

## Verification

```bash
# Push initial ruleset to KV
wrangler kv key put --binding ANOMALY_RULES_KV "anomaly_rules:v1" \
  "$(cat rules.json)" --remote

# Check quarantine bucket for flagged messages
wrangler r2 object list email-quarantine --prefix quarantine/ --remote

# Query Analytics Engine (Cloudflare dashboard SQL)
# SELECT blob1 AS rule_id, blob2 AS severity, count() AS hits
# FROM anomaly_email_events
# WHERE timestamp > NOW() - INTERVAL '7' DAY
# GROUP BY rule_id, severity
# ORDER BY hits DESC
```

## Related
- `workers-inbound-email-spam-filtering-custom-rules.md` — content-based spam filtering
- `email-dnsbl-realtime-blacklist-check-workers.md` — IP reputation checks at inbound
- `email-authentication-check-tools.md` — DKIM/SPF/DMARC verification tooling
- `email-security-audit-trail-d1-immutable-log.md` — immutable log of inbound events
- `email-header-injection-security.md` — preventing header injection in outbound

## Sources
- https://developers.cloudflare.com/email-routing/email-workers/
- https://developers.cloudflare.com/kv/
- https://developers.cloudflare.com/r2/
- https://developers.cloudflare.com/analytics/analytics-engine/
- https://datatracker.ietf.org/doc/html/rfc5322 (Internet Message Format)
