# gdpr-data-portability-export

**Issue:** Implementing GDPR Article 20 data portability endpoints
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Data subjects have the right to receive data they provided in a structured, commonly used, machine-readable format. Portability also includes the right to transmit data directly to another controller.

## Pattern / Solution
API endpoint pattern (REST):

```
GET /api/v1/me/export
Authorization: Bearer <token>
Accept: application/json
```

Response: 202 Accepted with job ID; deliver ZIP via email or polling endpoint within 30 days.

Export package contents (JSON + CSV):
- Profile data (provided by subject)
- Transaction/activity records (observed data)
- Preferences and settings
- Consent records with timestamps
- Communications sent

Exclude from export:
- Inferred/derived attributes (e.g., predicted churn score)
- Data about third parties
- Data processed under legal obligation basis

Machine-to-machine transfer (Art. 20(2)):
Provide a standardized endpoint where another controller can pull data with subject authorization (OAuth2 token issued to receiving controller).

Audit every export: log user ID, timestamp, IP, export format.

## Gotchas
- Portability applies only to consent and contract bases — not legitimate interest
- Format must be machine-readable (JSON/CSV), not PDF or human-readable only
- 30-day window starts from validated request receipt, not submission
- If the export would reveal other persons data, redact or exclude it

## Related
- `gdpr-data-subject-rights-api.md`
- `gdpr-article-17-erasure.md`
