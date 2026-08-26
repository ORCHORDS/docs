# gdpr-dpo-role-requirements

**Issue:** Determining when a Data Protection Officer is mandatory and what the role requires
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
GDPR Articles 37 to 39 mandate a DPO for public bodies, organizations doing large-scale systematic monitoring, and large-scale processing of special-category data. Many organizations appoint one voluntarily or to satisfy contractual requirements.

## Pattern / Solution
Mandatory triggers (Art. 37(1)):
- Public authority or body
- Core activities involve large-scale systematic monitoring (ad networks, telcos, surveillance)
- Core activities involve large-scale processing of special-category or criminal conviction data

DPO tasks (Art. 39):
1. Inform and advise controller/processors and staff of GDPR obligations
2. Monitor compliance: assign responsibilities, conduct audits, raise awareness
3. Advise on and monitor Data Protection Impact Assessments (Art. 35)
4. Cooperate with and act as contact point for the supervisory authority
5. Serve as contact for data subjects on rights requests

Structural requirements:
- Reports directly to highest management (board level)
- Cannot be dismissed or penalized for performing duties
- Must have no conflict of interest (DPO cannot also be CISO/CTO who decides processing purposes)
- Contact details published and registered with national DPA
- Provided adequate resources and access to data/systems

DPO can be external contractor — formalize with a written services agreement.

## Gotchas
- Voluntarily appointed DPO has same legal protections — cannot demote if GDPR tasks are assigned
- Multiple organizations may share one DPO if accessible from each entity
- National DPAs can mandate DPO even where thresholds are not met
- DPO designation must be communicated to supervisory authority (varies by member state — some require formal notification)

## Related
- `gdpr-privacy-notice-template.md`
- `gdpr-data-breach-notification.md`
