# Function Authorization Must Be Enforced Per Operation

**Issue:** An API authenticates the caller successfully but does not consistently check whether that caller may invoke each specific operation.

**Date:** 2026-09-04
**Author:** ORCHORDS
**Status:** documented

## The lesson

OWASP API5:2023 treats function-level authorization as a distinct control boundary. Authentication or object ownership does not automatically authorize administrative, destructive, export, role-management, or other privileged functions.

## Engineering rule

- Define the required role, capability, or policy for every sensitive operation.
- Deny access by default and grant functions explicitly.
- Apply the same authorization mechanism to every code path that reaches the function.
- Test alternate HTTP methods and equivalent routes, not just the documented happy path.
- Keep authorization policy centrally understandable even when enforcement is distributed.

## Verification

- Build a role-by-operation matrix and execute negative tests for every disallowed combination.
- Change `GET`, `POST`, `PUT`, `PATCH`, and `DELETE` where routes accept or route methods differently and verify privilege boundaries remain intact.
- Confirm internal refactors cannot bypass the authorization layer by calling the same business function through another controller or route.

## Official sources

- OWASP API5:2023 Broken Function Level Authorization: https://owasp.org/API-Security/editions/2023/en/0xa5-broken-function-level-authorization/
- OWASP WSTG API Broken Function Level Authorization: https://owasp.org/www-project-web-security-testing-guide/latest/4-Web_Application_Security_Testing/12-API_Testing/04-API_Broken_Function_Level_Authorization
