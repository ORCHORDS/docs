# NIST SP 800-193 Platform Firmware Resiliency Governance

## Purpose

Govern the application of NIST SP 800-193 (Platform Firmware Resiliency Guidelines) so that platform firmware — the code that boots before the operating system — is protected, detected when corrupted, and recovered automatically, making firmware-level compromise survivable rather than catastrophic.

## Scope

Applies to every server, appliance, and endpoint platform the studio procures or operates where firmware resiliency matters. Covers the protect/detect/recover model for firmware, secure boot chains, and firmware update integrity. Does not cover operating system hardening or application-level supply chain security.

## Workflow

1. Require platform firmware resiliency capabilities in procurement: devices handling production workloads must support the SP 800-193 protect/detect/recover mechanisms, and the requirement appears in procurement specifications.
2. Map each platform's boot chain against the guideline's protection mechanism: immutable or verifiable boot code at each link, with each stage verifying the next before execution.
3. Enable detection: firmware integrity measurement and reporting that surfaces corruption events to platform management and the studio's monitoring.
4. Enable recovery: automatic restoration of corrupted firmware from a trusted, immutable recovery copy where the platform supports it; document platforms where recovery is manual and the compensating procedure.
5. Manage firmware update integrity: updates are cryptographically verified by the platform before application; unsigned update paths are prohibited in production.
6. Record each platform's firmware resiliency posture in the platform register: protection mechanism, detection integration, recovery method, and last verified date.
7. Exercise recovery deliberately on a sample of platforms each year: verify the recovery path works before it is needed in an incident.

## Controls and evidence

- Procurement requirement text and vendor capability confirmations per platform class.
- Platform register entries: boot chain protection, detection integration, recovery method, last verified date.
- Firmware update verification configuration and update logs.
- Annual recovery exercise records with outcomes.

## Validation

- Sample platform register entries and confirm detection events flow to monitoring in a test.
- Confirm firmware update application rejects an unsigned or corrupted update in a test scenario.
- Confirm the most recent recovery exercise for a sampled platform succeeded or produced a remediation plan.

## Failure correction

- **Firmware corruption detected without recovery** → invoke the documented manual recovery procedure, then remediate the platform's recovery gap or replace the platform.
- **Unsigned update path discovered** → disable the path, audit firmware versions for tampering, and close the procurement gap.
- **Recovery exercise failed** → treat as a platform-level finding; escalate to procurement and platform owners with a deadline.

## Limitations

- SP 800-193 targets x86 server and client platforms primarily; other architectures implement resiliency differently.
- Detection depends on platform management integration; unmonitored platforms have detection without visibility.
- Recovery from firmware-level compromise assumes the recovery copy itself is protected; verify that assumption per platform.

## Scope note

This article is part of the platforms leaf. Cross-reference: `NIST_SP_800_204_CLOUD_NATIVE_SECURITY.md`, `FIPS_140_3_CRYPTOGRAPHIC_MODULE_VALIDATION_GOVERNANCE.md` (security leaf), and `ETSI_MEC_MULTI_ACCESS_EDGE_COMPUTING_GOVERNANCE.md`.

## Canonical sources

- NIST SP 800-193 — Platform Firmware Resiliency Guidelines: https://csrc.nist.gov/pubs/sp/800/193/final
- NIST SP 800-147B — BIOS Protection Guidelines: https://csrc.nist.gov/pubs/sp/800/147b/final
- Trusted Computing Group — TPM 2.0 Library Specification: https://trustedcomputinggroup.org/resource/tpm-library-specification/
- Unified Extensible Firmware Interface (UEFI) Forum — Secure Boot: https://uefi.org/specifications
- NIST SP 800-147 — BIOS Protection Guidelines (original): https://csrc.nist.gov/publications/detail/sp/800-147/final
