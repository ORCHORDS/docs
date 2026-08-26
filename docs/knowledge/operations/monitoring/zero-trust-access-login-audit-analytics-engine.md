# Zero Trust Access Login Audit with Analytics Engine

Date: 2026-08-23
Author: example.com
Status: production

## Symptom / Use-case

Your team uses Cloudflare Zero Trust Access to gate internal tools and staging environments. You
need to answer: Who logged in? From where? How often do logins fail? Which applications see the
most traffic from which identity providers? The built-in Access audit log is queryable via API but
not aggregatable; shipping it to Analytics Engine gives you SQL-based dashboards, anomaly detection,
and long-term trending without a third-party SIEM.

## Context

Cloudflare Zero Trust emits Access audit events via Logpush in the `access_requests` dataset. Each
row contains the user email, identity provider (IdP), application URL, action (`login`,
`logout`, `failed_login`), country, and timestamp. By landing these events in Analytics Engine
(via a receiver Worker), you gain SQL aggregation for per-user, per-app, and per-IdP breakdowns
at minimal cost. The pipeline is: Logpush → HTTP destination → receiver Worker → Analytics Engine.

## Architecture Overview

```
Cloudflare Access  →  Logpush (access_requests)  →  Receiver Worker  →  Analytics Engine
                                                         ↓
                                              (scheduled Worker)  →  Alerts / Dashboard
```

## Logpush Job for Access Requests

```typescript
// scripts/create-access-logpush.ts
const destinationUrl = new URL("https://log-receiver.example.workers.dev/access-audit");
destinationUrl.searchParams.set("header_Authorization", `Bearer ${process.env.RECEIVER_SECRET}`);

const body = {
  name: "zero-trust-access-audit",
  dataset: "access_requests",
  output_options: {
    field_names: [
      "AppDomain",
      "AppUUID",
      "Action",       // login | logout | failed_login | service_auth
      "UserEmail",
      "IDPType",
      "Country",
      "IPAddress",
      "CreatedAt",
      "Allowed",      // bool
      "PolicyResults",
    ],
    timestamp_format: "rfc3339",
    batch_prefix: "",
    batch_suffix: "",
    record_delimiter: "\n",
  },
  destination_conf: destinationUrl.toString(),
  enabled: true,
  frequency: "high",
};

await fetch(
  `https://api.cloudflare.com/client/v4/accounts/${process.env.CF_ACCOUNT_ID}/logpush/jobs`,
  {
    method: "POST",
    headers: { Authorization: `Bearer ${process.env.CF_API_TOKEN}`, "Content-Type": "application/json" },
    body: JSON.stringify(body),
  }
);
```

## Receiver Worker: Logpush → Analytics Engine

```typescript
// log-receiver-worker/src/index.ts
export interface Env {
  ACCESS_AUDIT: AnalyticsEngineDataset;
  RECEIVER_SECRET: string;
}

interface AccessLogRow {
  AppDomain: string;
  AppUUID: string;
  Action: string;
  UserEmail: string;
  IDPType: string;
  Country: string;
  IPAddress: string;
  CreatedAt: string;
  Allowed: boolean;
  PolicyResults?: string;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    // Auth check
    const token = request.headers.get("Authorization")?.replace("Bearer ", "");
    if (token !== env.RECEIVER_SECRET) {
      return new Response("Unauthorized", { status: 401 });
    }

    const text = await request.text();
    const lines = text.split("\n").filter(Boolean);

    for (const line of lines) {
      let row: AccessLogRow;
      try {
        row = JSON.parse(line);
      } catch {
        continue; // skip malformed lines
      }

      const isAllowed = row.Allowed ? 1 : 0;
      const isFailedLogin = row.Action === "failed_login" ? 1 : 0;
      const isLogin = row.Action === "login" ? 1 : 0;

      env.ACCESS_AUDIT.writeDataPoint({
        blobs: [
          row.UserEmail ?? "",      // blob1 – user
          row.AppDomain ?? "",      // blob2 – app
          row.Action ?? "",         // blob3 – action type
          row.IDPType ?? "",        // blob4 – identity provider
          row.Country ?? "",        // blob5 – country code
          row.IPAddress ?? "",      // blob6 – source IP
        ],
        doubles: [
          1,              // double1 – event count
          isLogin,        // double2 – login count
          isFailedLogin,  // double3 – failed login count
          isAllowed,      // double4 – allowed count
          1 - isAllowed,  // double5 – denied count
        ],
        indexes: [row.UserEmail ?? "unknown"],
      });
    }

    return new Response("OK");
  },
} satisfies ExportedHandler<Env>;
```

## Failed Login Rate by Application

```sql
SELECT
  blob2 AS app_domain,
  sum(double2)  AS logins,
  sum(double3)  AS failed_logins,
  sum(double3) / sum(double2) * 100 AS failure_pct
FROM zero_trust_access_audit
WHERE timestamp > NOW() - INTERVAL '24' HOUR
GROUP BY blob2
ORDER BY failure_pct DESC
LIMIT 20
```

## Per-User Login Frequency (Anomaly Detection Seed)

Export daily login counts per user to detect account compromise or credential stuffing:

```sql
SELECT
  blob1 AS user_email,
  toStartOfInterval(timestamp, INTERVAL '1' HOUR) AS hour,
  sum(double2) AS logins
FROM zero_trust_access_audit
WHERE
  timestamp > NOW() - INTERVAL '7' DAY
  AND double2 = 1
GROUP BY blob1, hour
ORDER BY logins DESC
```

A scheduled Worker queries this and pages on-call if any user exceeds N logins in an hour:

```typescript
// src/anomaly-check.ts
export default {
  async scheduled(_event: ScheduledEvent, env: Env): Promise<void> {
    const sql = `
      SELECT blob1 AS email, sum(double2) AS logins
      FROM zero_trust_access_audit
      WHERE timestamp > NOW() - INTERVAL '1' HOUR AND double2 = 1
      GROUP BY blob1
      HAVING logins > 50
    `;
    const res = await queryAE(sql, env);
    for (const row of res.data) {
      await env.ALERT_QUEUE.send({
        severity: "high",
        message: `Suspicious login volume: ${row.email} made ${row.logins} logins in 1 hour`,
      });
    }
  },
} satisfies ExportedHandler<Env>;
```

## IdP Usage Distribution Dashboard Query

```sql
SELECT
  blob4 AS idp_type,
  sum(double1)  AS events,
  sum(double2)  AS logins,
  sum(double3)  AS failed_logins,
  sum(double5)  AS denied
FROM zero_trust_access_audit
WHERE timestamp > NOW() - INTERVAL '30' DAY
GROUP BY blob4
ORDER BY events DESC
```

## Country-Level Access Breakdown

```sql
SELECT
  blob5 AS country,
  sum(double1) AS events,
  sum(double3) AS failed_logins
FROM zero_trust_access_audit
WHERE timestamp > NOW() - INTERVAL '7' DAY
GROUP BY blob5
ORDER BY events DESC
LIMIT 30
```

## Anti-patterns

- **Storing raw `PolicyResults` JSON in a blob.** PolicyResults can be hundreds of bytes long and
  bloat blob storage. Parse to a summary flag (`"all_passed"`, `"partial"`, `"blocked"`) before
  writing.
- **Using `IPAddress` as an Analytics Engine index.** IPs are extremely high-cardinality and the
  index is meant for the primary group-by key (user email or app domain). Keep IP as a blob for
  filtering only.
- **Mixing Access audit rows with Worker trace rows in the same dataset.** Schema collisions on
  blob/double positions make queries confusing. Use a dedicated `zero_trust_access_audit` dataset.
- **Alerting on absolute failure counts.** One failed login might be a typo. Alert on rate
  (failed/total > threshold over a sliding window) or on burst (N failures in M minutes from a
  single IP).

## Gotchas

- The `access_requests` Logpush dataset is only available on Zero Trust plans (Teams Standard or
  above). It does not appear in the dataset list on Free-tier accounts.
- `UserEmail` is empty for service auth tokens (non-user machine-to-machine). Filter or handle the
  empty-string case explicitly.
- Logpush delivers `access_requests` with up to a 60-second delay. Real-time security dashboards
  should supplement with the Zero Trust API for the most recent events.
- Analytics Engine rows are immutable. If you need to correct a mislabeled row, you must append a
  compensating row; there is no UPDATE.

## Verification

1. Log in to an Access-protected application from two different countries (use a VPN for the
   second).
2. Wait 90 seconds for Logpush delivery.
3. Query:
   ```sql
   SELECT blob1, blob5, blob3, count() FROM zero_trust_access_audit
   WHERE timestamp > NOW() - INTERVAL '5' MINUTE
   GROUP BY blob1, blob5, blob3
   ```
   Expect rows for your email with two different country codes.
4. Attempt a failed login; confirm `double3 = 1` in the corresponding row.
5. Run the anomaly alert query with threshold lowered to 1; confirm alert fires.

## Related

- `logpush-http-destination-custom-auth-headers.md`
- `cloudflare-logpush-setup.md`
- `analytics-engine-multi-tenant-usage-metering.md`
- `cloudflare-analytics-engine.md`
- `alert-severity-levels.md`
- `log-security-masking.md`

## Sources

- https://developers.cloudflare.com/cloudflare-one/insights/logs/audit-logs/
- https://developers.cloudflare.com/logs/reference/log-fields/account/access_requests/
- https://developers.cloudflare.com/analytics/analytics-engine/
- https://developers.cloudflare.com/cloudflare-one/identity/idp-integration/
