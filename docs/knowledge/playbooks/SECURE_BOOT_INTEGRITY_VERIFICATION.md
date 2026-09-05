---
title: "Secure Boot Integrity Verification"
owner: "Endpoint Security"
status: "approved"
classification: "public"
last-reviewed: "2026-09-05"
review-cycle: "180 days"
next-review: "2027-03-04"
trigger: "New firmware or bootloader release, supply-chain advisory affecting platform root-of-trust, or scheduled six-monthly attestation."
scope: "All corporate and production-tenant laptops, workstations, and edge appliances enrolled in fleet management; production server platforms with measured boot or TPM attestation."
inputs:
  - "Endpoint inventory with platform, firmware version, and enrollment state"
  - "Current Secure Boot DB and DBX (forbidden signatures) from vendor"
  - "Fleet management attestation reports"
  - "Recent advisories affecting UEFI, TPM, or firmware"
plan:
  - "Step 1: Confirm enrollment coverage — every in-scope device has a fleet attestation record."
  - "Step 2: Compare observed firmware and bootloader versions against the approved baseline."
  - "Step 3: Compare observed Secure Boot state — enabled, disabled, or unknown — against the platform policy."
  - "Step 4: Cross-check Secure Boot DB against the vendor revocation list to ensure no forbidden signer is present."
  - "Step 5: Validate TPM PCR measurements against expected platform measurements for in-scope servers with measured boot."
  - "Step 6: Investigate any device where the attestation state is unknown or non-compliant; isolate if needed."
  - "Step 7: Apply approved firmware and bootloader updates in line with change control."
  - "Step 8: Re-attest; document residual risk for any device remaining out of compliance."
evidence:
  - "Attestation report per device class with timestamps"
  - "Baseline and observed firmware matrix"
  - "DB and DBX cross-check output"
  - "TPM measurement log for measured-boot servers"
  - "Residual risk register entries with compensating controls and expiry"
escalation:
  - "Any device with unknown attestation state and out-of-date firmware — escalate to Endpoint Security."
  - "Any platform advisory with active exploitation — escalate to Security on-call and apply emergency update procedure."
completion:
  - "100 percent of in-scope devices have a current attestation record."
  - "All non-compliant devices remediated or risk-accepted with expiry."
exceptions:
  - "Legacy devices with documented business need and compensating controls."
related:
  - "PATCH_MANAGEMENT_EFFECTIVENESS_REVIEW.md"
  - "ASSET_INVENTORY_REVIEW.md"
  - "VENDOR_REMOTE_ACCESS_REVIEW.md"
