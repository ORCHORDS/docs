# gdpr-by-design-not-retrofit

**Issue:** Adding GDPR compliance to an existing system after launch requires re-architecting data flows, storage, and deletion — at enormous cost
**Date:** 2026-08-11
**Status:** documented

## What happened
A US startup expanded to Europe and discovered that their data model had no concept of data residency, no deletion workflow (right to erasure), and no consent records. Personal data was scattered across seven tables, four microservices, and two external analytics platforms. Retrofitting took an eight-engineer sprint lasting three months, cost $400k, and blocked the EU launch by a quarter.

## The lesson
Privacy by design means building data protection in from the beginning, not bolting it on later. Before writing the first line of code for any feature that touches personal data, define: what data is collected, why, how long it is retained, and how it can be deleted. Design the schema and services around these constraints.

## Why it matters
Retrofitting GDPR compliance into an existing system requires finding every place personal data lives — which is much harder than designing it not to spread. The cost grows with system complexity and time.

## How to apply
- [ ] Before building any feature that collects personal data, answer: what, why, how long, and how deleted.
- [ ] Design a single "user data deletion" flow that cascades across all services from the start.
- [ ] Store consent records (what was agreed to, when, version of privacy policy) with the user record.
- [ ] Use a data catalog to track where each personal data field is stored and why.
- [ ] Review new features against GDPR principles (minimization, purpose limitation) in technical design review.

## Related
- `data-minimization-reduces-breach-impact.md`
- `user-consent-flows-need-ux-review.md`
- `supplier-breach-affects-you.md`
