# Internet Exposure Reconciliation

## Trigger
Run on a regular cadence, after material network/cloud/DNS changes, after acquisitions or migrations, and whenever an unexpected public service is discovered.

## Inputs
- Documented internet-facing asset/service inventory.
- DNS, gateway, load-balancer, cloud, and deployment inventories available to the organization.
- Independent external discovery or vulnerability-scanning results.
- Asset/service ownership information.

## Procedure
1. Capture the current documented list of assets and services expected to be reachable from the public internet.
2. Perform or obtain an independent outside-in assessment of internet reachability.
3. Reconcile each externally discovered asset/service against the documented inventory.
4. Assign an owner to every unmatched result and determine whether the exposure is expected, stale, accidental, or unknown.
5. For expected exposures, confirm the listed service/protocol and ownership information are current.
6. For unexpected or unnecessary exposures, initiate removal or restriction through the normal change process.
7. Recheck externally after remediation rather than relying only on an internal configuration change.
8. Record recurring discovery blind spots and add authoritative data sources or checks to the next assessment.

## Escalation
Escalate unknown, unowned, sensitive, administrative, or unsupported public exposures that cannot be quickly explained or reduced.

## Evidence
- Expected exposure inventory snapshot.
- External discovery result.
- Reconciliation table and dispositions.
- Ownership assignments.
- Remediation/restriction evidence.
- External retest result.

## Completion criteria
Every externally discovered exposure is documented, owned, intentionally reachable, and either retained with justification or verified as removed/restricted.

## Source basis
- CISA, Internet Exposure Reduction Guidance, published June 4, 2025: https://www.cisa.gov/resources-tools/resources/exposure-reduction
