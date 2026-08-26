# casl-canada-compliance

**Issue:** Complying with Canada's Anti-Spam Legislation for email sent to Canadian recipients
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
CASL is stricter than CAN-SPAM; sending without express or implied consent to Canadians can result in fines up to CAD $10 million per violation.

## Pattern / Solution
CASL requires consent before sending commercial electronic messages (CEMs) to Canadian recipients.

**Express consent** — explicit opt-in with clear purpose disclosure:
- Unchecked checkbox on signup form
- Store: who consented, when, what they consented to, and how (form wording)
- No expiry on express consent unless withdrawn

**Implied consent** — limited-time window without explicit opt-in:
- Existing business relationship (purchase, inquiry): valid for 2 years
- Conspicuously published address (e.g., website contact page): 1 send allowed, add them to implied list
- Membership or volunteer relationship: valid for 2 years after end of relationship

Transition: if implied consent expires and no express consent obtained, stop sending.

Required message content:
- Sender identification (name, mailing address, and website or email)
- Unsubscribe mechanism (must work for at least 60 days after send)
- Unsubscribe must be processed within 10 business days

```python
def can_send_casl(subscriber, now=datetime.utcnow()):
    if subscriber.casl_express_consent_at and not subscriber.casl_withdrawn_at:
        return True
    if subscriber.casl_implied_consent_type == 'business_relationship':
        return (now - subscriber.casl_implied_consent_at) < timedelta(days=730)
    return False
```

## Gotchas
- CASL applies to the recipient's location, not the sender's — a US company sending to a Canadian address must comply
- The "conspicuously published address" implied consent does not require a prior relationship; however, the message must relate to the business function of that address
- CASL has a private right of action (individuals can sue senders); this is more aggressive than CAN-SPAM

## Related
- `gdpr-email-consent.md`
- `can-spam-compliance.md`
- `suppression-list-management.md`
