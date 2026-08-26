# PII Redaction in Tail Workers

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

Console logs in production Workers sometimes contain personally identifiable information — email addresses, credit-card numbers, SSNs — accidentally emitted during debugging or error formatting. Before forwarding logs to Logpush (or any external SIEM), you must strip PII to comply with GDPR, PCI-DSS, and HIPAA requirements. A Tail Worker is the ideal interception point: it sees all log lines before they leave Cloudflare, and the redaction logic runs inside Cloudflare's network.

## Context

A Tail Worker consumes `TailEvent` objects. Each event contains an array of log entries (`console.log`, `console.error`, etc.) as `TailItem.logs`. The redaction Worker applies regex patterns to each log line, replaces matches with a placeholder, then forwards the sanitised payload to a Logpush-compatible HTTP sink. Redaction events (service, timestamp, count of redactions) are persisted in D1 for audit purposes.

---

## Section 1 — PII regex patterns

```typescript
// redactor/src/patterns.ts

export interface RedactionPattern {
  name:        string;
  pattern:     RegExp;
  replacement: string;
}

export const PII_PATTERNS: RedactionPattern[] = [
  {
    name:        'email',
    pattern:     /[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}/g,
    replacement: '[REDACTED-EMAIL]',
  },
  {
    // Visa / Mastercard / Amex 13-16 digit PANs with optional spaces/dashes
    name:        'credit-card',
    pattern:     /\b(?:\d[ \-]?){13,16}\b/g,
    replacement: '[REDACTED-CARD]',
  },
  {
    // US SSN: 3-2-4 digit groups with hyphens or spaces
    name:        'ssn',
    pattern:     /\b(?!000|666|9\d{2})\d{3}[- ](?!00)\d{2}[- ](?!0{4})\d{4}\b/g,
    replacement: '[REDACTED-SSN]',
  },
  {
    // US phone numbers in common formats
    name:        'phone-us',
    pattern:     /\b(?:\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b/g,
    replacement: '[REDACTED-PHONE]',
  },
  {
    // IPv4 addresses (may be PII when tied to a user session)
    name:        'ipv4',
    pattern:     /\b(?:\d{1,3}\.){3}\d{1,3}\b/g,
    replacement: '[REDACTED-IP]',
  },
];

export interface RedactionResult {
  text:         string;
  count:        number;
  typesMatched: string[];
}

export function redact(input: string): RedactionResult {
  let text = input;
  let count = 0;
  const typesMatched: string[] = [];

  for (const { name, pattern, replacement } of PII_PATTERNS) {
    const before = text;
    text = text.replace(pattern, replacement);
    if (text !== before) {
      const matches = (before.match(pattern) ?? []).length;
      count += matches;
      typesMatched.push(name);
    }
  }

  return { text, count, typesMatched };
}
```

## Section 2 — Tail Worker entrypoint

```typescript
// redactor/src/index.ts
import type { TailEvent, TailItem } from '@cloudflare/workers-types';
import { redact } from './patterns';
import { auditRedactions } from './audit';

export interface Env {
  AUDIT_DB:      D1Database;
  LOGPUSH_URL:   string;   // HTTP sink URL
  LOGPUSH_TOKEN: string;   // Bearer token for the sink
}

export default {
  async tail(events: TailEvent[], env: Env, ctx: ExecutionContext): Promise<void> {
    const sanitised: object[] = [];
    const auditRows: Array<{ service: string; ts: number; count: number; types: string }> = [];

    for (const event of events) {
      for (const item of event) {
        const { cleanItem, redactionCount, typesMatched } = sanitiseItem(item);
        sanitised.push(cleanItem);

        if (redactionCount > 0) {
          auditRows.push({
            service: item.scriptName ?? 'unknown',
            ts:      item.timestamp ?? Date.now(),
            count:   redactionCount,
            types:   typesMatched.join(','),
          });
        }
      }
    }

    ctx.waitUntil(Promise.all([
      forwardToLogpush(sanitised, env),
      auditRedactions(auditRows, env),
    ]));
  },
};

function sanitiseItem(item: TailItem): {
  cleanItem: object;
  redactionCount: number;
  typesMatched: string[];
} {
  let redactionCount = 0;
  const allTypes = new Set<string>();

  const cleanLogs = (item.logs ?? []).map((log) => {
    const cleanMessages = (log.message ?? []).map((msg) => {
      const str = typeof msg === 'string' ? msg : JSON.stringify(msg);
      const result = redact(str);
      redactionCount += result.count;
      result.typesMatched.forEach((t) => allTypes.add(t));
      return result.text;
    });
    return { ...log, message: cleanMessages };
  });

  // Also redact exception messages and stack traces
  const cleanExceptions = (item.exceptions ?? []).map((ex) => {
    const result = redact(ex.message ?? '');
    redactionCount += result.count;
    result.typesMatched.forEach((t) => allTypes.add(t));
    return { ...ex, message: result.text };
  });

  return {
    cleanItem: { ...item, logs: cleanLogs, exceptions: cleanExceptions },
    redactionCount,
    typesMatched: [...allTypes],
  };
}

async function forwardToLogpush(items: object[], env: Env): Promise<void> {
  if (items.length === 0) return;

  const body = items.map((i) => JSON.stringify(i)).join('\n');

  const res = await fetch(env.LOGPUSH_URL, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/x-ndjson',
      'Authorization': `Bearer ${env.LOGPUSH_TOKEN}`,
    },
    body,
  });

  if (!res.ok) {
    console.error(`Logpush forward failed: HTTP ${res.status}`);
  }
}
```

## Section 3 — D1 audit schema and writer

```sql
-- migrations/0001_redaction_audit.sql
CREATE TABLE IF NOT EXISTS redaction_events (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  service     TEXT    NOT NULL,
  event_ts    INTEGER NOT NULL,
  count       INTEGER NOT NULL,
  types       TEXT    NOT NULL,  -- CSV of matched PII types
  recorded_at INTEGER DEFAULT (unixepoch() * 1000)
);

CREATE INDEX idx_re_service ON redaction_events(service, event_ts DESC);
CREATE INDEX idx_re_ts      ON redaction_events(event_ts DESC);
```

```typescript
// redactor/src/audit.ts
import type { Env } from './index';

export async function auditRedactions(
  rows: Array<{ service: string; ts: number; count: number; types: string }>,
  env: Env
): Promise<void> {
  if (rows.length === 0) return;

  const stmt = env.AUDIT_DB.prepare(
    `INSERT INTO redaction_events (service, event_ts, count, types)
     VALUES (?, ?, ?, ?)`
  );

  const batch = rows.map((r) => stmt.bind(r.service, r.ts, r.count, r.types));
  await env.AUDIT_DB.batch(batch);
}
```

## Section 4 — wrangler.toml

```toml
# redactor/wrangler.toml
name = "log-redactor"
main = "src/index.ts"
compatibility_date = "2025-10-01"

tail_consumers = []  # This Worker IS the tail consumer; target is set on the origin

[[d1_databases]]
binding       = "AUDIT_DB"
database_name = "redaction-audit"
database_id   = "<your-d1-id>"

[vars]
LOGPUSH_URL = "https://your-logpush-sink.example.com/ingest"
# LOGPUSH_TOKEN is set as a secret
```

```bash
# Set the Logpush token as a secret
wrangler secret put LOGPUSH_TOKEN

# Deploy
wrangler deploy --config redactor/wrangler.toml

# Apply migration
wrangler d1 migrations apply redaction-audit --remote

# Wire up as tail consumer of the origin Worker (replace my-api)
wrangler tail my-api --format json  # verify raw events before redaction

# Query audit table for recent redactions
wrangler d1 execute redaction-audit --remote \
  --command "SELECT service, count, types, datetime(recorded_at/1000,'unixepoch') AS at FROM redaction_events ORDER BY at DESC LIMIT 20;"
```

## Anti-patterns

- **Redacting in the origin Worker before logging** — increases latency on the hot path and risks missed patterns when developers add new log statements. Centralise redaction in the Tail Worker.
- **Using `.replace()` without the `g` flag** — only the first match is replaced. Always use the `g` flag or a `replaceAll()` equivalent.
- **Logging the original PII-containing message in the Tail Worker's own console** — Tail Workers can themselves be tailed. If you `console.log(originalMessage)` for debugging, you'll re-expose PII in a nested tail.
- **Storing redaction counts without types** — a count of 3 is not actionable. Record which PII types were matched for compliance reporting.

## Gotchas

- `TailItem.logs[].message` is typed as `unknown[]`, not `string[]`. Serialise non-string values with `JSON.stringify` before applying regex.
- Regex patterns for credit cards have high false-positive rates (any 13-16 digit sequence). Tune patterns to your data format; consider Luhn-check validation for production use.
- The `g` flag on a shared regex retains `lastIndex` state between calls when used with `.exec()`. Prefer `.replace()` or reset `lastIndex = 0` between uses. The patterns above use `.replace()` so this is safe.
- D1 `batch()` has a maximum of 100 statements per call. For high-volume Workers, chunk `auditRows` into batches of 100.

## Verification

```bash
# Test the redact function locally with a unit test runner
cat > /tmp/test-redact.ts << 'EOF'
import { redact } from './src/patterns';

const cases = [
  { input: 'Contact alice@example.com for info', want: '[REDACTED-EMAIL]' },
  { input: 'Card: 4111 1111 1111 1111', want: '[REDACTED-CARD]' },
  { input: 'SSN 123-45-6789 on file', want: '[REDACTED-SSN]' },
];

for (const c of cases) {
  const { text } = redact(c.input);
  console.assert(text.includes(c.want), `FAIL: ${c.input} -> ${text}`);
  console.log(`PASS: ${c.input} -> ${text}`);
}
EOF
npx ts-node /tmp/test-redact.ts

# Check audit table after sending logs from origin Worker
wrangler d1 execute redaction-audit --remote \
  --command "SELECT COUNT(*) as total_events, SUM(count) as total_redactions FROM redaction_events;"
```

## Related

- `workers-tail-worker-request-sampling.md` — selective log capture via Tail Workers
- `workers-dead-man-switch-cron-alert.md` — proactive alerting pattern
- Cloudflare Tail Workers: https://developers.cloudflare.com/workers/observability/tail-workers/
- Logpush HTTP destination: https://developers.cloudflare.com/logs/get-started/enable-destinations/http/

## Sources

- https://developers.cloudflare.com/workers/observability/tail-workers/
- https://developers.cloudflare.com/logs/get-started/enable-destinations/http/
- https://gdpr.eu/what-is-gdpr/
- https://www.pcisecuritystandards.org/
