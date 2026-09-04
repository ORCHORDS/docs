# Network Device Configuration Source-of-Truth Review Template

Use this record to review configuration governance, drift detection, and unauthorized-change alerting for managed network devices. Keep actual production configurations and sensitive topology in protected systems.

## Review metadata

- Device/network class: `<class>`
- Reviewer: `<role or team>`
- Review date: `<YYYY-MM-DD>`
- Authoritative configuration repository/system: `<system class>`
- Change-management reference: `<reference>`

## Configuration governance

| Device/config class | Central source of truth? | Device copy treated as authoritative? | Approved deployment path | Drift detection | Unauthorized-change alerting | Evidence |
| --- | --- | --- | --- | --- | --- | --- |
| `<class>` | `<yes/no>` | `<yes/no>` | `<path/process>` | `<method>` | `<method>` | `<reference>` |

## Review checks

- [ ] Configurations are stored centrally under controlled access and change management.
- [ ] A managed device is not the sole trusted source of truth for its intended configuration.
- [ ] Normal configuration changes are traceable to an approved change, identity, and timestamp.
- [ ] Monitoring detects device changes made outside the approved configuration/deployment path.
- [ ] Alerts cover security-relevant changes such as users, ACLs, routing, management services, and enabling weak/unapproved protocols.
- [ ] Drift is compared against the intended central state at a defined cadence or event trigger.
- [ ] The organization can restore or reapply the approved configuration after unauthorized drift.
- [ ] Backup/configuration records are protected from unauthorized modification.

## Drift exercise

- Controlled test change: `<non-sensitive description>`
- Expected alert/detection: `<expected>`
- Detection result: `<result>`
- Source-of-truth comparison result: `<result>`
- Approved-state restoration result: `<result>`
- Time to detection/restoration: `<values>`

## Findings and actions

- Unmanaged configuration paths: `<text>`
- Alerting gaps: `<text>`
- Devices without central authoritative state: `<text>`
- Corrective actions/owner/date: `<text>`

## Source

- CISA, Enhanced Visibility and Hardening Guidance for Communications Infrastructure: https://www.cisa.gov/resources-tools/resources/enhanced-visibility-and-hardening-guidance-communications-infrastructure
