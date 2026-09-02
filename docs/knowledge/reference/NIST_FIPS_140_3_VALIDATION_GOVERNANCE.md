# NIST FIPS 140-3 Cryptographic Module Validation Governance

## Purpose

FIPS 140-3 is the U.S. federal standard for cryptographic modules. The Cryptographic Module Validation Program (CMVP) validates modules against FIPS 140-3 requirements. Governance ensures that cryptographic modules in use are validated to the appropriate level, that the validation is current, and that the operational environment matches the validated configuration.

## Current context and source status

FIPS 140-3 was approved in 2019 and became effective in its current form on April 1, 2021. The standard supersedes FIPS 140-2. The CMVP validates modules to FIPS 140-3; FIPS 140-2 validations are no longer issued but existing validations remain effective until their sunset dates. Verify the current FIPS 140-3 implementation guidance and module-specific transitions before treating any specific validation requirement as a current requirement.

## Governance workflow and controls

### 1. Determine applicable use

Determine whether the use case requires FIPS validation. U.S. federal agencies and contractors must use validated modules for the protection of sensitive information. Other organizations may voluntarily adopt FIPS-validated modules as a security baseline.

### 2. Select the security level

Select the appropriate FIPS 140-3 security level (1 to 4) based on the threat environment and the data sensitivity. Higher levels require more tamper resistance and stronger role authentication.

### 3. Verify module validation

Verify the module's validation status. The CMVP maintains a list of validated modules with their validation certificates, module names, and vendor information. Check the certificate is active.

### 4. Verify operational environment

Verify the module is used in the operational environment specified in the validation. Changes to the environment (operating system, hardware platform, firmware) may invalidate the validation.

### 5. Manage vendor transitions

Manage vendor transitions when validated modules are deprecated or when new modules become available. Update systems before the validation expires.

### 6. Document module use

Maintain a register of cryptographic modules in use, including:

- module name and version;
- vendor;
- validation certificate number;
- security level;
- operational environment;
- application or workload;
- owner.

### 7. Address non-validated algorithms

Address any non-validated algorithms used (for example, for legacy interoperation). Apply risk acceptance with documented rationale and expiry.

## Validation and evidence

- Cryptographic module register.
- Validation certificate copies.
- Operational environment configuration records.
- Vendor transition plan.
- Non-validated algorithm risk acceptance.

## Failure correction

Common defects include use of non-validated modules, modules used outside their validated environment, and expired validations. Corrective actions include a module inventory audit, an environment-configuration review, and a validation expiry calendar.

## Limitations

- FIPS 140-3 is a U.S. standard; other jurisdictions have analogous programs (e.g., CAVP, Common Criteria).
- Validation does not guarantee module security in all operational contexts.
- Module transitions take time; plan ahead.
- Some modules are validated at higher levels for stricter requirements.

## Canonical sources

- NIST FIPS 140-3, Security Requirements for Cryptographic Modules, 2019.
- NIST CMVP, current implementation guidance and module list.
- NIST SP 800-140x series, current editions.

## Scope note

This article belongs to the reference leaf and cross-references the security leaf for cryptographic controls, the platforms leaf for cloud HSMs, and the standards leaf for cryptographic standards.
