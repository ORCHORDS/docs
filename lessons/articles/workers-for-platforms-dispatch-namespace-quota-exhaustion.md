# Incident: Workers for Platforms Dispatch Namespace Quota Exhaustion Blocked Tenant Deployments

- **Date:** 2026-08-23
- **Author:** example.com
- **Status:** production
- **Severity:** P1 — all tenant script deployments failed for 47 minutes

---

## Symptom

At 09:14 UTC the platform's tenant onboarding pipeline began returning HTTP 429 errors on every call to the Cloudflare API endpoint that registers a new Workers for Platforms (WfP) script into the dispatch namespace. New customer sign-ups completed their UI flow, but the background Worker that provisions each tenant's isolated script slot received `"workers.api.error.exceeded_workers_for_platforms_limit"` and queued them as permanently failed. Forty-seven minutes elapsed before the quota was identified and remediated. Approximately 230 new tenants were stuck in a broken state with no active script.

---

## Context

Workers for Platforms allows a SaaS provider to run untrusted tenant code inside Cloudflare Workers by uploading per-tenant scripts into a **dispatch namespace**. The platform used one dispatch namespace per environment (production, staging). Each dispatch namespace is subject to a quota on the number of scripts it may contain. The quota is set at account creation and is not self-serve — it requires a Cloudflare Enterprise support ticket or a limit increase through the dashboard.

The platform had grown steadily from 1,200 tenants to 9,800 tenants over eight months. Nobody had tracked how close the dispatch namespace was to its provisioned quota ceiling.

---

## Timeline

| UTC | Event |
|-----|-------|
| 09:12:41 | Tenant #10,001 onboarding triggered via webhook |
| 09:14:03 | First 429 with quota error from CF API observed in logs |
| 09:14:51 | Onboarding queue begins accumulating failed jobs |
| 09:21:00 | Support ticket opened by on-call (initially misrouted to billing) |
| 09:35:00 | Ticket escalated to Cloudflare Enterprise support |
| 09:58:00 | Temporary quota increase provisioned by Cloudflare |
| 10:01:22 | Queue replay begins; tenant scripts deploy successfully |
| 10:15:00 | All 230 backlogged tenants provisioned; incident closed |

---

## Root Cause Analysis

### Primary: No Quota Headroom Monitoring

The dispatch namespace quota was a hard account-level ceiling unknown to the engineering team. There was no alert, dashboard panel, or capacity review that tracked the current script count versus the provisioned ceiling. The quota was hit cold with no warning.

### Contributing: No Soft-Limit Alert

The Cloudflare API does not proactively notify account holders when a quota is approaching saturation. The only signal is the 429 error returned when the limit is exceeded. Without a proactive check (e.g. a scheduled Worker that polls the current count), the team had no warning.

### Contributing: Onboarding Queue Treated 429 as Permanent Failure

The job queue processing tenant script uploads used a retry policy that classified HTTP 4xx responses as non-retryable. This caused all 230 jobs queued during the 47-minute window to be marked dead immediately rather than being retried after quota was increased. The jobs required manual replay.

---

## Technical Sections

### 1. Dispatch Namespace Script Count — Querying Headroom

There is no dedicated "quota remaining" endpoint, but the total number of scripts currently uploaded into a dispatch namespace can be fetched via the Cloudflare API and compared against the known provisioned ceiling:

```ts
// Scheduled Worker: runs every hour, alerts when >80% of quota used
export default {
  async scheduled(_event: ScheduledEvent, env: Env): Promise<void> {
    const accountId = env.CF_ACCOUNT_ID;
    const namespaceName = env.DISPATCH_NAMESPACE_NAME;
    const provisioned = Number(env.DISPATCH_NAMESPACE_QUOTA); // store in secret

    const resp = await fetch(
      `https://api.cloudflare.com/client/v4/accounts/${accountId}/workers/dispatch/namespaces/${namespaceName}/scripts?per_page=1`,
      {
        headers: { Authorization: `Bearer ${env.CF_API_TOKEN}` },
      }
    );
    const body = await resp.json<{ result_info: { total_count: number } }>();
    const used = body.result_info.total_count;
    const pct = (used / provisioned) * 100;

    await env.ANALYTICS.writeDataPoint({
      blobs: [namespaceName],
      doubles: [used, provisioned, pct],
      indexes: ['wfp_quota_used'],
    });

    if (pct >= 80) {
      await fetch(env.ALERT_WEBHOOK_URL, {
        method: 'POST',
        body: JSON.stringify({ text: `WfP quota at ${pct.toFixed(1)}% (${used}/${provisioned})` }),
      });
    }
  },
};
```

### 2. Classifying 429 Quota Errors as Retryable

A quota-exhaustion 429 is fundamentally different from a rate-limit 429. A rate-limit 429 resolves after a delay; a quota 429 resolves only after a limit increase. The onboarding queue must distinguish them:

```ts
async function uploadTenantScript(tenantId: string, env: Env): Promise<void> {
  const resp = await fetch(
    `https://api.cloudflare.com/client/v4/accounts/${env.CF_ACCOUNT_ID}/workers/dispatch/namespaces/${env.NS}/scripts/${tenantId}`,
    { method: 'PUT', headers: buildHeaders(env), body: buildScriptBody(tenantId) }
  );

  if (resp.status === 429) {
    const body = await resp.json<{ errors: Array<{ code: number; message: string }> }>();
    const isQuotaError = body.errors.some(e => e.message.includes('exceeded_workers_for_platforms_limit'));

    if (isQuotaError) {
      // Do NOT mark as permanent failure — quota may be increased at any time
      // Enqueue with a long delay and alert
      await env.ONBOARDING_QUEUE.send({ tenantId, reason: 'quota_exhausted' }, { delaySeconds: 300 });
      await notifyOpsChannel(env, `WfP quota exhausted — tenant ${tenantId} queued for retry`);
      return;
    }

    // True rate limit: back off and retry
    throw new RetryableError('Rate limited by CF API');
  }

  if (!resp.ok) {
    throw new Error(`CF API error ${resp.status}: ${await resp.text()}`);
  }
}
```

### 3. Tracking Dispatch Namespace Quota Ceiling as a Platform Constant

Store the provisioned ceiling alongside the namespace name in environment variables or a KV config entry so it is always accessible to monitoring code:

```toml
# wrangler.toml — production environment
[env.production.vars]
DISPATCH_NAMESPACE_NAME    = "prod-tenant-scripts"
DISPATCH_NAMESPACE_QUOTA   = "15000"   # update after any limit increase
```

When Cloudflare increases the limit, update this value in the same PR that processes the support ticket, keeping documentation and runtime value in sync.

### 4. Runbook: Requesting a Quota Increase

Quota increases require contacting Cloudflare support. Automate the escalation trigger:

```ts
async function ensureQuotaHeadroom(env: Env, current: number, ceiling: number): Promise<void> {
  const headroom = ceiling - current;
  if (headroom < 500) {
    // Open a Jira ticket or send a Slack alert for the team to file a CF support request
    await env.OPS_QUEUE.send({
      type: 'quota_increase_request',
      resource: 'wfp_dispatch_namespace',
      namespace: env.DISPATCH_NAMESPACE_NAME,
      current,
      ceiling,
      requestedCeiling: ceiling + 5000,
    });
  }
}
```

### 5. Replay Dead-Letter Queue After Quota Restored

After a quota increase, jobs in the dead-letter queue must be replayed. Design the DLQ payload to include all fields needed for a clean replay without a re-query:

```ts
interface OnboardingJob {
  tenantId: string;
  scriptContent: string;       // embedded, not a reference — avoids a DB round-trip on replay
  reason?: 'quota_exhausted';
  enqueuedAt: number;
}

// Replay handler — invoked by ops after quota increase confirmed
async function replayQuotaDeadLetterQueue(env: Env): Promise<void> {
  const dlq = await env.KV.list({ prefix: 'dlq:quota:' });
  for (const key of dlq.keys) {
    const job = await env.KV.get<OnboardingJob>(key.name, 'json');
    if (job) {
      await env.ONBOARDING_QUEUE.send(job);
      await env.KV.delete(key.name);
    }
  }
}
```

### 6. Capacity Planning for WfP Dispatch Namespace Scripts

Model growth and project quota exhaustion date quarterly:

```ts
// Scheduled: monthly capacity report
async function wfpCapacityReport(env: Env): Promise<void> {
  const history = await env.ANALYTICS.query(`
    SELECT SUM(double1) as used, MAX(double3) as pct
    FROM DELINEATED_DATASET
    WHERE timestamp > NOW() - INTERVAL '30 days'
    AND index1 = 'wfp_quota_used'
  `);
  const growthPerMonth = /* diff of first and last datapoints */ 0;
  const ceiling = Number(env.DISPATCH_NAMESPACE_QUOTA);
  const current = /* latest count */ 0;
  const monthsToExhaustion = (ceiling - current) / growthPerMonth;
  // Alert if < 3 months headroom
  if (monthsToExhaustion < 3) {
    await notifyOpsChannel(env, `WfP quota will exhaust in ~${monthsToExhaustion.toFixed(1)} months. File limit increase now.`);
  }
}
```

---

## Anti-Patterns

- **No headroom monitoring for account-level quotas.** Hard limits imposed by Cloudflare are not visible in Grafana unless you instrument them yourself. Assume every quota is opaque until you query it.
- **Treating quota 429 as a permanent job failure.** A 429 from a quota ceiling is a temporary infrastructure condition. Jobs must be durable, delayed, and replayed after the ceiling is raised.
- **Storing provisioned quota only in a team's memory.** The person who negotiated the original limit increase may no longer be on the team. Store it in source-controlled config and update it with every change.
- **Waiting for the quota error to discover the ceiling.** Always know the ceiling before hitting it. Set alerts at 70% and 90% of quota.
- **Manual replay procedures with no runbook.** The 15-minute replay after quota restoration was slower than necessary because there was no documented replay procedure. Write the runbook before the incident.

---

## Gotchas

- The `per_page=1` trick on the scripts list endpoint returns `result_info.total_count` without downloading all script metadata. Use it for lightweight quota polling.
- Dispatch namespace script count includes scripts in all states (active, draft, error). A failed upload may still consume a slot until explicitly deleted.
- Cloudflare quota increases can take minutes to hours to propagate to all API edge nodes. After receiving confirmation, wait 5 minutes before replaying the queue and verify a test upload succeeds first.
- Wrangler's `wrangler dispatch-namespace list-scripts` command outputs paginated JSON; pipe through `jq` and sum pages to get an accurate total count for ad-hoc checks.
- There is a separate quota for **dispatch namespace count** (number of namespaces per account) and **script count per namespace**. Monitor both.

---

## Verification

Post-incident verification steps completed on 2026-08-23:

1. Confirmed hourly scheduled Worker emits `wfp_quota_used` data points to Analytics Engine; dashboard panel shows current count vs ceiling.
2. Alert fired correctly in staging when count was manually set above 80% threshold via synthetic KV override.
3. DLQ replay script executed against 230 backlogged jobs in staging clone; all deployed within 4 minutes.
4. Retry policy updated in onboarding queue consumer to route quota 429s to delayed retry bucket (5-minute delay, 48-hour TTL) rather than dead-letter.
5. `DISPATCH_NAMESPACE_QUOTA` added to `wrangler.toml` for all environments; PR merged and reviewed by two engineers.

---

## Related

- `cloudflare-workers-engineering-onboarding.md`
- `capacity-forecast-error-review-loop.md`
- `queue-consumers-must-be-idempotent.md`
- `rate-limit-before-you-need-it.md`
- `build-vs-buy-cloudflare-adjacent-tooling.md`

---

## Sources

- Cloudflare Workers for Platforms documentation: https://developers.cloudflare.com/cloudflare-for-platforms/workers-for-platforms/
- Cloudflare API — Dispatch Namespace scripts list: https://developers.cloudflare.com/api/operations/workers-for-platforms-list-namespace-scripts
- Workers limits and quotas: https://developers.cloudflare.com/workers/platform/limits/
- Cloudflare Queues — delayed delivery: https://developers.cloudflare.com/queues/configuration/javascript-apis/#messagesendoptions
