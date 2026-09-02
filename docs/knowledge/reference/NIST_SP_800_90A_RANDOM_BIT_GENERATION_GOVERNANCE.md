# NIST SP 800-90A Random Bit Generation Governance

## Purpose

NIST SP 800-90A specifies deterministic random bit generator (DRBG) algorithms for cryptographic applications. Governance ensures that cryptographic applications use approved DRBG algorithms, that entropy sources meet the requirements, and that DRBG state is properly managed to ensure unpredictability.

## Current context and source status

NIST SP 800-90A was first published in 2012 with revision 1 published in 2015. SP 800-90A specifies three approved DRBG mechanisms (Hash_DRBG, HMAC_DRBG, CTR_DRBG). SP 800-90B addresses entropy sources. SP 800-90C forms the construction of the RBGs. Verify the current NIST publications before treating any specific DRBG mechanism as the only approved choice.

## Governance workflow and controls

### 1. Use approved DRBGs

For cryptographic applications requiring FIPS-validated modules, use a validated DRBG from SP 800-90A. Document the mechanism and the parameters.

### 2. Source entropy responsibly

Source entropy per SP 800-90B. Use approved entropy sources. Document the entropy source and the estimated entropy per sample.

### 3. Manage DRBG state

Manage DRBG state per SP 800-90A: instantiation, reseeding, output generation. Reseed at the required intervals. Document the management approach.

### 4. Apply prediction resistance

Apply prediction resistance where the threat model requires it. Implement reseed mechanisms that incorporate fresh entropy.

### 5. Address Dual_EC_DRBG

Do not use Dual_EC_DRBG. The algorithm was withdrawn and is not approved.

### 6. Apply per-application requirements

Apply application-specific requirements: key generation, nonces, salt, IV generation. Document the use of each DRBG output.

### 7. Verify in cryptographic modules

Verify the DRBG implementation within the cryptographic module is consistent with the validation certificate. Document the verification.

## Validation and evidence

- DRBG inventory.
- Entropy source documentation.
- Reseed schedule.
- Module validation certificate.

## Failure correction

Common defects include use of non-approved DRBGs, weak entropy sources, and missing reseed logic. Corrective actions include a DRBG compliance check, an entropy source audit, and a reseed verification test.

## Limitations

- SP 800-90A is specific to DRBG; entropy sources are addressed in SP 800-90B.
- DRBG security depends on entropy source quality.
- Reseed intervals are based on the algorithm and threat model.
- Some applications may require additional randomness beyond DRBG output.

## Canonical sources

- NIST SP 800-90A Rev. 1, Recommendation for Random Number Generation Using Deterministic Random Bit Generators, 2015.
- NIST SP 800-90B, Recommendation for the Entropy Sources Used for Random Bit Generation, current edition.
- NIST SP 800-90C, Recommendation for Random Bit Generator (RBG) Constructions, current edition.

## Scope note

This article belongs to the reference leaf and cross-references the security leaf for cryptographic controls, the engineering leaf for cryptographic implementation, and the standards leaf for cryptographic standards.
