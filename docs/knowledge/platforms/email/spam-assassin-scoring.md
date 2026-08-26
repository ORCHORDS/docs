# spam-assassin-scoring

**Issue:** Understanding SpamAssassin scoring to diagnose deliverability issues
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
SpamAssassin is used by many ISPs and mail gateways; understanding its scoring helps debug filtering.

## Pattern / Solution
Score threshold: messages scoring >= 5 are marked spam by default (varies by server config).

Key rules and typical scores:
- `NO_RECEIVED` (+1.2): No Received headers
- `HTML_MESSAGE` (+0.0): HTML present (neutral, but adds to other scores)
- `BAYES_99` (+3.5): Bayesian classifier confident it's spam
- `MISSING_HEADERS` (+2.0): Missing Date or From header
- `SPF_FAIL` (+5.0): SPF check failed
- `DKIM_INVALID` (+0.1): DKIM signature invalid

Test tools:
- `spamassassin -t < email.eml` locally
- mail-tester.com for online scoring
- MXToolbox Email Health Check

## Gotchas
- Bayesian filter score depends on the receiving server's training data; your score may vary per server.
- Passing SPF and DKIM reduces many negative rules automatically.
- HTML-only emails add several points; plain text alternative reduces score.

## Related
- email-spam-triggers, email-content-guidelines, email-authentication-check-tools, email-deliverability-audit
