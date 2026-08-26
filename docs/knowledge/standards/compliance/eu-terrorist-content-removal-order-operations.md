# EU terrorist-content removal-order operations

**Issue:** A hosting service provider offering services in the EU can receive a removal order under Regulation (EU) 2021/784 requiring removal or disabling access in all Member States as soon as possible and no later than one hour after receipt. Ad hoc moderation queues cannot reliably authenticate the order, preserve review rights, act globally, and retain evidence safely within that clock.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## Applicability and controls

- Determine whether the service stores and disseminates user-provided information to the public and offers services in the Union; document jurisdiction and any required legal representative.
- Maintain a continuously reachable designated contact point with trained backups and a tested one-hour escalation path.
- Authenticate the issuing competent authority, order integrity, receipt timestamp, content locator, scope, and required language without letting routine verification consume the deadline.
- Freeze the identified version, then remove or disable access across all Member States while preserving a scoped audit trail.
- Notify the content provider and support complaint or judicial-review rights where required, subject to lawful restrictions.
- Preserve removed content and related data for the six-month statutory period, and longer only upon a valid authority or court request, with strict purpose, access, encryption, and deletion controls.
- Keep voluntary-specific-measure governance separate from order execution and protect educational, journalistic, artistic, research, and awareness-raising context.
- Do not implement general monitoring as a shortcut.

## Implementation and tests

Route a signed synthetic order through receipt, verification, legal escalation, global disablement, authority response, user notice, preservation, review, restoration where ordered, and expiry deletion. Test a malformed or duplicate order, wrong authority, unavailable content, ambiguous locator, live stream, clock outage, multi-region cache, preservation extension, and successful challenge.

Use an append-only timeline with authority, receipt, verification, decisions, operator, affected object versions, regional propagation evidence, notices, preservation dates, and disposition.

## Gotchas and legal caveat

The one-hour clock is tied to receipt of the order, not completion of an internal ticket. Preservation is not permission to reuse the content. Over-removal can impair fundamental rights, while persistent or systematic non-compliance can trigger serious penalties.

Competent authorities, remedies, penalties, and procedures interact with national law. Obtain current legal advice; this is an operational control pattern, not a content classification rule.

## Official sources

- [EUR-Lex: Regulation (EU) 2021/784](https://eur-lex.europa.eu/eli/reg/2021/784/oj)
- [European Commission: Terrorist content online](https://home-affairs.ec.europa.eu/policies/internal-security/counter-terrorism-and-radicalisation/prevention-radicalisation/terrorist-content-online_en)
