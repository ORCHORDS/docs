# waf-managed-rules-exception-order-and-future-rule-drift

**Issue:** A Cloudflare WAF managed-rules exception either does not apply or silently fails to cover future rule changes.
**Date:** 2026-08-11
**Author:** ORCHORDS
**Status:** documented

## Root cause

Managed-rule overrides and skip exceptions have execution order and scope. An exception placed after the managed-rules execution cannot protect the intended request; a rule-specific override may not cover future rules in the same ruleset/category.

**Source:** [Cloudflare WAF managed rules](https://developers.cloudflare.com/waf/managed-rules/).

## Fix

- identify the smallest legitimate traffic pattern requiring an exception;
- place skip/exception logic before managed-rules execution;
- choose ruleset/tag-level versus individual-rule scope intentionally;
- add expiration, owner, justification, and review date to every exception;
- validate representative legitimate traffic and malicious/negative traffic in a controlled rollout;
- monitor Security Events after managed-rules updates for drift.

## Verification

- The intended legitimate request is handled as documented.
- Unrelated malicious traffic remains inspected/blocked.
- A future ruleset update is reviewed against the exception scope.
- Expired exceptions are removed or renewed with evidence.

## Related

- `cloudflare/api-shield-schema-validation-2-rollout.md`
- `cloudflare/waf-rate-limiting-deep-dive.md`
