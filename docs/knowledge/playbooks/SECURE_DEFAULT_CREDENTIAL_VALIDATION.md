# Secure-Default Credential Validation

## Trigger
Run before releasing a new product or appliance, after installation/reset/authentication changes, and when support or recovery access paths change.

## Inputs
- Two clean product instances or equivalent isolated test deployments.
- Installation, first-use, factory-reset, recovery, maintenance, and support flows.
- Baseline product tier/configuration and supported authentication documentation.

## Procedure
1. Start two clean instances and document the initial credential behavior for every administrative, local, service, maintenance, recovery, and support entry point.
2. Confirm the instances do not receive one universally shared manufacturer default password.
3. Verify the normal setup path requires creation of a secure credential, uses an instance-unique initial credential, or uses another controlled bootstrap mechanism before authenticated functionality is exposed.
4. Perform factory reset, reinstall, and recovery operations and confirm they do not restore a universal reusable credential.
5. Inspect documented maintenance, rescue, manufacturing, and support paths for hidden or reusable default credentials.
6. Verify remote administrative interfaces are not made easier to reach by an insecure credential default.
7. Record any legacy deployment that still relies on default credentials and the supported migration/remediation path.
8. Retest all affected entry points after remediation.

## Escalation
Treat a universal default credential, a reset path that restores one, or an undocumented reusable support credential as a release/security defect requiring remediation before relying on customer hardening.

## Evidence
- Clean-instance credential comparison.
- First-use/setup evidence.
- Factory-reset and reinstall results.
- Recovery/support/maintenance-path review.
- Legacy migration and retest evidence where applicable.

## Completion criteria
Every supported entry point establishes credentials without a universal manufacturer password and remains secure across first use, reset, recovery, and maintenance flows.

## Source basis
- CISA/FBI, Product Security Bad Practices, updated January 17, 2025: https://www.cisa.gov/news-events/alerts/2025/01/17/cisa-and-fbi-release-updated-guidance-product-security-bad-practices
- CISA, Secure by Design Alert — How Manufacturers Can Protect Customers by Eliminating Default Passwords: https://www.cisa.gov/sites/default/files/2023-12/SbD-Alert-How-Software-Manufacturers-Can-Protect-Customers-by-Eliminating-Default-Passwords-508c_0.pdf
