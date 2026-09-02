# W3C Verifiable Credentials Data Model 2 Governance

## Purpose

W3C Verifiable Credentials Data Model 2 (VCDM 2) defines a model for expressing verifiable, tamper-evident credentials on the Web. Governance ensures that an organization issuing or verifying VCs uses the model correctly, that the underlying cryptography meets the required security level, and that revocation and status mechanisms are implemented.

## Current context and source status

W3C published the Verifiable Credentials Data Model 2.0 as a W3C Recommendation in 2024, replacing the 1.1 specification. VCDM 2 introduces a new data model with improved semantics, supports new credential formats, and provides better internationalization. Verify the current W3C Recommendation status and any companion specifications before treating any specific data model property as a current requirement.

## Governance workflow and controls

### 1. Apply VCDM 2 data model

Apply VCDM 2 data model for verifiable credentials. Use the defined credential structure with `@context`, `type`, `issuer`, `validFrom`, `validUntil`, `credentialSubject`, `proof`. Document the application.

### 2. Apply secure proof formats

Apply secure proof formats (W3C VC-JOSE-COSE, VC Data Integrity with Data Authentication Cryptography suites). Verify the chosen suite against the latest W3C guidance.

### 3. Manage issuer keys

Manage issuer keys securely. Use Hardware Security Modules (HSMs) for production issuers. Document key management.

### 4. Implement status and revocation

Implement credential status and revocation. Use StatusList 2021 or comparable. Update status records on revocation.

### 5. Apply schema definitions

Define credential schemas (JSON Schema or comparable). Document the schema. Apply schemas during verification.

### 6. Verify credentials

Verify credentials thoroughly:

- verify the proof suite;
- verify the issuer's key;
- verify the credential status;
- verify the credential schema;
- verify the credential's validity period.

Document the verification procedure.

### 7. Privacy considerations

Apply privacy considerations. Minimize disclosed data. Use selective disclosure (e.g., SD-JWT VC) where available. Document privacy choices.

### 8. Interoperability

Test interoperability across multiple issuers and verifiers. Use the W3C VC Test Suite or comparable.

## Validation and evidence

- Credential issuance configuration.
- Verification procedure documentation.
- Status/revocation management.
- Interoperability test results.

## Failure correction

Common defects include weak proof suites, missing status updates, and undisclosed credential schemas. Corrective actions include a proof suite upgrade, a status update procedure, and a schema documentation requirement.

## Limitations

- VCDM 2 is a data model, not a complete solution; multiple infrastructure choices remain.
- Some features (selective disclosure, key rotation) require additional specifications.
- Implementations vary; test for interoperability.
- Privacy depends on data minimization and selective disclosure choices.

## Canonical sources

- W3C, Verifiable Credentials Data Model 2.0, Recommendation, 2024.
- W3C, VC-JOSE-COSE, current edition.
- W3C, VC Data Integrity, current edition.

## Scope note

This article belongs to the reference leaf and cross-references the security leaf for cryptographic controls, the engineering leaf for credential implementation, and the standards leaf for identity standards.
