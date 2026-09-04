# Internet Exposure Is a Business Decision, Not a Default

**Issue:** A service remains publicly reachable because the original deployment exposed it, even though nobody can explain why direct internet access is still required.

**Date:** 2026-09-04
**Author:** ORCHORDS
**Status:** documented

## The lesson

CISA's Internet Exposure Reduction Guidance tells organizations to evaluate whether each internet-accessible asset actually needs public exposure and to remove or restrict access when it does not. Reachability should therefore be an explicit operational requirement, not an inherited infrastructure default.

## Engineering rule

- Require an owner and current business or operational reason for public reachability.
- Prefer private, restricted, proxied, VPN, gateway, or other controlled access when direct public access is unnecessary.
- Review dependencies before changing exposure so reduction work does not accidentally break required services.
- Revisit the exposure decision when the service, users, architecture, or business need changes.
- Treat "it has always been public" as missing evidence, not justification.

## Verification

- Select internet-facing services and ask the responsible owner to state the current need for direct public access.
- Remove or restrict a nonessential exposure and confirm required operations still work through the intended path.
- Verify retained exposures have an owner, justification, and reassessment date.

## Official source

- CISA, Internet Exposure Reduction Guidance, published June 4, 2025: https://www.cisa.gov/resources-tools/resources/exposure-reduction
