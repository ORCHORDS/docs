# PCI DSS Customized Approach Versus Compensating Controls

**Issue:** Treating the customized approach and compensating controls as interchangeable produces invalid control design and assessment evidence.

**Date:** 2026-08-17
**Author:** ORCHORDS
**Status:** documented

## Controls

- Use the defined approach by default and identify explicitly when a requirement is assessed through the customized approach.
- For a customized approach, document the requirement objective, control design, targeted risk analysis, testing method, and evidence showing the objective is met.
- Use a compensating control only when a legitimate technical or documented business constraint prevents meeting the requirement as stated.
- Document why each compensating control sufficiently addresses the original risk and exceeds normal expected controls.
- Engage the responsible assessor and compliance-program authority before relying on either path.

## Verification

- Trace each non-defined control to the exact requirement, rationale, objective, test procedure, result, owner, and approval.
- Challenge whether the claimed constraint is genuine and whether the control remains effective after system changes.
- Reassess annually and when threat, scope, design, or evidence changes.

## Gotchas

- Verify source maturity and product support before making a normative claim.
- Keep secrets, tokens, personal data, and restricted evidence out of examples and logs.
- Reassess after material changes to scope, dependencies, or enforcement.

## Sources

- https://blog.pcisecuritystandards.org/pci-ssc-publishes-new-guidance-on-compensating-controls-and-the-customized-approach
