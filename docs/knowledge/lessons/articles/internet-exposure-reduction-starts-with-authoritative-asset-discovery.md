# Internet-Exposure Reduction Starts With Authoritative Asset Discovery

**Issue:** An organization hardens the internet-facing systems it knows about but has no reliable method to find forgotten hosts, legacy interfaces, default credentials, or outdated services that are already exposed.

**Date:** 2026-09-04
**Author:** ORCHORDS
**Status:** documented

## The lesson

CISA's 2025 Internet Exposure Reduction Guidance highlights that organizations frequently leave misconfigured systems, default credentials, and outdated software reachable from the internet. Exposure reduction therefore starts with discovering the externally reachable attack surface and reconciling that view with intended inventory; hardening only the systems teams already remember cannot address unknown exposure.

## Engineering rule

- Maintain an authoritative inventory of systems and services that are intentionally internet reachable.
- Independently discover external exposure using appropriate DNS, cloud, gateway, network, certificate, and internet-search evidence rather than trusting inventory alone.
- Reconcile discovered assets against approved exposure and investigate every unknown or obsolete endpoint.
- Remove unnecessary internet reachability instead of compensating for it only with stronger passwords or monitoring.
- Prioritize default credentials, unsupported/outdated software, exposed administrative interfaces, and legacy remote-access services for immediate review.
- Repeat exposure discovery after infrastructure, networking, deployment, and ownership changes.

## Verification

- Compare the documented external-asset inventory with an independent discovery result and resolve every mismatch.
- Select representative exposed administrative and remote-access interfaces and confirm their internet reachability is intentional.
- Test whether decommissioned assets actually disappear from external discovery after removal.
- Track recurring unknown exposure back to the process that created it so the control improves beyond one-time cleanup.

## Official source

- CISA, Internet Exposure Reduction Guidance, June 4, 2025: https://www.cisa.gov/resources-tools/resources/exposure-reduction
