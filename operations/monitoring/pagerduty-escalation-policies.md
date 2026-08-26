# PagerDuty Escalation Policies: Design and Automation

- **Date**: 2026-08-22
- **Author**: example.com
- **Status**: production

## Symptom / Use-case

Alerts are routing to the wrong people, or to no one. A P1 incident fires at 3 AM, the first responder does not acknowledge within 5 minutes, but the escalation goes to someone who has no context for that service. Alternatively, every alert page-bombards the entire engineering team because there is only one "catch-all" policy. You need a structured escalation model — layered response targets, service-specific ownership, and clear escalation timing — managed as code rather than clicked together in the PagerDuty UI.

## Context

A PagerDuty escalation policy is the bridge between an incoming alert (arriving via the Events API or an integration) and the humans responsible for resolving it. A policy contains one or more **escalation rules**, each specifying:

1. **Targets** — users, schedules, or teams to notify (multiple targets within a rule are notified simultaneously).
2. **Escalation delay** — how many minutes to wait for acknowledgment before moving to the next rule.
3. **Repeat count** — how many times the full policy loops before the incident stays unacknowledged permanently.

Each PagerDuty **service** is connected to exactly one escalation policy. One policy can be shared across multiple services, but tight coupling makes policy changes risky. Prefer one policy per service or per service tier.

## Designing a Three-Tier Escalation Model

The most maintainable model for a small-to-medium engineering team:

- **Tier 1 (Rule 1)** — primary on-call schedule for the owning team. Notified immediately. Acknowledgment window: 5 minutes.
- **Tier 2 (Rule 2)** — secondary on-call (senior engineer or backup schedule). Acknowledgment window: 10 minutes.
- **Tier 3 (Rule 3)** — engineering manager or incident commander. Acknowledgment window: 15 minutes.

For P1/critical incidents (SEV-1): loop the policy once (repeat_enabled: true) before leaving the incident unacknowledged.
For P2/warning incidents: no loop; let the incident sit unacknowledged and surface via daily digest.

## Creating Escalation Policies via the PagerDuty REST API

Managing policies via API enables GitOps-style change control and CI/CD-driven on-call configuration.

```bash
# List existing escalation policies
curl -s \
  "https://api.pagerduty.com/escalation_policies?limit=25" \
  -H "Authorization: Token token=${PD_API_TOKEN}" \
  -H "Accept: application/vnd.pagerduty+json;version=2" \
  | jq '.escalation_policies[] | {id, name, num_loops}'
```

```bash
# Create a three-tier policy
curl -s -X POST \
  "https://api.pagerduty.com/escalation_policies" \
  -H "Authorization: Token token=${PD_API_TOKEN}" \
  -H "Accept: application/vnd.pagerduty+json;version=2" \
  -H "Content-Type: application/json" \
  -H "From: ops@example.com" \
  -d '{
    "escalation_policy": {
      "name": "API Platform On-Call",
      "description": "Three-tier escalation for the API platform service tier",
      "num_loops": 1,
      "on_call_handoff_notifications": "if_has_services",
      "escalation_rules": [
        {
          "escalation_delay_in_minutes": 5,
          "targets": [
            {
              "id": "<PRIMARY_SCHEDULE_ID>",
              "type": "schedule_reference"
            }
          ]
        },
        {
          "escalation_delay_in_minutes": 10,
          "targets": [
            {
              "id": "<SECONDARY_SCHEDULE_ID>",
              "type": "schedule_reference"
            }
          ]
        },
        {
          "escalation_delay_in_minutes": 15,
          "targets": [
            {
              "id": "<EM_USER_ID>",
              "type": "user_reference"
            },
            {
              "id": "<INCIDENT_COMMANDER_TEAM_ID>",
              "type": "team_reference"
            }
          ]
        }
      ],
      "teams": [
        { "id": "<API_TEAM_ID>", "type": "team_reference" }
      ]
    }
  }'
```

Key fields:

- `num_loops` — how many times the full policy repeats after reaching the last rule without acknowledgment. `1` means it runs through once more. `0` means no repeat.
- `on_call_handoff_notifications` — `"if_has_services"` sends handoff notifications only to engineers on call for services attached to this policy. `"always"` notifies even for policies with no services.
- Tier 3 uses both a user and a team as targets — both are notified simultaneously when Tier 2 escalation delay expires.

## Attaching the Policy to a Service

```bash
# Patch an existing service to use the new escalation policy
curl -s -X PUT \
  "https://api.pagerduty.com/services/${PD_SERVICE_ID}" \
  -H "Authorization: Token token=${PD_API_TOKEN}" \
  -H "Accept: application/vnd.pagerduty+json;version=2" \
  -H "Content-Type: application/json" \
  -H "From: ops@example.com" \
  -d '{
    "service": {
      "escalation_policy": {
        "id": "<POLICY_ID>",
        "type": "escalation_policy_reference"
      }
    }
  }'
```

## Routing Rules and Alert Grouping by Severity

PagerDuty **Event Orchestration** (formerly Rulesets) lets you inspect incoming alert payloads and route to different services — and thus different escalation policies — based on severity, source, or custom fields. This is the key mechanism for multi-tier escalation: P1 alerts go to the "high-urgency" service (5-minute escalation policy); P2 alerts go to the "low-urgency" service (60-minute delay or no page at all).

```json
// Event Orchestration rule example (Terraform-style pseudo-JSON)
{
  "actions": {
    "route_to": "<P2_SERVICE_ID>",
    "severity": "warning",
    "suppress": false,
    "annotate": "Routed to low-urgency service by severity=warning rule"
  },
  "conditions": [
    {
      "expression": "event.severity matches 'warning'"
    }
  ]
}
```

```json
{
  "actions": {
    "route_to": "<P1_SERVICE_ID>",
    "severity": "critical",
    "priority": { "id": "<P1_PRIORITY_ID>", "type": "priority_reference" },
    "suppress": false
  },
  "conditions": [
    {
      "expression": "event.severity matches 'critical'"
    }
  ]
}
```

Use the PagerDuty Terraform provider for managing orchestration rules in version control:

```hcl
resource "pagerduty_event_orchestration_global_cache_variable" "region" {
  event_orchestration = pagerduty_event_orchestration.global.id
  name                = "source_region"
  configuration {
    type  = "recent_value"
    regex = "region=([a-z]+-[0-9])"
    source = "event.source"
    ttl_seconds = 3600
  }
}

resource "pagerduty_event_orchestration_global" "routing" {
  event_orchestration = pagerduty_event_orchestration.global.id

  set {
    id = "start"
    rule {
      condition {
        expression = "event.severity matches 'critical'"
      }
      actions {
        route_to = "P1"
      }
    }
    rule {
      condition {
        expression = "event.severity matches 'warning' or event.severity matches 'info'"
      }
      actions {
        route_to = "P2"
      }
    }
  }
}
```

## Automating Policy Audits

Escalation policies can drift from their documented state if engineers update them via the UI. Run a scheduled audit Worker (or CI job) that compares the live API state against a committed policy definition.

```javascript
// audit/src/index.js
const EXPECTED_POLICIES = {
  'API Platform On-Call': {
    num_loops: 1,
    escalation_rules_count: 3,
    escalation_delays: [5, 10, 15],
  },
  'Data Pipeline On-Call': {
    num_loops: 0,
    escalation_rules_count: 2,
    escalation_delays: [10, 20],
  },
};

export default {
  async scheduled(event, env) {
    const resp = await fetch(
      'https://api.pagerduty.com/escalation_policies?limit=100',
      {
        headers: {
          Authorization: `Token token=${env.PD_API_TOKEN}`,
          Accept: 'application/vnd.pagerduty+json;version=2',
        },
      }
    );
    const { escalation_policies: policies } = await resp.json();

    const drifts = [];

    for (const [name, expected] of Object.entries(EXPECTED_POLICIES)) {
      const live = policies.find((p) => p.name === name);

      if (!live) {
        drifts.push({ policy: name, issue: 'MISSING' });
        continue;
      }

      if (live.num_loops !== expected.num_loops) {
        drifts.push({
          policy: name,
          issue: `num_loops is ${live.num_loops}, expected ${expected.num_loops}`,
        });
      }

      if (live.escalation_rules.length !== expected.escalation_rules_count) {
        drifts.push({
          policy: name,
          issue: `has ${live.escalation_rules.length} rules, expected ${expected.escalation_rules_count}`,
        });
      }

      const delays = live.escalation_rules.map((r) => r.escalation_delay_in_minutes);
      if (JSON.stringify(delays) !== JSON.stringify(expected.escalation_delays)) {
        drifts.push({
          policy: name,
          issue: `escalation delays are [${delays}], expected [${expected.escalation_delays}]`,
        });
      }
    }

    if (drifts.length > 0) {
      await sendSlackAlert(drifts, env);
    }

    // Emit audit metric
    env.ANALYTICS.writeDataPoint({
      blobs: ['escalation-policy-audit'],
      doubles: [drifts.length, Object.keys(EXPECTED_POLICIES).length],
      indexes: ['audit'],
    });
  },
};
```

## Schedule Design for Escalation Targets

A policy is only as good as the on-call schedule it points to. Key schedule design rules:

- **Rotation type** — weekly rotation is standard; daily rotations cause fatigue. Use weekly with a Monday handoff.
- **Restrictions** — use `rendered_schedule_entries` with restrictions to limit pages to business hours for P2/P3 services.
- **Overrides** — always use API-managed overrides for PTO, not manual schedule edits, so the override is auditable.

```bash
# Create a schedule override (PTO coverage)
curl -s -X POST \
  "https://api.pagerduty.com/schedules/${SCHEDULE_ID}/overrides" \
  -H "Authorization: Token token=${PD_API_TOKEN}" \
  -H "Accept: application/vnd.pagerduty+json;version=2" \
  -H "Content-Type: application/json" \
  -H "From: ops@example.com" \
  -d '{
    "override": {
      "start": "2026-09-01T00:00:00Z",
      "end": "2026-09-08T00:00:00Z",
      "user": {
        "id": "<COVERAGE_USER_ID>",
        "type": "user_reference"
      }
    }
  }'
```

## Anti-patterns

- **Single "catch-all" escalation policy** — one policy for all services means one misconfiguration can affect every service. Every service tier should have its own policy.
- **User references instead of schedule references in Tier 1** — pointing directly at a user bypasses rotation and will page the same person indefinitely, including during PTO.
- **Setting `num_loops` to a high number for P2 alerts** — looping a P2 alert three times with 60-minute delays means an alert can be active for 3 hours before it expires. This inflates incident count and burns on-call goodwill. For P2, set `num_loops: 0` and review via daily unacknowledged incident report.
- **Not attaching a team to the policy** — without a `teams` field, the policy is not visible in team-filtered views and won't appear in team-scoped dashboards.

## Gotchas

- **Simultaneous targets in a rule are not redundant** — all simultaneous targets in a rule receive the notification; the first to acknowledge resolves the escalation for that rule. This is intentional (secondary on-call can also acknowledge), but it means two people may respond to the same alert. Establish "ACK etiquette" in the runbook.
- **`num_loops: 1` means the policy runs twice total** — it loops once, meaning the sequence runs, then runs again. A value of `0` means one pass with no repeat.
- **Event Orchestration routing overrides service-level escalation policy** — if you use a global orchestration to route to a different service, the policy attached to the *destination* service applies, not the one attached to the event's original source service.
- **PagerDuty API rate limit** — the REST API is limited to 960 requests per minute per account. Bulk policy audits should be batched and throttled; each `GET /escalation_policies` page returns up to 100 records.

## Verification

1. Create a test service with the new policy attached.
2. Trigger a test incident via the Events API with `event_action: trigger`.
3. Wait 5 minutes without acknowledging — confirm Tier 2 is notified.
4. Wait another 10 minutes — confirm Tier 3 is notified.
5. Run the audit Worker and confirm zero drift is reported.
6. Introduce a deliberate drift (change `num_loops` via the dashboard) and re-run the audit — confirm a Slack alert fires.

## Related

- `escalation-policy-design.md` — conceptual escalation design principles
- `on-call-rotation-setup.md` — PagerDuty schedule configuration
- `on-call-handoff-checklist.md` — handoff procedures for schedule transitions
- `workers-error-alerting-pagerduty-integration.md` — routing Worker errors to PagerDuty
- `alerting-strategy-routing-escalation.md` — multi-layer alert routing architecture

## Sources

- PagerDuty Escalation Policies API: https://developer.pagerduty.com/api-reference/YXBpOjExMDI5NTUy-pager-duty-api#tag/Escalation-Policies
- PagerDuty Terraform provider: https://registry.terraform.io/providers/PagerDuty/pagerduty/latest/docs
- PagerDuty Event Orchestration: https://support.pagerduty.com/docs/event-orchestration
- PagerDuty on-call schedule restrictions: https://support.pagerduty.com/docs/schedule-basics
