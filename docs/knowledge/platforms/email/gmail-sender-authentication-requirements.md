# gmail-sender-authentication-requirements

**Issue:** Mail to Gmail can be rejected or spam-foldered when sender authentication is incomplete or misaligned.
**Date:** 2026-08-26
**Status:** documented
**Source:** https://support.google.com/mail/answer/81126

## Context
Google's sender guidelines require authentication for mail sent to Gmail accounts. Google states that all senders need SPF or DKIM, while bulk senders need SPF, DKIM, and DMARC.

## Pattern
For every active sending domain:
- publish and validate SPF for legitimate sending infrastructure
- enable DKIM signing with the sending provider
- publish a DMARC policy and monitor reports
- keep the visible From domain aligned with authenticated identities where required
- authenticate each distinct sending domain rather than assuming one parent-domain setup covers everything

## Operational checks
- Confirm SPF stays within DNS lookup limits after provider changes.
- Rotate DKIM keys according to provider capability and organizational policy.
- Monitor DMARC aggregate reports for unexpected senders.
- Remove obsolete providers from SPF and DKIM configuration after migrations.
- Test transactional and marketing streams independently if they use different providers or subdomains.

## Failure signal
Google documents that messages failing authentication can be rejected or marked as spam, including 5.7.26 authentication-related failures.

## Security rationale
Sender authentication reduces spoofing and impersonation risk and improves confidence that mail came from infrastructure authorized by the domain owner. It is not a substitute for abuse monitoring, list hygiene, rate management, or secure account access.

## Verification
Send controlled test messages to Gmail and inspect message authentication results for SPF, DKIM, and DMARC. Repeat after DNS, provider, or domain changes.

## Related
- `spf-record-setup.md`
- `dkim-signing.md`
- `dmarc-policy.md`
- `email-deliverability.md`
