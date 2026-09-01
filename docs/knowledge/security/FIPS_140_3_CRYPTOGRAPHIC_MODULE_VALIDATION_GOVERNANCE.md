# FIPS 140-3 Cryptographic Module Validation Governance

## Purpose

FIPS 140-3, *Security Requirements for Cryptographic Modules*, is the United States National Institute of Standards and Technology (NIST) Federal Information Processing Standard that defines the security requirements for cryptographic modules used by federal agencies and many regulated industries. It supersedes FIPS 140-2 and aligns with ISO/IEC 19790:2012, the corresponding international standard. The Cryptographic Module Validation Program (CMVP) jointly operated by NIST and the Canadian Centre for Cyber Security (CCCS) validates modules against FIPS 140-3 and publishes the results.

This article describes a governance pattern for operating, procuring, and validating FIPS 140-3 cryptographic modules. It does not assert compliance with any specific U.S. federal requirement or with the CMVP's validation decisions, and it does not replace the standard or the CMVP validation lists.

## Scope

FIPS 140-3 applies to the *module* — the set of hardware, software, and firmware that implements cryptographic functions and that is clearly bounded by the module's defined cryptographic boundary. It does not apply to the larger system that uses the module, but the security of that system depends on whether the module is integrated correctly.

A FIPS 140-3 program should document:

- which systems rely on FIPS-validated cryptography and which do not;
- which modules are validated and at which security level (1 through 4);
- the boundary between the validated module and the surrounding system; and
- the relationship between FIPS 140-3 and adjacent standards (FIPS 197 for AES, FIPS 186-5 for digital signatures, NIST SP 800-90A/B/C for randomness, NIST SP 800-131A for algorithm transitions).

## Workflow

A reusable FIPS 140-3 program runs as a cycle.

1. **Identify cryptographic use.** Inventory every cryptographic operation that protects regulated or sensitive data, including confidentiality, integrity, authentication, and non-repudiation. Distinguish operations provided by FIPS-validated modules from operations provided by software-only libraries.
2. **Select an appropriate module.** Match the security level (1 through 4) to the threat model and the operating environment. Document the module's certificate number, vendor, version, and operational status.
3. **Integrate correctly.** Ensure the cryptographic module is invoked in its validated configuration. Misconfiguration (operating outside the module's validated mode, using non-approved algorithms, or using non-approved key sizes) voids the validation for that use.
4. **Operate the validated configuration.** Apply operator guidance from the module's Security Policy. Use only approved algorithms and key sizes. Manage keys according to the relevant key-management standard.
5. **Monitor for change.** Track module vendor advisories, algorithm deprecation notices (notably those from NIST SP 800-131A), and revalidation status.
6. **Plan transition.** When a module is retired or a transition is announced, schedule a migration before the deadline and verify that downstream systems are not affected by the change.
7. **Document evidence.** Retain validation certificates, the module Security Policy, integration records, and any exceptions with owners and expiry.

## Controls and evidence

FIPS 140-3 organizes requirements into eleven sections. A program should map its controls to each section that applies to the module in use.

| Section | Topic | Typical evidence |
|---|---|---|
| 1 | General | Module name, version, validation certificate |
| 2 | Cryptographic module specification | Approved algorithms, security policy, validated configuration |
| 3 | Cryptographic module interfaces | Logical interfaces, data paths, ports, trust paths |
| 4 | Roles, services, and authentication | Operator and crypto-officer roles, authentication mechanisms |
| 5 | Software/firmware security | Integrity verification mechanism, load tests |
| 6 | Operational environment | OS version, hardening settings, EAL assurance if applicable |
| 7 | Physical security | Tamper evidence, response, zeroization |
| 8 | Non-invasive security | Side-channel mitigation if applicable |
| 9 | Sensitive security parameters management | Generation, entry/output, storage, zeroization |
| 10 | Self-tests | Pre-operational, conditional, critical-function, error state |
| 11 | Life-cycle assurance | Configuration management, delivery, operation, end-of-life |

For each module in use, retain at minimum: the validation certificate number and the certificate's issued date; the Security Policy document; the operational configuration in use; the integration evidence showing the module is invoked correctly; the most recent self-test results; and the algorithm inventory showing only approved algorithms.

## Validation

Validation confirms that the deployed configuration matches the validated configuration and that approved algorithms are the only ones in use. Useful activities include:

- comparing the deployed module's version and configuration with the certificate and Security Policy;
- running module self-tests on a defined schedule and after power-cycle events;
- inspecting traffic or storage to confirm only approved algorithms are active;
- reviewing module logs for self-test failures and operator actions;
- reviewing the surrounding system for correct key-management practice; and
- confirming that the integration does not bypass the module's logical or physical boundary.

Validation must distinguish between validated and not-validated configurations. A module that has been reconfigured outside its Security Policy is no longer operating in a validated mode for that use, even if the underlying certificate is still active.

## Failure correction

When a FIPS 140-3 control fails, follow a documented path.

1. Confirm the failure with reproducible evidence.
2. Identify the section and requirement that was violated and the operational impact.
3. Apply the corrective change through the change management process.
4. Verify with new evidence (such as a fresh self-test or scanner output).
5. Report material failures to the appropriate authority where required by policy or contract.

Common failure modes include:

- assuming that the presence of a FIPS-validated library guarantees correct integration;
- using a module outside its validated configuration (for example in a different operating environment than the certificate specifies);
- continuing to use deprecated algorithms (such as single-DES, SHA-1 in certain modes, or RSA signatures below the published minimum modulus) past the published transition deadlines;
- storing keys in software outside the module's protection; and
- failing to track certificates that have been placed on the CMVP historical list after a transition deadline.

## Limitations

FIPS 140-3 specifies module security, not system security. A validated module integrated into an unvalidated or improperly designed system cannot protect data beyond the module's boundary. Programs should pair FIPS 140-3 controls with system-level controls drawn from NIST SP 800-53, ISO/IEC 27001, or equivalent frameworks.

Validation timelines through the CMVP have been historically long, and certificates can lag behind the published state of the art. Organizations should not wait for a certificate to begin using a module whose underlying algorithm is NIST-approved and whose vendor has committed to validation.

## Canonical sources

- FIPS 140-3 — *Security Requirements for Cryptographic Modules*, final: https://csrc.nist.gov/pubs/fips/140-3/final
- NIST Cryptographic Module Validation Program (CMVP) — official module validation lists and program documentation: https://csrc.nist.gov/projects/cryptographic-module-validation-program
- ISO/IEC 19790:2012 — *Information technology — Security techniques — Security requirements for cryptographic modules* (international counterpart aligned with FIPS 140-3): https://www.iso.org/standard/52906.html

## Scope note

This article summarizes reusable governance practices derived from FIPS 140-3 and the CMVP. It is not a substitute for the standard or for the CMVP's published validation lists, does not assert conformity with any U.S. federal cryptographic requirement, and does not constitute legal or compliance advice for any specific procurement or operation.
