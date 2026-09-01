# 3DS Cardholder Information Server Role

**Issue:** The Cardholder Information Server (CIS) is the merchant-side data store that participates in the 3-D Secure flow by holding cardholder account history, device-binding history, and prior authentication references that the Access Control Server (ACS) and Directory Server (DS) can query during a 3DS2 authentication. The CIS was added in 3DS2 to let issuers make risk decisions with more context than the 3DS request payload alone provides: the merchant's relationship with the cardholder, prior purchases, chargeback history, and the device fingerprint associated with the account. CIS integration is optional — many merchants skip it — but for high-traffic merchants with a returning customer base, a well-instrumented CIS shifts authentication toward the frictionless path and improves authorization rates.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Role in the 3DS2 flow

1. **AReq enrichment.** When the 3DS Server builds an authentication request on behalf of the merchant, it can query the CIS for additional cardholder data to include in the AReq payload. The CIS returns fields like prior authentication count, last authentication date, card creation date, purchase count last 24 hours, and cardholder account change history. The 3DS Server adds these to the AReq, which the Directory Server forwards to the issuer's ACS.
2. **Issuer request handling.** During authentication, the issuer's ACS may call the merchant's CIS to verify a fact the cardholder asserted during the challenge flow. For example, if the cardholder provides a one-time code and the issuer wants to verify that the same cardholder recently made a purchase, the ACS queries the CIS for a transaction history to validate the context.
3. **Recurring and MIT support.** For subsequent merchant-initiated transactions, the CIS stores the original 3DS authentication reference (the Authentication Reference, the 3DS Server Transaction ID, and the Data Exchange Reference). The merchant's 3DS Server uses the CIS to construct subsequent AReq messages that link to the original authentication. Without a CIS, recurring payments lose the reference and force a new authentication.

## Data the CIS exposes

1. **Cardholder account facts.** Account creation date, last account change date (address, email, phone), purchase count in trailing windows (24 hours, 6 months, 12 months), last successful transaction date, and the card's tenure with the merchant. These fields are mapped to specific 3DS2 AReq fields (3DS2 supports a rich set of cardholder account information fields).
2. **Authentication history.** A count of successful prior authentications, dates of those authentications, and the 3DS Server Transaction IDs from each. Issuers use this to evaluate low-risk exemption eligibility and to detect anomalous authentication patterns.
3. **Device and channel history.** If the merchant collects device fingerprints across sessions, the CIS holds the binding between account and device fingerprint. An AReq that submits a fingerprint consistent with prior sessions signals lower risk; a brand-new device fingerprint on a long-tenure account signals higher risk.

## Implementation paths

1. **Standalone CIS service.** Some 3DS Server providers (Adyen 3DS2, CardinalCommerce, Verifi) offer a managed CIS component that the merchant points at its data store. The merchant writes account-history records to the CIS as transactions occur, and the 3DS Server reads from it during AReq construction.
2. **Built into the 3DS Server.** Other 3DS Server implementations include CIS functionality implicitly: the 3DS Server maintains the account history internally, exposing query APIs to the merchant's checkout. The merchant integrates via the SDK without standing up a separate CIS.
3. **Merchant-owned CIS.** Some merchants build a CIS as a dedicated microservice that writes to a database of account facts and exposes query APIs. The build cost is meaningful — the merchant owns the schema, the freshness guarantees, the privacy controls — and the operational benefit is most visible at high transaction volumes with a returning customer base.

## Operational and privacy controls

1. **Data minimization.** The CIS stores facts that the issuer's ACS will use during authentication. Storing more than the 3DS2 specification requires does not help authentication and increases privacy exposure. Engineering should map every CIS field to a specific 3DS2 use case and remove anything that does not map.
2. **Retention limits.** The CIS is not an account-history archive. Retention should align with the issuer's authentication-reference validity window — typically 12 to 24 months for recurring series, longer for dispute support. A CIS that grows unbounded increases breach exposure and complicates privacy-rights compliance (GDPR right-to-erasure, CCPA data deletion).
3. **Authentication on CIS access.** Access to CIS data must be authenticated and authorized. The 3DS Server and any internal service querying the CIS must use mTLS or signed tokens. Direct database access is restricted to a small operations team with audit logging.

## Failure modes

1. **Stale data defeats the CIS purpose.** A CIS that updates asynchronously with the checkout flow (with seconds of lag) is treated by the 3DS Server as a low-confidence signal. The 3DS Server falls back to submitting a thin AReq to the issuer, which often routes to a challenge. Engineering must ensure CIS writes are synchronous with the authorization flow, or as close to synchronous as the architecture allows.
2. **CIS exposes PII in transit.** CIS queries that return cardholder name, email, phone, or address in the AReq payload must use TLS, and the receiving endpoint must enforce TLS. The merchant's CIS implementation is in PCI DSS scope because the AReq flows through it; PCI controls apply.
3. **Recurring reference drift.** A CIS that loses the link between a recurring series and the original 3DS Server Transaction ID forces the merchant's 3DS Server to authenticate each installment as a fresh transaction. The authentication cost multiplies, and many issuers decline the resulting MIT requests because the chain is broken.

## Canonical sources

1. EMVCo, EMV 3-D Secure Protocol and Core Functions Specification, with the dedicated Cardholder Information Server section. https://www.emvco.com/emv-technologies/3d-secure/
2. PCI Security Standards Council, Payment Card Industry Data Security Standard, Version 4.0, Requirement 3 and Requirement 4 on protected storage and transmission of cardholder data. https://www.pcisecuritystandards.org/document_library
