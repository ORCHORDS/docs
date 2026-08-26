# alerting-runbook-linking

**Issue:** Attaching runbook URLs to alerts so on-call engineers know exactly what to do
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Alert fires at 3am; engineer has no context on what it means or how to respond. Time to resolution increases.

## Pattern / Solution
Add runbook_url annotation to every Prometheus alert rule. Format the URL to include the alertname. For PagerDuty/OpsGenie, include runbook link in incident description template. Maintain runbooks in version control alongside alert definitions. Runbook template: symptom, likely causes, diagnostic commands, remediation steps, escalation path, rollback procedure.

## Gotchas
Stale runbooks are worse than no runbooks — schedule quarterly runbook reviews. Link runbooks from the alert, not the other way around. Keep runbooks short and actionable. Test runbooks during game days before real incidents.

## Related
alert-severity-levels, pagerduty-integration, on-call-rotation-setup, escalation-policy-design
