# NIST SP 800-63-3 Digital Identity Guidelines Governance

## Purpose

NIST SP 800-63-3 (June 2017, with subsequent revisions to the 63B and 63C supplements) provides technical guidance on digital identity, authentication, and lifecycle management. Governance ensures that ORCHORDS assigns Identity Assurance Levels (IAL), Authenticator Assurance Levels (AAL), and Federation Assurance Levels (FAL) based on risk, validates authenticator types against AAL requirements, and maintains the identity proofing and binding lifecycle.

## Current context and source status

SP 800-63-3 supersedes SP 800-63-2. The 2017 revision decoupled identity proofing from authentication and introduced the IAL, AAL, and FAL categorizations. SP 800-63A, 63B, and 63C are bound supplements. Verify current revision status before adopting a new revision.

## Governance workflow and controls

### 1. Assign assurance levels

- Assign IAL based on the consequences of identity proofing failure.
- Assign AAL based on the consequences of authentication failure.
- Assign FAL when the assertion is asserted to a relying party through a federation protocol.

### 2. Identity proofing (IAL)

- Apply identity proofing controls for the assigned IAL — IAL1 (no identity proofing required), IAL2 (remote or in-person), IAL3 (in-person with strong evidence).
- Validate identity evidence, capture biometric data where required, and bind the credential to the proven identity.

### 3. Authentication (AAL)

- Apply authenticator requirements for the assigned AAL — AAL1 (single-factor or multi-factor), AAL2 (multi-factor with phishing resistance where possible), AAL3 (hardware-based authenticator and verifier impersonation resistance).
- Restrict memorized secrets, validate authenticator strength, and require phishing-resistant options for higher AALs.

### 4. Federation (FAL)

- Apply FAL controls when assertions are issued to relying parties — FAL1 (signed assertion), FAL2 (encrypted assertion), FAL3 (additional replay protection).
- Validate relying party registration and trust chain.

### 5. Lifecycle

- Manage the binding lifecycle: issuance, renewal, recovery, revocation, and re-binding.
- Apply re-proofing on a documented cadence and on trigger events.
- Maintain evidence of identity proofing, authenticator assignment, and federation agreements.

## Validation and evidence

- Assurance level register with assigned IAL, AAL, and FAL.
- Identity proofing records aligned with IAL.
- Authenticator inventory aligned with AAL.
- Federation agreements and trust chain records.
- Lifecycle event log: issuance, renewal, revocation.

## Failure correction

Common defects include misassigned assurance levels, weak authenticators at high AAL, and missing lifecycle evidence. Corrective actions include assurance level review, authenticator strength audit, and lifecycle event log completeness check.

## Companion documents

- NIST_SP_800_53B_CONTROL_BASELINES_GOVERNANCE.md
- ../reference/NIST_SP_800_207_ZERO_TRUST_GOVERNANCE.md
- ISO_IEC_27001_2022_VERSION_TRANSITION_GOVERNANCE.md
