# W3C Verifiable Credentials 2.0 Template Governance

## Purpose

W3C Verifiable Credentials 2.0 (VC 2.0) defines a data model and representations for cryptographically verifiable claims about subjects (people, organizations, things). VC 2.0 updates the prior VC 1.x with a new data model, multiple representations (JSON, JSON-LD, CBOR/VC-JOSE-CBOR), and the integration with the W3C VC-JOSE-CBOR secured format. VC 2.0 enables interoperability across issuers, holders, and verifiers, and is used in digital wallets, decentralized identifiers, and trust frameworks. This article governs the application of VC 2.0 as a template for issuing, holding, and verifying verifiable credentials.

## Scope

The specification applies to any organization that issues, holds, or verifies verifiable credentials. Within this knowledge base, the article covers the VC 2.0 data model (Credential, Subject, Issuer, Claim, Proof, Status), the representations (JSON, JSON-LD, CBOR), the verification process, and the documentation of the credential schema. It does not cover decentralized identifiers (DIDs); readers should consult the W3C DID specification for that.

## Workflow

1. Identify the claims to be expressed as verifiable credentials. Each claim should have a defined subject, issuer, schema, and proof mechanism.
2. Define or reuse a credential schema. VC 2.0 supports JSON Schema for the credential's data structure; reuse existing schemas where they fit.
3. Implement the issuer:
   - Receive the claims from the source.
   - Build the credential conforming to the VC 2.0 data model.
   - Apply a proof (a cryptographic signature over the credential) using the issuer's signing key. VC 2.0 supports multiple proof suites (Data Integrity with EdDSA, ECDSA, BBS; JWT-based proofs; SD-JWT).
   - Optionally, register a status mechanism for revocation or suspension (StatusList2021, Bitstring Status List).
4. Implement the holder: receive, store, and present credentials. The holder may also derive presentations with selective disclosure.
5. Implement the verifier:
   - Receive the verifiable presentation.
   - Validate the credential's proof using the issuer's verification method.
   - Validate the credential's status.
   - Validate the credential's schema and any required claims.
   - Check the trust framework: is the issuer trusted for this type of claim in this context?
6. Document the credential schemas, the issuer's verification methods, the trust framework, and the verification process.

## Controls and evidence

VC controls include the credential schemas, the issuer's key management, the status list, the verification logs, and the trust framework documentation. Each credential issuance should be auditable: which issuer signed it, when, with what key, under what schema. The verification process should be recordable so disputes can be investigated.

## Validation

Validation should confirm the credentials conform to the schema, the proofs verify, the status checks return current results, the trust framework is applied, and the presentations disclose only the claims the holder intends. Sample-based testing across credential types and issuers confirms the implementation.

## Failure correction

Common failure modes: schemas are not reused across issuers (corrective: define a small set of canonical schemas and require conformance); revocation is not implemented (corrective: implement a status mechanism and validate status at verification); the issuer's key management is weak (corrective: use HSMs or equivalent for signing keys and rotate per policy); trust framework is implicit and not documented (corrective: document the trust framework including which issuers are trusted for which claims).

## Limitations

VC 2.0 is a data model and representations; it does not certify any deployment or any specific credential. The standard does not address legal recognition of credentials; that is governed by jurisdiction-specific law (eIDAS in the EU, state digital ID frameworks, etc.). VC 2.0 does not guarantee the issuer is trusted; the verifier must evaluate the trust framework separately.

## Scope note

This article summarizes project-neutral use of W3C Verifiable Credentials 2.0 as a template. It does not assert any specific issuer's conformance or claim any certification outcome.

## Canonical sources

- W3C Verifiable Credentials 2.0 — Data Model: https://www.w3.org/TR/vc-data-model-2.0/
- W3C Verifiable Credentials 2.0 — Securing Verifiable Credentials using Data Integrity: https://www.w3.org/TR/vc-data-integrity/
- W3C Bitstring Status List: https://www.w3.org/TR/vc-bitstring-status-list/