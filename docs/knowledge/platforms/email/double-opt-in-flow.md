# double-opt-in-flow

**Issue:** Implementing confirmed opt-in to ensure address validity and consent
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Single opt-in allows typos, fake addresses, and addresses submitted by third parties without consent, leading to bounces and complaints.

## Pattern / Solution
Flow:
1. User submits email on signup form
2. Save address with `status = 'pending'`; generate time-limited confirmation token
3. Send confirmation email immediately (from transactional sending path)
4. User clicks link → set `status = 'confirmed'`, log timestamp and IP
5. Expire unconfirmed records after 48–72 hours

Token generation:
```python
import secrets, hashlib, time

def generate_confirm_token(email: str, secret: str) -> str:
    nonce = secrets.token_hex(16)
    payload = f"{email}:{nonce}:{int(time.time())}"
    sig = hashlib.sha256(f"{payload}:{secret}".encode()).hexdigest()
    return f"{nonce}.{sig}"
```

Confirmation email subject line: "Confirm your subscription to [Brand]" — keep it neutral and clear.

Database schema addition:
```sql
ALTER TABLE subscribers ADD COLUMN confirm_token TEXT;
ALTER TABLE subscribers ADD COLUMN confirm_token_expires_at TIMESTAMPTZ;
ALTER TABLE subscribers ADD COLUMN confirmed_at TIMESTAMPTZ;
ALTER TABLE subscribers ADD COLUMN confirm_ip INET;
```

## Gotchas
- Do not send any marketing email until confirmed; send only the confirmation message
- Track the confirmation rate; a rate below 40% suggests form abuse or a poor signup experience
- Store `confirmed_at` and `confirm_ip` as GDPR evidence of consent
- Resend confirmation: allow one resend per 10 minutes to prevent abuse

## Related
- `single-opt-in-tradeoffs.md`
- `gdpr-email-consent.md`
- `email-list-hygiene.md`
