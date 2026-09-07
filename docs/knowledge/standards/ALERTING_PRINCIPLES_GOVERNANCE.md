# Alerting Principles Governance

## 1. Scope
This standard defines how teams author, route, and operate alerts
across the platform so that on-call engineers receive timely,
actionable notifications and minimise alert fatigue.

It applies to alerts produced by Prometheus, Alertmanager, Grafana
unified alerting, and any downstream notification integration
(PagerDuty, Slack, email, webhook). It does not override service-
specific alerting policies documented in service runbooks.

## 2. Normative references
The following documents are referenced and inform the requirements of
this standard:

- Google SRE Book, Chapter 5 (Alerting on SLOs) and Chapter 8 (Alerting
  Principles).
- Prometheus alerting adoption playbook.
- Platform Prometheus and Grafana version governance cards.
- Platform on-call rotation and incident response governance.

## 3. Terms and definitions
For the purposes of this standard, the following terms apply:

- **Symptom-based alert**: an alert triggered by a user-visible
  symptom such as elevated error rate or latency.
- **Cause-based alert**: an alert triggered by an internal condition
  such as CPU saturation or disk pressure.
- **Burn-rate alert**: an alert triggered by the rate at which an
  error budget is being consumed.
- **Page**: a notification routed to an on-call responder that
  interrupts their current activity.

## 4. Alert philosophy
Teams MUST prioritise symptom-based alerts that reflect user impact.
Cause-based alerts MAY be used as supporting signals but MUST NOT
page on-call responders directly unless paired with a documented
user-visible impact.

## 5. SLO-aligned alerting
Alerts at severity `page` MUST be aligned with SLO burn-rate
thresholds documented in the SLI/SLO practice governance standard.
Alerts MUST include runbook links, dashboard links, and impact
statements in their payload.

## 6. Routing and ownership
Every alert MUST be associated with an owning service, an on-call
rotation, and a routing key in Alertmanager. Unowned alerts MUST NOT
be promoted to production.

## 7. Alert hygiene
Each team MUST review its alert inventory at least quarterly and
remove alerts that have not fired in the previous 180 days or that
have been consistently silenced. False-positive rate MUST be tracked
per alert and alerts exceeding the agreed false-positive budget MUST
be redesigned or retired.

## 8. Notification channels
Pages MUST be delivered through the agreed PagerDuty integration
with acknowledgement and escalation policy configured. Slack and
email MAY be used as secondary channels for lower-severity alerts.

## 9. Silence policy
Silences MUST be scoped to the smallest possible matchers and
expiry window. Long-running silences MUST be tracked in the alert
register and reviewed before renewal.

## 10. Testing and validation
New alerts MUST be validated against synthetic traffic or chaos
exercises before promotion to production. Alert payloads MUST be
reviewed for sensitive data leakage and stripped before delivery
where required.

## 11. Roles and responsibilities
Service owners are accountable for the alert inventory and
documentation associated with their services. The platform
observability team owns Alertmanager routing and notification
integrations. The incident response team owns the on-call rotation
policy.

## 12. Audit and evidence
Alert definitions, routing configuration, and silence records MUST
be retained for at least 24 months in the versioned configuration
repository.

## 13. Review cycle
This standard is reviewed at least annually or when material changes
occur in alerting tooling, on-call policy, or upstream SRE practice.

---

This card is reviewed every 180 days. The next scheduled review is 2027-03-07.
