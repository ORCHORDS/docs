# Multi-Tenant Email Sending Domain Isolation with D1 and Workers

Date: 2026-08-23
Author: example.com
Status: production

## Symptom / Use-case

SaaS platforms that send email on behalf of multiple customers (tenants) must prevent one tenant's sending reputation from poisoning another's. Without isolation, a high-complaint-rate tenant degrades the shared IP pool's deliverability for every other tenant on the platform. Isolation means each tenant maps to a dedicated sending domain, a tenant-scoped DKIM key, and a tenant-scoped suppression list — and cross-tenant data leakage in analytics and suppression management is eliminated at the application layer.

A Cloudflare Workers + D1 architecture enforces this isolation per-request: every outbound API call is routed through a tenant-aware envelope builder that selects the correct `From` domain, DKIM selector, and daily quota limit based on the authenticated tenant's record in D1.

## Context

MailChannels supports per-sender DKIM keys supplied at API call time via `personalizations[].dkim_domain`, `personalizations[].dkim_selector`, and `personalizations[].dkim_private_key`. This makes it straightforward to store per-tenant DKIM credentials in D1 and inject them at send time in a Worker, without any shared credential surface across tenants.

D1 provides the ACID semantics needed to atomically enforce per-tenant suppression lists, daily send quotas, and rate windows. Workers Queues handles async batch dispatch so that tenant isolation applies equally to synchronous sends and deferred bulk sends.

## Tenant Registry in D1

```sql
-- Tenant configuration
CREATE TABLE tenants (
  id               TEXT    PRIMARY KEY,
  api_key          TEXT    NOT NULL UNIQUE,
  sending_domain   TEXT    NOT NULL UNIQUE,
  dkim_selector    TEXT    NOT NULL,
  dkim_private_key TEXT    NOT NULL,   -- PEM PKCS8; never store plaintext in production
  daily_send_quota INTEGER NOT NULL DEFAULT 10000,
  plan             TEXT    NOT NULL DEFAULT 'starter',  -- starter | growth | enterprise
  active           INTEGER NOT NULL DEFAULT 1,
  created_at       TEXT    NOT NULL
);

-- Per-tenant suppression list (separate from any shared list)
CREATE TABLE tenant_suppressions (
  tenant_id    TEXT NOT NULL,
  email        TEXT NOT NULL,
  reason       TEXT,             -- 'bounce' | 'complaint' | 'unsubscribe' | 'manual'
  suppressed_at TEXT NOT NULL,
  PRIMARY KEY (tenant_id, email),
  FOREIGN KEY (tenant_id) REFERENCES tenants(id)
);

-- Per-tenant daily rolling send counter
CREATE TABLE tenant_send_counts (
  tenant_id TEXT NOT NULL,
  date      TEXT NOT NULL,  -- YYYY-MM-DD UTC
  count     INTEGER NOT NULL DEFAULT 0,
  PRIMARY KEY (tenant_id, date)
);

CREATE INDEX idx_tenant_suppressions_tenant
  ON tenant_suppressions(tenant_id);
```

## Tenant Authentication and Envelope Building

```typescript
export interface Env {
  DB: D1Database;
}

interface TenantConfig {
  id: string;
  sendingDomain: string;
  dkimSelector: string;
  dkimPrivateKey: string;
  dailySendQuota: number;
}

async function resolveTenant(
  db: D1Database,
  apiKey: string
): Promise<TenantConfig | null> {
  const row = await db
    .prepare(
      `SELECT id, sending_domain, dkim_selector, dkim_private_key, daily_send_quota
       FROM tenants
       WHERE api_key = ? AND active = 1`
    )
    .bind(apiKey)
    .first<{
      id: string;
      sending_domain: string;
      dkim_selector: string;
      dkim_private_key: string;
      daily_send_quota: number;
    }>();

  if (!row) return null;

  return {
    id: row.id,
    sendingDomain: row.sending_domain,
    dkimSelector: row.dkim_selector,
    dkimPrivateKey: row.dkim_private_key,
    dailySendQuota: row.daily_send_quota,
  };
}

// Atomic upsert + quota check in one round-trip using RETURNING
async function checkAndIncrementQuota(
  db: D1Database,
  tenantId: string,
  quota: number
): Promise<{ allowed: boolean; count: number }> {
  const today = new Date().toISOString().slice(0, 10); // YYYY-MM-DD

  const result = await db
    .prepare(
      `INSERT INTO tenant_send_counts (tenant_id, date, count) VALUES (?, ?, 1)
       ON CONFLICT(tenant_id, date) DO UPDATE SET count = count + 1
       RETURNING count`
    )
    .bind(tenantId, today)
    .first<{ count: number }>();

  const count = result?.count ?? 1;
  return { allowed: count <= quota, count };
}

async function isSuppressed(
  db: D1Database,
  tenantId: string,
  email: string
): Promise<boolean> {
  const row = await db
    .prepare(
      "SELECT 1 FROM tenant_suppressions WHERE tenant_id = ? AND email = ?"
    )
    .bind(tenantId, email.toLowerCase())
    .first();
  return !!row;
}
```

## Sending Through MailChannels with Per-Tenant DKIM

```typescript
interface SendOptions {
  tenantId: string;
  config: TenantConfig;
  fromLocalPart: string;
  fromName: string;
  to: string;
  subject: string;
  html: string;
  text?: string;
}

async function sendTenantEmail(opts: SendOptions): Promise<void> {
  const fromEmail = `${opts.fromLocalPart}@${opts.config.sendingDomain}`;
  const messageId = `<${crypto.randomUUID()}@${opts.config.sendingDomain}>`;

  const response = await fetch("https://api.mailchannels.net/tx/v1/send", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      personalizations: [
        {
          to: [{ email: opts.to }],
          // Per-tenant DKIM — injected per-message, never shared
          dkim_domain:      opts.config.sendingDomain,
          dkim_selector:    opts.config.dkimSelector,
          dkim_private_key: opts.config.dkimPrivateKey,
        },
      ],
      from: { email: fromEmail, name: opts.fromName },
      subject: opts.subject,
      headers: { "Message-ID": messageId },
      content: [
        { type: "text/html; charset=utf-8", value: opts.html },
        ...(opts.text
          ? [{ type: "text/plain; charset=utf-8", value: opts.text }]
          : []),
      ],
    }),
  });

  if (!response.ok) {
    const body = await response.text();
    throw new Error(`MailChannels error ${response.status}: ${body}`);
  }
}
```

## Worker API Handler

```typescript
export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);
    if (request.method !== "POST" || url.pathname !== "/v1/send") {
      return new Response("Not Found", { status: 404 });
    }

    const apiKey = <redacted-secret>"X-Api-Key");
    if (!apiKey) return new Response("Unauthorized", { status: 401 });

    const config = await resolveTenant(env.DB, apiKey);
    if (!config) return new Response("Unauthorized", { status: 401 });

    const body = await request.json<{
      to: string;
      subject: string;
      html: string;
      text?: string;
      fromName?: string;
      fromLocalPart?: string;
    }>();

    // Enforce that From domain matches the tenant's registered domain
    const fromLocalPart = (body.fromLocalPart ?? "noreply").replace(/@.*/, "");

    // Suppression check (tenant-scoped)
    if (await isSuppressed(env.DB, config.id, body.to)) {
      return Response.json(
        { error: "Recipient is suppressed for this account" },
        { status: 422 }
      );
    }

    // Quota check (atomic)
    const { allowed, count } = await checkAndIncrementQuota(
      env.DB,
      config.id,
      config.dailySendQuota
    );
    if (!allowed) {
      return Response.json(
        { error: `Daily send quota of ${config.dailySendQuota} exceeded (used ${count})` },
        { status: 429 }
      );
    }

    await sendTenantEmail({
      tenantId: config.id,
      config,
      fromLocalPart,
      fromName: body.fromName ?? "Notifications",
      to: body.to,
      subject: body.subject,
      html: body.html,
      text: body.text,
    });

    return Response.json({ success: true });
  },
};
```

## Tenant Complaint Monitoring Cron

```typescript
export default {
  async scheduled(_event: ScheduledEvent, env: Env, _ctx: ExecutionContext) {
    // Flag tenants whose 7-day complaint-driven suppressions exceed a threshold
    const highRisk = await env.DB.prepare(
      `SELECT tenant_id, COUNT(*) AS complaints
       FROM tenant_suppressions
       WHERE suppressed_at > datetime('now', '-7 days')
         AND reason = 'complaint'
       GROUP BY tenant_id
       HAVING complaints > 50`
    ).all<{ tenant_id: string; complaints: number }>();

    for (const { tenant_id, complaints } of highRisk.results) {
      console.warn(
        JSON.stringify({
          event: "high_complaint_rate_tenant",
          tenant_id,
          complaints_7d: complaints,
        })
      );
      // Optionally: auto-suspend tenant by setting active = 0
    }
  },
};
```

## Adding a Tenant Suppression Entry

```typescript
async function suppressAddress(
  db: D1Database,
  tenantId: string,
  email: string,
  reason: "bounce" | "complaint" | "unsubscribe" | "manual"
): Promise<void> {
  await db
    .prepare(
      `INSERT OR IGNORE INTO tenant_suppressions
         (tenant_id, email, reason, suppressed_at)
       VALUES (?, ?, ?, ?)`
    )
    .bind(tenantId, email.toLowerCase(), reason, new Date().toISOString())
    .run();
}
```

## Anti-patterns

- Storing DKIM private keys as plaintext in D1 without encryption — use Workers Secrets (for a shared platform key) combined with per-tenant key material encrypted at rest in D1
- Sharing a single suppression list across all tenants — a suppression for tenant A silently blocks sends for tenant B to the same address
- Allowing tenants to supply arbitrary `From` domains — enforce that `fromLocalPart@<sending_domain>` always uses the tenant's registered domain; any other value is rejected
- Not enforcing per-tenant DKIM — a tenant sending without DKIM will fail DMARC alignment and damage your platform's sending domain reputation
- Using a shared `Message-ID` local part namespace across tenants — include the tenant ID in the local part to prevent cross-tenant message ID collisions in email thread tracking

## Gotchas

- D1's `ON CONFLICT DO UPDATE` upsert is not strictly serializable under concurrent Workers invocations for the same tenant and date; a burst of concurrent requests may increment slightly over quota before the check fires — add a 5–10% tolerance or use a Durable Object counter for strict enforcement
<redacted-private-key>
