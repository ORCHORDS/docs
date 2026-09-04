# Security Logging Baseline Capability Review Template

Use this record to review whether a product provides the foundational security evidence customers need for detection and incident response as a baseline product capability.

## Review metadata

- Product/service: `<name>`
- Reviewer: `<role or team>`
- Review date: `<YYYY-MM-DD>`
- Baseline tier/configuration: `<description>`
- Log access/export mechanism: `<summary>`

## Security-event coverage

| Event class | Generated? | Enabled by default? | Baseline tier? | Actor/action/outcome present? | Evidence |
| --- | --- | --- | --- | --- | --- |
| Authentication | `<yes/no>` | `<yes/no>` | `<yes/no>` | `<result>` | `<reference>` |
| Authorization/privilege | `<yes/no>` | `<yes/no>` | `<yes/no>` | `<result>` | `<reference>` |
| Administrative configuration | `<yes/no>` | `<yes/no>` | `<yes/no>` | `<result>` | `<reference>` |
| Security-policy changes | `<yes/no>` | `<yes/no>` | `<yes/no>` | `<result>` | `<reference>` |
| Other product-specific intrusion evidence | `<yes/no>` | `<yes/no>` | `<yes/no>` | `<result>` | `<reference>` |

## Logging-quality checks

- [ ] Security-relevant events are generated without requiring a premium security add-on.
- [ ] Customers have a supported method to retrieve/export the logs for monitoring and incident response.
- [ ] Time information is sufficient to order/reconstruct relevant events.
- [ ] Actor, action, target/context, and result are recorded where appropriate to the event class.
- [ ] Access to logs is protected from unauthorized reading or modification.
- [ ] Default enablement and retention are documented product decisions rather than accidental platform defaults.
- [ ] Entitlement/tier changes cannot silently remove core intrusion evidence without an explicit compatibility/security decision.

## Incident simulation evidence

- Representative authentication event: `<reference/result>`
- Privilege/configuration change: `<reference/result>`
- Retrieval/export during incident exercise: `<reference/result>`
- Baseline-tier entitlement test: `<result>`

## Findings and actions

- Findings: `<text>`
- Corrective actions/owner/date: `<text>`
- Retest result: `<result>`

## Sources

- NSA/CISA, Top Ten Cybersecurity Misconfigurations — high-quality audit logs at no extra charge: https://www.cisa.gov/news-events/cybersecurity-advisories/aa23-278a
- CISA, expanded logging capabilities and security data by default: https://www.cisa.gov/news-events/news/cisa-omb-oncd-and-microsoft-efforts-bring-new-logging-capabilities-federal-agencies
- CISA, Logging on Business Systems: https://www.cisa.gov/audiences/small-and-medium-businesses/secure-your-business/use-logging-on-business-systems
