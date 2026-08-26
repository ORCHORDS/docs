# inbound-email-processing

**Issue:** Architecting reliable processing pipelines for inbound email
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Applications that receive email need to parse, validate, route, and process messages reliably without losing emails.

## Pattern / Solution
Architecture:
1. MX -> ESP inbound webhook (Postmark, Mailgun, SendGrid Inbound Parse) -> your HTTPS endpoint.
2. Endpoint acknowledges 200 immediately, enqueues message to queue (SQS, BullMQ, etc.).
3. Worker processes: parse headers, validate sender, extract body, handle attachments.
4. Apply routing logic: match to user/ticket/record.
5. Dead-letter queue for processing failures with alerting.

Validation steps:
- Verify webhook signature (prevent spoofing).
- Validate sender is allowed (allowlist or domain check).
- Sanitize HTML body before storage (XSS prevention).
- Scan attachments for malware before processing.

## Gotchas
- ESPs retry webhooks on 5xx; ensure idempotent processing using message ID.
- Parsing MIME manually is error-prone; use libraries (mailparser, email-reply-parser).
- Thread detection: use `In-Reply-To` and `References` headers to correlate threads.

## Related
- postmark-inbound-email, email-to-ticket-pattern, email-parsing-patterns, email-catch-all-patterns
