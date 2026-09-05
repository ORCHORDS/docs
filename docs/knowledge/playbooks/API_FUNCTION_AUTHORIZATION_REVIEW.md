# API Function Authorization Review

## Trigger
Run before releasing a new privileged API operation, after authorization-policy changes, and during periodic API security review.

## Inputs
- API specification or observed route list.
- Caller roles/capabilities.
- Sensitive operations and supported HTTP methods.
- Test credentials representing allowed and disallowed roles.

## Procedure
1. Build a matrix of sensitive operations against caller roles or capabilities.
2. Mark the expected allow/deny result for every matrix cell before testing.
3. Invoke each operation with an allowed identity and confirm expected success.
4. Invoke each operation with lower-privilege identities and confirm denial before the business action executes.
5. Repeat tests with alternate HTTP methods and equivalent routes where the router exposes them.
6. Test privileged operations directly without relying on client UI navigation or hidden controls.
7. Record inconsistent enforcement, bypass paths, and remediation owners.
8. Retest every failed matrix cell after remediation.

## Escalation
Treat successful execution of a privileged function by an unauthorized caller as an access-control defect requiring security triage before release or continued exposure.

## Evidence
- Role/capability-by-operation matrix.
- Request/response evidence for positive and negative tests.
- Route/method inventory tested.
- Findings and retest results.

## Completion criteria
All sensitive operations enforce the documented authorization decision across supported and alternate reachable methods/routes, with no UI-only control dependency.

## Source basis
- OWASP API5:2023 Broken Function Level Authorization: https://owasp.org/API-Security/editions/2023/en/0xa5-broken-function-level-authorization/
- OWASP WSTG API Broken Function Level Authorization: https://owasp.org/www-project-web-security-testing-guide/latest/4-Web_Application_Security_Testing/12-API_Testing/04-API_Broken_Function_Level_Authorization
