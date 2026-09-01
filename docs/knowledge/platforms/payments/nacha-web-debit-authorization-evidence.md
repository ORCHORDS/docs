# NACHA Web Debit Authorization Evidence

**Issue:** WEB debit entries, originated under the Nacha Operating Rules, allow a merchant to debit a consumer's account based on an authorization captured electronically — typically through a website form. The authorization must meet specific evidence requirements: it must be written and signed (or electronically equivalent), it must include the specific terms of the debit, and it must be retained by the originator for a defined period. The Nacha "Web Debit" rule revisions tightened the authorization evidence requirements in response to rising unauthorized debit volume. Engineering the evidence capture path means producing and retaining the signed authorization, the IP address and timestamp of capture, the consumer's affirmative consent, and the merchant's ability to produce the evidence on receipt of an unauthorized debit return (R10) or a written statement of unauthorized debit (WSUD).

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Authorization elements

1. **Express authorization language.** The consumer must affirmatively agree to the debit before the entry is originated. An unchecked checkbox, a pre-checked checkbox, or a "by submitting this form you agree" disclosure in a Terms of Service does not satisfy the WEB authorization rule. The authorization must be a discrete consent action.
2. **Authorization content.** The authorization must include: the consumer's name, the account to be debited (bank routing and account number or tokenized reference), the amount or range of amounts, the frequency (one-time or recurring), the date(s) of debit, the receiver (the merchant), and the consumer's signature or electronic equivalent.
3. **Disclosure content.** The authorization must include disclosures required by Nacha Rule and by Regulation E: the consumer's right to revoke, the consumer's right to receive a receipt, the merchant's contact information, and the date of the authorization.

## Evidence capture

1. **Immutable storage.** The signed authorization must be stored in a system that prevents modification after capture. An append-only log with cryptographic chaining (Merkle root per day, hash-linked entries) is the standard. The system must be able to produce the authorization and the metadata on demand.
2. **Metadata captured at sign time.** In addition to the signed content, the system must capture: the IP address, the user agent string, the timestamp (with timezone), and any session identifier that ties the consent to the broader checkout flow. This metadata supports evidence production for dispute resolution.
3. **Retention period.** Nacha requires retention of WEB debit authorizations for two years from the date of the last authorization-initiated transaction, with longer retention required for some recurring patterns. Engineering must enforce the retention period in the storage layer, not as an out-of-band process.

## Disputes and evidence production

1. **R10 unauthorized return.** When the RDFI returns a WEB debit as unauthorized (R10), the ODFI may request evidence from the originator. The originating merchant has a defined window (typically 10 banking days under Nacha rules, though specific schedules vary) to produce the signed authorization. Failure to produce shifts liability to the merchant.
2. **Written statement of unauthorized debit (WSUD).** A consumer dispute outside the ACH return window (typically after 60 days from settlement) is handled as a WSUD. The originator must produce the signed authorization and the supporting metadata. The arbitration process under Nacha may adjudicate if the consumer and originator disagree on the validity of the authorization.
3. **Tampered or missing authorization.** If the stored authorization cannot be produced, has been modified, or does not match the transaction, the originator loses the dispute. Engineering must treat the authorization as a regulated record with controls at the same level as financial transaction records.

## Engineering controls

1. **Capture-before-origination gate.** The origination system must verify that an authorization record exists for every WEB debit before submission. A WEB debit without a captured authorization is a compliance breach; the origination must be rejected at the gate.
2. **Re-collection flow on authorization failure.** When the consumer revokes authorization or the stored authorization is no longer valid, the system must surface a re-collection flow at the next interaction. Continuing to originate WEB debits on a revoked authorization triggers Reg E and Nacha Rule violations.
3. **Evidence production API.** The operations team must be able to produce the authorization and metadata on demand, typically within hours. Engineering should expose an evidence production API that returns the signed authorization PDF, the captured metadata JSON, and the cryptographic chain anchor.

## Failure modes

1. **Authorization captured but not stored.** A capture flow that writes the authorization to a transient store (cache, session database, ephemeral log) loses the authorization on system restart or scaling event. Engineering must persist to a durable, immutable store at capture time.
2. **Auth text differs from originated entry.** An authorization for $9.99/month cannot be used to originate a $19.99/month debit. If the terms in the signed authorization differ from the originated entry, the authorization is invalid for that entry. Engineering must surface the authorization terms to the origination system and reject mismatches.
3. **Expired authorization.** Nacha limits the validity of a WEB authorization for recurring debits to a defined period unless renewed. Engineering must track authorization expiration and refuse to originate WEB debits on expired authorizations, or surface a re-authorization prompt to the consumer.

## Canonical sources

1. Nacha (National Automated Clearing House Association), Nacha Operating Rules & Guidelines, including the WEB debit entry authorization provisions and the evidence retention requirements, current edition. https://www.nacha.org/rules
2. Consumer Financial Protection Bureau, Regulation E (12 CFR Part 1005), Subpart A and the official staff commentary on electronic fund transfer authorizations. https://www.consumerfinance.gov/rules-policy/final-rules/electronic-fund-transfers-regulation-e/
