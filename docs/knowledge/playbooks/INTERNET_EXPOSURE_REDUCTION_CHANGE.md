# Internet Exposure Reduction Change

## Trigger
Run when an internet-accessible asset or service no longer requires direct public exposure or can be moved behind a more restricted access path.

## Inputs
- Exposure inventory and current business/operational justification.
- Service/dependency map or equivalent dependency evidence.
- Proposed target access path and controls.
- Change, rollback, and validation plan.

## Procedure
1. Confirm the exposure is not required for the current business or operational use case, or identify the restricted replacement access path.
2. Identify upstream/downstream dependencies, external consumers, automation, monitoring, certificates, DNS, firewall rules, and other components that may depend on the existing exposure.
3. Define the target state: remove the service from public reachability or restrict it through the approved gateway, VPN, proxy, policy-enforcement point, allowlist, or other architecture.
4. Define rollback criteria that restore service without silently restoring unnecessary long-term exposure.
5. Execute the change through the normal change-control path.
6. Test required business functionality through the target access path.
7. Verify from an external vantage point that the old public exposure is no longer reachable or is restricted as intended.
8. Update the exposure inventory, owner record, diagrams, and monitoring scope.
9. Observe the service through an appropriate validation window and close only after dependencies remain healthy.

## Escalation
Escalate when removal causes unknown critical dependencies, the service cannot be safely restricted, or rollback would reintroduce an exposure with unresolved high risk.

## Evidence
- Necessity/decision record.
- Dependency review.
- Approved change and rollback plan.
- Functional test result.
- External reachability retest.
- Updated inventory/documentation.

## Completion criteria
Required operations continue through the intended access path and independent external verification confirms unnecessary public reachability has been removed or restricted.

## Source basis
- CISA, Internet Exposure Reduction Guidance, published June 4, 2025: https://www.cisa.gov/resources-tools/resources/exposure-reduction
