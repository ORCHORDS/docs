# Locale-Aware Webhook Payload Localization in Workers

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

Your platform sends a webhook event to a partner's endpoint whenever an invoice
is settled. The payload includes `amount: 1234.56`, `currency: "EUR"`, and
`settled_at: "2024-08-15T10:30:00Z"`. The German partner's ERP system expects
`1.234,56` (European decimal notation) and the date as `15.08.2024`. The
Brazilian partner expects `1.234,56` and `15/08/2024`. The US partner needs
`1,234.56` and `08/15/2024`. Sending a one-size-fits-all ISO payload causes
ingestion errors or silent mis-parsing on the receiver side.

---

## Context

Webhook payloads are a form of machine-to-machine communication, but when the
consuming system is a legacy ERP, a data warehouse with locale-sensitive import
rules, or an accounting tool that displays raw payload values in its UI, the
locale of the *receiver* matters as much as for a human-facing interface.

The correct approach depends on what the consumer needs:

- **ISO-only consumers** (most modern APIs): always send machine-readable ISO
  8601 dates and numeric strings like `"1234.56"`. The locale layer is the
  consumer's responsibility.
- **Legacy or locale-sensitive consumers**: deliver pre-formatted strings
  alongside (or instead of) the canonical values, keyed to the subscriber's
  registered locale.
- **Hybrid**: send canonical fields (`amount_raw`, `settled_at_iso`) plus
  formatted display fields (`amount_display`, `settled_at_display`), controlled
  per subscriber.

This article covers the hybrid approach with a Workers Queues fan-out pattern.

---

## Subscriber Locale Registry in D1

```sql
-- migrations/0001_webhook_subscribers.sql
CREATE TABLE webhook_subscribers (
  id          TEXT PRIMARY KEY,
  endpoint    TEXT NOT NULL,
  secret      TEXT NOT NULL,        -- HMAC signing secret
  locale      TEXT NOT NULL DEFAULT 'en-US',  -- BCP 47
  date_format TEXT NOT NULL DEFAULT 'ISO8601', -- ISO8601 | DMY_SLASH | MDY_SLASH | DMY_DOT | YMD_SLASH
  payload_mode TEXT NOT NULL DEFAULT 'canonical', -- canonical | display | hybrid
  created_at  TEXT NOT NULL
);
```

---

## Payload Formatter

```typescript
// src/lib/webhook-formatter.ts

export type PayloadMode = 'canonical' | 'display' | 'hybrid';
export type DateFmt = 'ISO8601' | 'DMY_SLASH' | 'MDY_SLASH' | 'DMY_DOT' | 'YMD_SLASH';

export interface SubscriberConfig {
  locale: string;
  dateFormat: DateFmt;
  payloadMode: PayloadMode;
}

export interface InvoiceEvent {
  invoiceId: string;
  amount: number;         // raw float in major units
  currency: string;       // ISO 4217
  settledAt: Date;        // UTC
}

export interface WebhookPayload {
  event: 'invoice.settled';
  invoice_id: string;
  // Canonical fields (always present in hybrid/canonical)
  amount_raw?: number;
  currency?: string;
  settled_at_iso?: string;
  // Display fields (always present in hybrid/display)
  amount_display?: string;
  settled_at_display?: string;
}

function formatDate(d: Date, fmt: DateFmt, locale: string): string {
  if (fmt === 'ISO8601') return d.toISOString().slice(0, 10);

  const y = d.getUTCFullYear();
  const m = String(d.getUTCMonth() + 1).padStart(2, '0');
  const day = String(d.getUTCDate()).padStart(2, '0');

  switch (fmt) {
    case 'DMY_SLASH': return `${day}/${m}/${y}`;
    case 'MDY_SLASH': return `${m}/${day}/${y}`;
    case 'DMY_DOT':   return `${day}.${m}.${y}`;
    case 'YMD_SLASH': return `${y}/${m}/${day}`;
    default:          return d.toISOString().slice(0, 10);
  }
}

function formatCurrency(amount: number, currency: string, locale: string): string {
  return new Intl.NumberFormat(locale, {
    style: 'currency',
    currency,
    // Let Intl derive minimumFractionDigits from currency defaults
  }).format(amount);
}

export function buildPayload(
  event: InvoiceEvent,
  subscriber: SubscriberConfig
): WebhookPayload {
  const { locale, dateFormat, payloadMode } = subscriber;

  const base: WebhookPayload = {
    event: 'invoice.settled',
    invoice_id: event.invoiceId,
  };

  if (payloadMode === 'canonical' || payloadMode === 'hybrid') {
    base.amount_raw = event.amount;
    base.currency = event.currency;
    base.settled_at_iso = event.settledAt.toISOString();
  }

  if (payloadMode === 'display' || payloadMode === 'hybrid') {
    base.amount_display = formatCurrency(event.amount, event.currency, locale);
    base.settled_at_display = formatDate(event.settledAt, dateFormat, locale);
  }

  return base;
}
```

---

## HMAC Signature Helper

Webhook receivers must verify authenticity. Sign the serialized payload body
with the subscriber's secret.

```typescript
// src/lib/webhook-sign.ts

export async function signPayload(
  body: string,
  secret: string,
  timestampSeconds: number
): Promise<string> {
  const encoder = new TextEncoder();
  const signingInput = `${timestampSeconds}.${body}`;
  const keyMaterial = await crypto.subtle.importKey(
    'raw',
    encoder.encode(secret),
    { name: 'HMAC', hash: 'SHA-256' },
    false,
    ['sign']
  );
  const sig = await crypto.subtle.sign('HMAC', keyMaterial, encoder.encode(signingInput));
  const hex = Array.from(new Uint8Array(sig))
    .map(b => b.toString(16).padStart(2, '0'))
    .join('');
  return `t=${timestampSeconds},v1=${hex}`;
}
```

---

## Workers Queue Fan-out

```typescript
// src/workers/webhook-dispatcher.ts
import { buildPayload } from '../lib/webhook-formatter';
import { signPayload } from '../lib/webhook-sign';

export interface Env {
  DB: D1Database;
  WEBHOOK_QUEUE: Queue<InvoiceEvent>;
}

interface InvoiceEvent {
  invoiceId: string;
  amount: number;
  currency: string;
  settledAt: string; // ISO string — queues serialize dates
}

interface SubscriberRow {
  id: string;
  endpoint: string;
  secret: string;
  locale: string;
  date_format: string;
  payload_mode: string;
}

export default {
  // Entry point: accept an invoice settled event and fan out to all subscribers
  async queue(batch: MessageBatch<InvoiceEvent>, env: Env): Promise<void> {
    const subscribers = await env.DB
      .prepare('SELECT id, endpoint, secret, locale, date_format, payload_mode FROM webhook_subscribers')
      .all<SubscriberRow>();

    for (const message of batch.messages) {
      const ev = message.body;
      const eventObj = {
        ...ev,
        settledAt: new Date(ev.settledAt),
      };

      await Promise.allSettled(
        (subscribers.results ?? []).map(sub =>
          deliverWebhook(eventObj, sub)
        )
      );

      message.ack();
    }
  },
};

async function deliverWebhook(
  event: { invoiceId: string; amount: number; currency: string; settledAt: Date },
  sub: SubscriberRow
): Promise<void> {
  const payload = buildPayload(event, {
    locale: sub.locale,
    dateFormat: sub.date_format as any,
    payloadMode: sub.payload_mode as any,
  });

  const body = JSON.stringify(payload);
  const ts = Math.floor(Date.now() / 1000);
  const signature = await signPayload(body, sub.secret, ts);

  const response = await fetch(sub.endpoint, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'X-Webhook-Signature': signature,
      'X-Webhook-Timestamp': String(ts),
      'X-Subscriber-Locale': sub.locale,
    },
    body,
  });

  if (!response.ok) {
    console.error(`Webhook delivery failed for subscriber ${sub.id}: ${response.status}`);
    // Throw to trigger Workers Queue retry
    throw new Error(`HTTP ${response.status} from ${sub.endpoint}`);
  }
}
```

---

## Subscriber Registration Endpoint

```typescript
// src/workers/subscriber-register.ts
import type { Env } from './webhook-dispatcher';

const VALID_DATE_FORMATS = new Set(['ISO8601', 'DMY_SLASH', 'MDY_SLASH', 'DMY_DOT', 'YMD_SLASH']);
const VALID_MODES = new Set(['canonical', 'display', 'hybrid']);

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    if (request.method !== 'POST') return new Response('Method Not Allowed', { status: 405 });

    const body = await request.json<{
      endpoint: string;
      secret: string;
      locale?: string;
      date_format?: string;
      payload_mode?: string;
    }>();

    if (!body.endpoint || !body.secret) {
      return Response.json({ error: 'endpoint and secret are required' }, { status: 400 });
    }

    const dateFormat = body.date_format ?? 'ISO8601';
    const payloadMode = body.payload_mode ?? 'hybrid';
    const locale = body.locale ?? 'en-US';

    if (!VALID_DATE_FORMATS.has(dateFormat)) {
      return Response.json({ error: `Invalid date_format. Valid: ${[...VALID_DATE_FORMATS].join(', ')}` }, { status: 400 });
    }
    if (!VALID_MODES.has(payloadMode)) {
      return Response.json({ error: `Invalid payload_mode.` }, { status: 400 });
    }

    // Validate locale via Intl
    try {
      new Intl.Locale(locale);
    } catch {
      return Response.json({ error: `Invalid locale: ${locale}` }, { status: 400 });
    }

    const id = crypto.randomUUID();
    await env.DB
      .prepare(
        'INSERT INTO webhook_subscribers (id, endpoint, secret, locale, date_format, payload_mode, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)'
      )
      .bind(id, body.endpoint, body.secret, locale, dateFormat, payloadMode, new Date().toISOString())
      .run();

    return Response.json({ id, locale, date_format: dateFormat, payload_mode: payloadMode }, { status: 201 });
  },
};
```

---

## Anti-patterns

**Sending locale-formatted strings as the *only* representation:**
```json
{ "amount": "1.234,56 €" }  // ❌ — receiver cannot parse this back to a number
```

**Formatting on the receiver side from a locale hint in the header:**
Relying on the receiver to pick up `X-Subscriber-Locale` and format the numbers
themselves puts the burden on the consumer. Store the preference; format on the
sender side.

**Silently defaulting all subscribers to `en-US` format:**
```typescript
const locale = subscriber.locale ?? 'en-US'; // ❌ if stored locale is '' or NULL
```
A NULL locale in D1 means the subscriber was never configured, not that they want
`en-US`. Require locale on registration.

**Using `.toLocaleString()` without locking the locale:**
```typescript
amount.toLocaleString() // ❌ — uses the Workers runtime's system locale, not subscriber's
```

---

## Gotchas

- **`Intl.NumberFormat` with `style: 'currency'` includes the currency symbol**
  in the formatted string. Some legacy receivers expect a bare number. Offer a
  `number_display` field using `style: 'decimal'` for those cases.
- **Queue retries**: Workers Queues retry on throw. If you throw inside `deliverWebhook`,
  every subscriber gets retried, not just the failed one. Use `Promise.allSettled`
  and track individual delivery failures in D1 rather than throwing unconditionally.
- **Time zones in date display**: `event.settledAt` is UTC. If a subscriber wants
  dates in their local time zone (e.g., `Europe/Berlin`), you need to apply a
  time zone offset before formatting. Store `subscriber.timezone` separately and
  use `Intl.DateTimeFormat` with `timeZone` to extract the local date.
- **Idempotency**: queue retries can deliver the same payload twice. Include an
  `idempotency_key: event.invoiceId` field in every payload so receivers can
  deduplicate.
- **Large subscriber lists**: iterating all subscribers for every event becomes a
  full-table scan. Add an index on `webhook_subscribers(created_at)` and consider
  pagination for subscriber counts above ~500.

---

## Verification

```typescript
// tests/webhook-formatter.test.ts
import { buildPayload } from '../src/lib/webhook-formatter';
import { describe, it, expect } from 'vitest';

const event = {
  invoiceId: 'inv_001',
  amount: 1234.56,
  currency: 'EUR',
  settledAt: new Date('2024-08-15T10:30:00Z'),
};

describe('buildPayload', () => {
  it('canonical mode: no display fields', () => {
    const p = buildPayload(event, { locale: 'de-DE', dateFormat: 'ISO8601', payloadMode: 'canonical' });
    expect(p.amount_raw).toBe(1234.56);
    expect(p.settled_at_iso).toBe('2024-08-15T10:30:00.000Z');
    expect(p.amount_display).toBeUndefined();
  });

  it('display mode for de-DE: uses dot thousand sep, comma decimal', () => {
    const p = buildPayload(event, { locale: 'de-DE', dateFormat: 'DMY_DOT', payloadMode: 'display' });
    expect(p.amount_display).toMatch(/1\.234,56/); // e.g. "1.234,56 €"
    expect(p.settled_at_display).toBe('15.08.2024');
    expect(p.amount_raw).toBeUndefined();
  });

  it('hybrid mode: includes both canonical and display', () => {
    const p = buildPayload(event, { locale: 'en-US', dateFormat: 'MDY_SLASH', payloadMode: 'hybrid' });
    expect(p.amount_raw).toBe(1234.56);
    expect(p.amount_display).toBeDefined();
    expect(p.settled_at_iso).toBeDefined();
    expect(p.settled_at_display).toBe('08/15/2024');
  });
});
```

---

## Related

- `locale-aware-date-parsing-ambiguity-workers.md`
- `cldr-supplemental-currency-fraction-digits-workers.md`
- `workers-queues-async-translation-pipeline.md`
- `workers-queues-locale-push-notification-scheduling.md`
- `currency-formatting-cloudflare-workers-intl-numberformat.md`

---

## Sources

- Workers Queues documentation: https://developers.cloudflare.com/queues/
- `Intl.NumberFormat` with currency: https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Global_Objects/Intl/NumberFormat
- Webhook signing best practice (Stripe model): https://stripe.com/docs/webhooks/signatures
- D1 documentation: https://developers.cloudflare.com/d1/
