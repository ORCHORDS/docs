# victorops-patterns

**Issue:** Using VictorOps (Splunk On-Call) for incident routing and war room coordination
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Teams using the Splunk ecosystem may prefer VictorOps for native integration with Splunk alerts and log-based alerting.

## Pattern / Solution
Configure VictorOps REST endpoint integration in Alertmanager using victorops_configs. Set routing_key to map to escalation policy. Use message_type field to set severity (CRITICAL, WARNING, INFO, ACKNOWLEDGEMENT, RECOVERY). VictorOps war rooms aggregate related incidents into a single timeline with chat. Configure Splunk saved search to route alerts directly to VictorOps.

## Gotchas
VictorOps merged into Splunk On-Call; API is backward compatible. Timeline view is powerful for post-mortems. ACKNOWLEDGEMENT and RECOVERY message types close incidents automatically. Rotation schedules are less flexible for complex multi-timezone teams.

## Related
pagerduty-integration, opsgenie-setup, on-call-rotation-setup, escalation-policy-design
