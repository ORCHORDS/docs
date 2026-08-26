# complaint-rate-monitoring

**Issue:** Tracking and responding to spam complaint (FBL) signals from ISPs
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Recipients mark your email as spam. Above threshold rates trigger ISP throttling or blocking.

## Pattern / Solution
**Feedback Loop (FBL) setup**
Register with each ISP's FBL program:
- Yahoo/AOL: `postmaster.yahooinc.com/mail/services/fbl`
- Microsoft: enrollment via SNDS
- Gmail: does not offer FBL; use Postmaster Tools spam rate metric instead

FBL reports arrive as Abuse Reporting Format (ARF) messages. Parse them:
```python
import email
def parse_arf(raw_message: bytes) -> dict:
    msg = email.message_from_bytes(raw_message)
    for part in msg.walk():
        if part.get_content_type() == 'message/feedback-report':
            payload = part.get_payload(decode=True).decode()
            lines = dict(line.split(': ', 1) for line in payload.splitlines() if ': ' in line)
            return {
                'original_recipient': lines.get('Original-Rcpt-To'),
                'feedback_type': lines.get('Feedback-Type'),  # 'abuse'
            }
```

Immediately unsubscribe the reported recipient from all marketing lists.

Thresholds (Google/Yahoo 2024 sender requirements):
- `< 0.10%` — acceptable
- `0.10%–0.30%` — warning zone; deliverability starts degrading
- `> 0.30%` — severe; expect blocking

## Gotchas
- FBL emails may have the recipient address hashed (Yahoo hashes to protect privacy); you need to maintain a hash map of sent mail
- Complaint rate is per campaign, not just overall; a single poorly targeted blast can spike the rate
- One-click unsubscribe (RFC 8058) significantly reduces complaint rates because users have a friction-free alternative to hitting spam

## Related
- `list-unsubscribe-header.md`
- `suppression-list-management.md`
- `email-sunset-policy.md`
