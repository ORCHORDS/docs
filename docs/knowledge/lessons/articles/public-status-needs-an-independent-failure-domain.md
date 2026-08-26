# Public Status Needs an Independent Failure Domain

**Issue:** When the status page shares DNS, identity, CDN, deployment, or control-plane dependencies with the product, the incident can make both the service and its explanation unreachable.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** draft

## Controls

- Host public incident communication outside the primary application failure domain.
- Use separate credentials, DNS paths, publishing roles, and emergency access procedures.
- Prepare minimal templates and a manual publishing route for control-plane outages.
- Test status publication while primary infrastructure and corporate identity are unavailable.

## Verification

- Run a game day that disables application DNS, SSO, and deployment control plane.
- Verify authorized responders can publish from a clean device and alternate network.
- Confirm customers can resolve and load status information from affected regions.

## Gotchas

- Embedding the status widget into the failed application does not provide independence.
- The external status provider can also fail; retain a second communication route.

## Official sources

- https://sre.google/sre-book/managing-incidents/
