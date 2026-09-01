# Network Tokenization Lifecycle Governance

**Issue:** Card network tokenization replaces the Primary Account Number (PAN) at the merchant or acquirer with a scheme-issued Token PAN (TPAN) bound to a Token Requestor ID and a specific device or merchant context. The token carries the same routing behavior as the underlying PAN but limits the blast radius of a breach: a stolen token cannot be used at a different merchant, in a different channel, or on a different device without re-binding. Engineering the lifecycle means managing token issuance, binding to a specific context (device fingerprint, merchant category, channel), storage and refresh, fallback to PAN when a token is unsupported, and token de-provisioning on card-replacement or account-closure events. Each lifecycle stage has distinct failure modes and distinct compliance implications under PCI DSS because the tokenization boundary changes the cardholder data environment.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Issuance and provisioning

1. **Token Requestor identification.** A merchant integrates with a Token Service Provider (TSP) — Visa Token Service, Mastercard MDES, Amex Token Service, Discover DPAS — and receives a Token Requestor ID after the scheme's due-diligence review. The TRID is the binding between the merchant context and every token the TSP issues on the merchant's behalf; it is also the identifier that the network uses to enforce token usage constraints.
2. **Card-on-file enrollment.** When the cardholder saves a card with the merchant, the merchant (or the TSP via an API call) requests a tokenization for that PAN. The TSP performs issuer verification — typically a one-time authentication — and returns a Token PAN, an Expiry Date, and a Cryptogram Key for cryptogram generation where applicable. The merchant stores the TPAN, never the PAN, after the enrollment is complete.
3. **Device binding.** Wallets (Apple Pay, Google Pay, Samsung Pay) provision tokens through the OEM's TSP integration, with the Secure Element or device attestation providing the device binding. Card-on-file tokens for e-commerce typically do not have a device binding; instead they are merchant-bound. The lifecycle is different: card-on-file tokens refresh on card-replacement events, wallet tokens refresh on device-loss events.

## Storage and usage

1. **Token PAN as cardholder data equivalent for scope.** PCI DSS v4 treats token PANs as sensitive authentication data equivalents only if they can be reversed to the PAN through collusion or compromise. The merchant's CDE scope depends on whether the TPAN is stored, the cryptogram keys are stored, and the BIN-to-PAN mapping is accessible. A TSP-stored TPAN that is referenced by token reference ID puts the merchant outside the CDE for the underlying PAN, but inside the CDE for the token and the metadata.
2. **Cryptogram generation per transaction.** For tokens that support network cryptograms (most wallet-issued tokens, certain card-on-file integrations), each transaction must generate a single-use cryptogram using the TRID-bound key. Replay protection is enforced by the network: a cryptogram cannot be reused beyond a narrow window. Merchants that cache cryptograms or retry with a stored cryptogram create network-level declines.
3. **Fallback to PAN.** Not every merchant or acquirer in the transaction chain supports tokens. Where the merchant submits a TPAN and the acquirer or downstream gateway does not support it, the transaction fails. Engineering must implement a fallback path — either detokenize via the TSP at submission time (introducing latency and operational risk) or maintain a parallel PAN storage in a tokenization-vault architecture that satisfies PCI DSS scope reduction.

## Lifecycle events

1. **Card-replacement notification.** When the issuer replaces the card, the network notifies the TSP, which invalidates the existing TPAN and issues a new one bound to the same TRID. The merchant's account-updater service (or a TSP-led push) propagates the new TPAN. Engineering must ensure the account-on-file records are updated within the network's notification SLA, typically 24-72 hours for Visa and Mastercard.
2. **Account closure.** Cardholder-initiated or issuer-initiated closure triggers a Token Status Change notification. The merchant must mark the card-on-file record as invalid and surface a re-collection flow at next checkout. Continuing to attempt authorization on a closed-account token yields network-level declines but also a chargeback risk for any pre-authorized recurring transaction.
3. **Device loss.** Wallet tokens bound to a specific device must be unprovisioned when the device is reported lost. The OEM's TSP integration handles this; the merchant's role is to drop the local token reference and re-enroll on the next legitimate device binding. Card-on-file tokens are not affected by device loss.

## Operational controls

1. **Token vault segregation.** The token vault — the system that maps internal account ID to TPAN, expiry, and metadata — must be logically segregated from the rest of the application. Access to the vault should be brokered, audited, and rate-limited. The vault is the new CDE perimeter in a tokenization architecture.
2. **Cryptogram key rotation.** TSPs rotate cryptogram keys on a defined schedule (often 30 days for EMVCo-compliant key derivation). The merchant must request new keys before each transaction or pre-fetch a small key cache. Stale-key transactions decline at the network layer.
3. **Token-to-PAN traceability for dispute resolution.** When a chargeback references a transaction, the merchant must produce the underlying transaction evidence. A tokenized transaction produces evidence keyed on TPAN; if the dispute process requires PAN evidence, the merchant must use the TSP's detokenization API under a controlled audit trail.

## Failure modes

1. **PAN stored alongside TPAN.** A common architectural mistake is to store the original PAN in a back-office system "for fallback" while processing with the TPAN in the front. PCI DSS scope then expands to every system that touches the PAN. Tokenization discipline is binary: either the PAN is segregated to a vault with no application access, or the merchant has not actually reduced scope.
2. **Cryptogram replay on retry.** A network timeout or acquirer retry that resubmits a stored cryptogram is rejected by the network, and the rejection may be flagged as suspicious. Implement retry with fresh cryptogram generation per attempt, not with cached values.
3. **Token Status Change ignored.** Account-updater events that are queued but not processed cause authorization failures on otherwise-valid cards. Engineering must monitor the queue depth and the time-since-last-update metric, with alerting when the TSP stops sending updates for an extended period.

## Canonical sources

1. EMVCo, EMV Payment Tokenization Specification — Technical Framework, latest published version. https://www.emvco.com/emv-technologies/payment-tokenization/
2. PCI Security Standards Council, Payment Card Industry Data Security Standard, Version 4.0. https://www.pcisecuritystandards.org/document_library
