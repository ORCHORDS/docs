# Object Identifiers Are Selectors, Not Authorization

**Issue:** An API treats possession of an object identifier as sufficient evidence that the authenticated caller may read, modify, or delete the selected record.

**Date:** 2026-09-04
**Author:** ORCHORDS
**Status:** documented

## The lesson

OWASP API1:2023 defines broken object-level authorization around client-controlled object identifiers. IDs identify which object the caller is asking about; they do not prove the caller has permission to perform the requested action on that object.

## Engineering rule

- Resolve the requested object and evaluate the caller's authorization for the requested action before returning or mutating it.
- Apply object-level checks to identifiers found in paths, queries, headers, and request bodies.
- Keep authorization decisions independent of whether an identifier appears difficult to guess.
- Test read, update, delete, and other object actions separately because permission can differ by action.

## Verification

- Use two distinct identities with separate objects and swap identifiers across requests.
- Repeat the test for every action exposed on the object.
- Confirm unauthorized requests are rejected before sensitive data is returned or state changes occur.

## Official sources

- OWASP API1:2023 Broken Object Level Authorization: https://owasp.org/API-Security/editions/2023/en/0xa1-broken-object-level-authorization/
- OWASP WSTG API Broken Object Level Authorization: https://owasp.org/www-project-web-security-testing-guide/latest/4-Web_Application_Security_Testing/12-API_Testing/02-API_Broken_Object_Level_Authorization
