# gdpr-breach-notification-72h

**Issue:** Meeting the 72-hour supervisory authority notification deadline after discovering a personal data breach (GDPR Art. 33)
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Controllers must notify their lead supervisory authority within 72 hours of becoming "aware" of a personal data breach — unless the breach is unlikely to result in risk to individuals. The clock starts at awareness, not at discovery by a technical team. Most teams fail because: (a) internal escalation is slow, (b) they wait until investigation is complete before notifying, or (c) they underestimate what counts as a "breach."

## Pattern / Solution
**What counts as a breach:** Any accidental or unlawful destruction, loss, alteration, unauthorised disclosure of, or access to personal data. This includes: misconfigured S3 bucket, lost laptop, accidental CC on an email, SQL injection exfiltration.

**72-hour response playbook:**

| Hour | Action |
|---|---|
| 0 | Incident confirmed → immediately page DPO and security lead |
| 0–4 | Contain the breach; preserve evidence; begin impact assessment |
| 4–12 | DPO makes initial risk assessment (low / medium / high risk to individuals) |
| 12–24 | If medium or high risk: draft initial SA notification (can be partial/incomplete) |
| 24–48 | File notification with SA via their online portal; state that investigation is ongoing |
| 48–72 | Submit updated notification with complete details as they become available |
| 72+ | Notify affected individuals if "high risk" (Art. 34); document all decisions |

**SA notification minimum content (Art. 33(3)):**
```
1. Nature of the breach (categories, approximate number of records and data subjects affected)
2. Name and contact details of the DPO
3. Likely consequences of the breach
4. Measures taken or proposed to address the breach
```

You can submit an initial notification with fields marked "under investigation" and supplement later. Filing late is better than not filing.

**Internal breach register (Art. 33(5)) — required regardless of notification:**
```json
{
  "breach_id": "BR-2026-042",
  "discovered_at": "2026-08-11T09:15:00Z",
  "aware_at": "2026-08-11T09:15:00Z",
  "nature": "Unauthorised access via credential stuffing",
  "categories_affected": ["email", "hashed_password"],
  "records_affected_approx": 1200,
  "risk_level": "medium",
  "notified_sa": true,
  "sa_notification_at": "2026-08-12T14:30:00Z",
  "notified_individuals": false,
  "rationale_no_individual_notification": "Risk mitigated by password hashing"
}
```

## Gotchas
- "Awareness" is the moment any employee with authority knew — not when the DPO was formally briefed. Train all staff to escalate immediately.
- Low-risk breaches (e.g., encrypted device lost, data minimised) do not require SA notification but **must** still be recorded internally.
- If you have customers in multiple EU member states, identify your lead SA (one-stop-shop) in advance — typically the SA of your EU establishment.
- Notification portals differ by country; pre-register an account before you need it.
- US-style breach notification laws run in parallel and may have shorter or different timelines (e.g., some US states require 30-day notification).

## Related
- `gdpr-data-breach-notification.md`
- `security-incident-response-plan.md`
- `audit-log-mandatory.md`
- `gdpr-data-subject-rights-api.md`
