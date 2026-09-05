# Unpredictable Object IDs Do Not Replace Access Control

**Issue:** A team uses UUIDs or other hard-to-guess identifiers and treats identifier unpredictability as the primary defense against cross-user object access.

**Date:** 2026-09-04
**Author:** ORCHORDS
**Status:** documented

## The lesson

OWASP API1:2023 recommends random, unpredictable record identifiers as defense in depth, but still requires object-level authorization checks in every function that uses client input to access a record. Identifier secrecy is not an authorization policy.

## Engineering rule

- Use unpredictable identifiers where appropriate to reduce enumeration opportunities.
- Still evaluate whether the authenticated caller may perform the requested action on the resolved object.
- Assume identifiers can leak through logs, links, notifications, referrers, browser history, support records, integrations, or other application behavior.
- Write regression tests that fail if authorization is removed even when identifiers remain random.

## Verification

- Obtain a valid identifier belonging to another test identity and request it directly.
- Confirm knowledge of the exact identifier is insufficient for access.
- Run object-authorization tests against both sequential and random-looking identifiers where supported by fixtures.

## Official source

- OWASP API1:2023 Broken Object Level Authorization: https://owasp.org/API-Security/editions/2023/en/0xa1-broken-object-level-authorization/
