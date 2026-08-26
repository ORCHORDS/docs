# Incident Severity Classification Automation

- **Date**: 2026-08-22
- **Author**: example.com
- **Status**: production

## Symptom / Use-case

On-call engineers spend the first minutes of every incident manually deciding
whether an alert is a P1, P2, or P3. That decision is high-stakes and
time-pressured, so it is often wrong in both directions: SEV1 labels on minor
blips drain team confidence; SEV3 labels on real outages delay escalation.
Teams want a consistent, auditable rule that assigns severity automatically the
moment an alert fires, without waiting for human triage.

## Context

Severity classification is the gateway to every downstream workflow: which
runbook fires, who gets paged, whether a status page update goes out, and
whether a post-mortem is required. Automating it replaces ad-hoc judgment with
a deterministic policy expressed in code, enabling consistent treatment across
time zones, engineers, and services. The classifier sits between the alerting
system (Prometheus / Cloudflare Workers alerts / Datadog) and the notification
router (PagerDuty / OpsGenie / Slack) and stamps each incoming event with a
severity before routing decisions are made.

Two approaches coexist in production systems:

- **Rules-based classification** — explicit threshold and label conditions
  evaluated in AlertManager, a Worker, or a CI script.
- **ML-assisted classification** — a lightweight model trained on historical
  incidents scores new events; a rules layer overrides it for safety-critical
  paths.

This article focuses on the rules-based path first (highest ROI, immediate
deployability) and then shows how to layer ML scoring on top.

## Severity Taxonomy

Define severity as a closed enum before writing any rules. A widely adopted
four-level taxonomy:

| Level | Label | Customer Impact | Response SLA |
|-------|-------|-----------------|--------------|
| 1 | SEV1 / P1 | Total service loss or data loss for all users | Page immediately, 15 min acknowledgement |
| 2 | SEV2 / P2 | Degraded service for a significant user cohort | Page in-hours on-call, 30 min ack |
| 3 | SEV3 / P3 | Minor degradation, workarounds exist | Ticket, next business day |
| 4 | SEV4 / P4 | Cosmetic / informational | Backlog |

Encode this as a shared config object checked into your infrastructure repo.
Every classification rule references the same enum. If the taxonomy changes,
one file changes.

## Rules-Based Classification Pipeline

### Signal Inputs

Every alert carries signals that drive severity:

- **Error rate** — percentage of requests returning 5xx or timeout.
- **Affected user count** — absolute or estimated from traffic share.
- **Service criticality label** — `tier=1` vs `tier=2` vs `tier=3` on the
  emitting service. Attach this label in Prometheus scrape config or as a
  Cloudflare Workers binding metadata field.
- **Time-of-day** — a 2 % error rate at 03:00 UTC may be SEV3; at 14:00 UTC
  peak it is SEV2 because more users are affected.
- **Blast radius** — single region vs multi-region vs global CDN.

### AlertManager Classification Rules (Prometheus)

```yaml
# severity-classification.yaml
groups:
  - name: severity_routing
    rules:
      - alert: HighErrorRate_SEV1
        expr: |
          sum(rate(http_requests_total{status=~"5.."}[2m]))
          / sum(rate(http_requests_total[2m])) > 0.20
        for: 1m
        labels:
          severity: sev1
          page: "true"
        annotations:
          summary: "Global error rate >20% for 1m — SEV1"

      - alert: HighErrorRate_SEV2
        expr: |
          sum(rate(http_requests_total{status=~"5.."}[5m]))
          / sum(rate(http_requests_total[5m])) > 0.05
        for: 3m
        labels:
          severity: sev2
          page: "true"
        annotations:
          summary: "Error rate >5% for 3m — SEV2"

      - alert: ElevatedErrorRate_SEV3
        expr: |
          sum(rate(http_requests_total{status=~"5.."}[10m]))
          / sum(rate(http_requests_total[10m])) > 0.01
        for: 10m
        labels:
          severity: sev3
          page: "false"
        annotations:
          summary: "Error rate >1% for 10m — SEV3"
```

The `for` clause is the primary anti-flap mechanism. Never skip it on
automated severity rules.

### Service Criticality Override

Inject a `service_tier` label at scrape time:

```yaml
# prometheus.yml scrape config
- job_name: "api-gateway"
  static_configs:
    - targets: ["api-gateway:9090"]
      labels:
        service_tier: "1"
```

Then reference it in classification rules:

```yaml
- alert: AnyError_TierOne_SEV1
  expr: |
    rate(http_requests_total{status=~"5..", service_tier="1"}[2m]) > 0
    and on() hour() >= 6 and hour() <= 22
  for: 30s
  labels:
    severity: sev1
```

Tier-1 services get SEV1 on the first error during business hours because
their criticality warrants it.

### Cloudflare Workers Classification Worker

For edge-native stacks, a Tail Worker can classify before events reach
external alerting:

```typescript
// severity-classifier.ts  (Tail Worker)
import { TraceItem } from "@cloudflare/workers-types";

const THRESHOLDS = {
  sev1: { errorRate: 0.20, windowMs: 60_000 },
  sev2: { errorRate: 0.05, windowMs: 180_000 },
  sev3: { errorRate: 0.01, windowMs: 600_000 },
};

interface Env {
  ANALYTICS: AnalyticsEngineDataset;
  PAGERDUTY_ROUTING_KEY: string;
}

export default {
  async tail(events: TraceItem[], env: Env): Promise<void> {
    const errors = events.filter(
      (e) => e.outcome === "exception" || (e.response?.status ?? 200) >= 500
    );
    const errorRate = errors.length / Math.max(events.length, 1);

    let severity: string;
    if (errorRate >= THRESHOLDS.sev1.errorRate) {
      severity = "sev1";
    } else if (errorRate >= THRESHOLDS.sev2.errorRate) {
      severity = "sev2";
    } else if (errorRate >= THRESHOLDS.sev3.errorRate) {
      severity = "sev3";
    } else {
      return; // no incident
    }

    env.ANALYTICS.writeDataPoint({
      blobs: [severity, "classifier"],
      doubles: [errorRate],
      indexes: [severity],
    });

    if (severity === "sev1" || severity === "sev2") {
      await triggerPagerDuty(env.PAGERDUTY_ROUTING_KEY, severity, errorRate);
    }
  },
};

async function triggerPagerDuty(
  key: string,
  severity: string,
  errorRate: number
): Promise<void> {
  await fetch("https://events.pagerduty.com/v2/enqueue", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      routing_key: key,
      event_action: "trigger",
      payload: {
        summary: `${severity.toUpperCase()} — error rate ${(errorRate * 100).toFixed(1)}%`,
        severity: severity === "sev1" ? "critical" : "error",
        source: "cloudflare-tail-classifier",
      },
    }),
  });
}
```

## ML-Assisted Scoring Layer

Rules handle thresholds well but struggle with composite signals (slow AND
elevated errors AND unusual traffic pattern). A gradient-boosted tree trained
on historical incidents can score these cases.

Training data schema:

```
error_rate_p95  latency_p99  affected_user_pct  service_tier  hour_of_day  -> severity_label
```

Keep the model small (< 500 KB) so it can run inside a Worker or a CI step.
Export to ONNX or a plain JSON decision-tree structure for portability.

Key constraint: the ML score is advisory. Rules always override it for:
- SEV1 declarations (too high stakes for model error)
- service_tier=1 services
- data loss indicators

Log every classification decision with the signal values that drove it to a
separate audit log stream. Post-mortem analysis will use this to retrain.

## Automation Workflow

```
Alert fires
    │
    ▼
Classifier evaluates signals (rules then ML)
    │
    ├──► SEV1/SEV2 ─► PagerDuty trigger ─► On-call paged
    │                   └─► Status page draft created
    │                   └─► Incident channel #inc-YYYY-MM-DD-NNN opened
    │
    ├──► SEV3 ─► Ticket created in Linear/Jira ─► Slack notification
    │
    └──► SEV4 ─► Log only
```

Automate channel creation and status page drafts with webhooks from PagerDuty
into Slack and your status-page provider's API. The on-call engineer's first
action becomes verification, not triage.

## Anti-patterns

**Hardcoding thresholds in alerting DSL with no owner.** Classification rules
must be reviewed quarterly against actual incident data. Add a `# reviewed:
YYYY-MM-DD` comment above each rule group.

**Classifying on instantaneous values without `for`.** A single-sample spike
will page SEV1 on a transient. The `for` clause is mandatory.

**Applying the same thresholds across all services.** A payment processor with
1 error/min is SEV1; a background job with 50 errors/min may be SEV3. Use
service tiers and per-service threshold overrides, not universal rules.

**Skipping human confirmation for SEV1 auto-escalation.** Auto-create the
incident and page, but require the on-call to confirm or downgrade within 5
minutes. This prevents cascading noise during alert storms.

**Not recording classifier decisions.** If you cannot replay what the
classifier did and why, you cannot improve it. Always write classification
audit events to a durable store.

## Gotchas

- **Alert flapping defeats severity stability.** If an alert bounces between
  SEV2 and SEV3 every minute, responders lose trust. Use longer `for` windows
  and hysteresis (resolve only when error rate drops below 50 % of the trigger
  threshold for 5 minutes).
- **Time zone offsets on hour-of-day rules.** Store thresholds in UTC.
  Engineers in non-UTC zones must convert mentally. Document this explicitly.
- **PagerDuty deduplication keys.** Use a stable dedup key per incident so
  repeated classification events do not open duplicate incidents.
- **Severity escalation vs re-creation.** If a SEV3 incident worsens to SEV2,
  update the existing incident rather than creating a new one. Implement an
  escalation call to your incident management API.

## Verification

1. Inject synthetic error traffic at 25 %, 6 %, and 1.5 % rates in a staging
   environment. Confirm the correct severity fires within the expected `for`
   window.
2. Run a chaos test that spikes errors on a tier-1 service and verify SEV1
   pages within 90 seconds end-to-end.
3. Review the audit log after each real incident: does the auto-assigned
   severity match the post-mortem declared severity? Track the
   over-classification and under-classification rates.
4. Monthly: compare classifier accuracy (agreement with human override) and
   retrain ML model if agreement drops below 85 %.

## Related

- `alert-severity-levels.md`
- `escalation-policy-design.md`
- `workers-error-alerting-pagerduty-integration.md`
- `alert-grouping-patterns.md`
- `on-call-rotation-setup.md`

## Sources

- PagerDuty Incident Response Best Practices (2024)
- Prometheus Alerting Rules documentation
- Cloudflare Tail Workers documentation
- "Implementing AIOps for Incident Management" — SRE Weekly, 2024
- Google SRE Book, Chapter 14: Managing Incidents
