# data-minimization-reduces-breach-impact

**Issue:** Collecting more data than necessary increases the scope and severity of any breach
**Date:** 2026-08-11
**Status:** documented

## What happened
An e-commerce site collected full date of birth, phone number, and gender "for personalization" but used none of it functionally. When the database was breached, the attacker obtained these fields for 2 million users. The additional fields elevated the breach from a "contact data exposure" (low regulatory impact) to a "sensitive personal data exposure" requiring individual notification to every affected user in multiple jurisdictions.

## The lesson
Only collect personal data that you actively use for a stated purpose. Every additional field is liability, not asset. Data you do not have cannot be stolen. Review your schema for "nice to have" fields and delete them.

## Why it matters
Regulatory breach notification requirements, fines, and reputational damage scale with the sensitivity of data exposed. Minimizing collection is the most effective way to limit the cost of a breach you haven't had yet.

## How to apply
- [ ] For every personal data field in your schema, answer: what feature uses this, and can we ship without it?
- [ ] If a field has no active use, delete it from the schema.
- [ ] Set data retention policies: automatically delete data after it is no longer needed for its purpose.
- [ ] Review signup and profile forms for fields that are collected "just in case" and remove them.
- [ ] Document your data collection in a data register with stated purpose — challenge any field without a clear purpose.

## Related
- `gdpr-by-design-not-retrofit.md`
- `dont-log-pii-in-production.md`
- `supplier-breach-affects-you.md`
