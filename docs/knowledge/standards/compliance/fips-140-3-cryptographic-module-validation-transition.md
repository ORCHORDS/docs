# FIPS 140-3 cryptographic-module validation transition

**Category:** Compliance
**Author:** ORCHORDS
**Primary source:** [NIST Cryptographic Module Validation Program](https://csrc.nist.gov/projects/cryptographic-module-validation-program)

## Scope

This applies when a customer, contract, or regulatory obligation requires a validated cryptographic module. It is not a claim that ordinary use of an approved algorithm alone makes an application FIPS validated.

## Practice

- Inventory each cryptographic module in scope, its exact version and operating environment, validation certificate, validation status, and owning product.
- Confirm that the deployment uses the validated module and approved mode described by its security policy; library name similarity is not evidence.
- Plan the FIPS 140-2 to FIPS 140-3 transition for new systems. NIST states that FIPS 140-2 active modules move to the Historical List after 21 September 2026 for new-system use.
- Track vendor maintenance, module revocation, patches, and configuration changes that can invalidate the compliance claim.
- Keep procurement evidence, security policies, build provenance, runtime configuration, and test results together for audit.
- State any limitation precisely: module validation does not automatically validate the surrounding application or its protocol design.

## Verification

1. Match the deployed module version, operating environment, and approved mode against the CMVP record and security policy.
2. Test startup and cryptographic operations with the approved mode enforced.
3. Review new-system roadmaps for FIPS 140-3-capable replacements before the transition date.
4. Reassess the evidence after every module, image, OS, or configuration update.

## Failure modes

- Calling a product FIPS compliant because it uses a FIPS-approved algorithm.
- Replacing a library or changing its build flags without rechecking the validated module boundary.
- Leaving an expiring FIPS 140-2 dependency in a new deployment path without a transition plan.

## Related

- [NIST CMVP](https://csrc.nist.gov/projects/cryptographic-module-validation-program)
