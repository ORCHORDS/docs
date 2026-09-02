# ISO/IEC 19790 Security Module Requirements Governance

## Purpose

Govern the application of ISO/IEC 19790 (security techniques — security requirements for cryptographic modules) so that cryptographic modules the studio deploys or procures meet defined requirements: the standard specifies the cryptographic module specification, ports and interfaces, roles and services, software/firmware security, operational environment, key management, self-tests, and mitigation of other attacks — and it is the technical basis under which FIPS 140-3 validation operates.

## Scope

Applies to cryptographic module selection, deployment, and validation tracking for studio systems. Covers module requirement areas, validation status management, and operational conformance. Does not cover algorithm selection (FIPS-approved algorithm standards govern that) or organizational key policy (SP 800-57 governs that).

## Workflow

1. Inventory cryptographic modules with their validation status: each module (library, HSM, appliance) recorded with certificate number, validation level, and version — unvalidated modules in FIPS-bound paths are findings.
2. Match requirement areas to deployment needs: physical security (levels 3-4), non-deterministic generation, self-tests, and operational environment constraints differ by validation level; the level required comes from data sensitivity and policy.
3. Track certificate scope precisely: validation covers a specific module version and security policy; upgrading the module library can silently invalidate the validation the deployment relies on.
4. Operate per the module's security policy: the certificate's security policy rules (approved modes, key input/output methods, role enforcement) are operational requirements, not documentation trivia.
5. Manage the module lifecycle: deprecating modules when validations retire (active security policy enforcement timelines) and scheduling replacements before retirement breaks compliance.
6. Verify vendor claims against the certificate listing: "FIPS validated" claims checked against the actual certificate entry — validated algorithms inside an unvalidated module do not make the module validated.
7. Layer with FIPS 140-3: ISO/IEC 19790 is the standard FIPS 140-3 adopts; track both the ISO text and the CMVP certificate status.

## Controls and evidence

- Cryptographic module inventory with certificate numbers, levels, and versions.
- Validation scope records matching deployed versions.
- Security policy operating records (modes, roles, key interfaces).
- Lifecycle retirement schedule with replacement plans.
- Vendor claim verification notes.

## Validation

- Sample five deployed modules and confirm each deployed version matches its certificate's scope.
- Confirm no FIPS-bound path depends on a module with retired validation.
- Confirm security policy operating requirements (e.g., approved mode enforcement) are configured and evidenced.

## Failure correction

- **Deployed version outside certificate scope** → roll back to the covered version or obtain updated validation evidence; the gap is a compliance break until closed.
- **Retired validation in production** → execute the replacement plan on an accelerated schedule and document interim risk acceptance.
- **Security policy rules unconfigured** → configure per the certificate policy and verify with the module's self-test/status indicators.

## Limitations

- Module validation covers the module, not the system using it; correct integration (key management hygiene, approved mode) remains the operator's obligation.
- Validation is point-in-time against the standard's requirements; new attack classes may postdate any certificate.
- Levels 3-4 physical security requirements constrain deployment form factors; not every environment can host every level.

## Scope note

This article is part of the security leaf. Cross-reference: `FIPS_140_3_CRYPTOGRAPHIC_MODULE_VALIDATION_GOVERNANCE.md`, `ISO_IEC_15408_COMMON_CRITERIA_EVALUATION_GOVERNANCE.md`, and `NIST_FIPS_203_ML_KEM_VERSION_GOVERNANCE.md` (reference leaf).

## Canonical sources

- ISO/IEC 19790:2025 — Security techniques — Security requirements for cryptographic modules: https://www.iso.org/obp/ui/#iso:std:iso-iec:19790:ed-3
- FIPS 140-3 — Security Requirements for Cryptographic Modules: https://csrc.nist.gov/pubs/fips/140-3/final
- NIST SP 800-140 — CMVPApproved security methods list series: https://csrc.nist.gov/pubs/sp/800/140/final
- NIST SP 800-57 Part 1 Rev 5 — Key Management Guidance: https://csrc.nist.gov/pubs/sp/800/57/part1/r5/final
- NIST CMVP — Cryptographic Module Validation Program: https://csrc.nist.gov/projects/cryptographic-module-validation-program
