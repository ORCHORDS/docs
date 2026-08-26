# dmarc-ruf-forensic

**Issue:** Understanding and safely handling DMARC forensic (RUF) failure reports
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
You need per-message detail on authentication failures but are unsure how to handle the privacy implications of forensic reports.

## Pattern / Solution
RUF reports are sent per-failing-message as a MIME message (multipart/report with `message/feedback-report` and sometimes the original message attached).

Sample feedback-report body:
```
Feedback-Type: auth-failure
User-Agent: Feedback-Loop-Reporter/1.0
Version: 1
Original-Mail-From: sender@yourdomain.com
Arrival-Date: Mon, 11 Aug 2026 10:00:00 +0000
Source-IP: 192.0.2.45
Authentication-Results: dkim=fail; spf=fail
```

Key `fo=` values in your DMARC record:
- `fo=0` — report only when all auth mechanisms fail (default)
- `fo=1` — report on any auth failure
- `fo=d` — report on DKIM failure only
- `fo=s` — report on SPF failure only

Privacy handling:
- Many ISPs (notably Gmail) do not send RUF reports at all due to privacy policies
- Strip or redact recipient addresses before storing reports
- Consider a dedicated mailbox with limited access and short retention

## Gotchas
- RUF volume can be very high during a spoofing attack; set up rate-limiting on the destination mailbox
- The original message body may be included — treat this mailbox as confidential
- Not all receiving domains implement RUF; aggregate RUA is more universally supported

## Related
- `dmarc-rua-reporting.md`
- `dmarc-policy-setup.md`
