# URL Shape Is Not an Authorization Boundary

**Issue:** Administrative endpoints are assumed safe because they live under an `admin` path or are absent from the normal client UI.

**Date:** 2026-09-04
**Author:** ORCHORDS
**Status:** documented

## The lesson

OWASP API5:2023 explicitly warns that endpoint paths do not determine whether a caller is authorized. Attackers can guess routes, change methods, replay requests, or call administrative functions directly even when the official client never exposes those controls.

## Engineering rule

- Treat route names and UI visibility as discoverability concerns, never access controls.
- Enforce authorization after routing and before the privileged business action executes.
- Apply the same policy when an administrative function shares a controller or resource path with ordinary functions.
- Review undocumented and legacy methods for privilege checks.

## Verification

- Call privileged endpoints directly with lower-privilege credentials without using the official client.
- Guess common administrative paths and test method variations.
- Confirm hidden buttons, client-side route guards, or navigation state are not required for the server-side decision.

## Official source

- OWASP API5:2023 Broken Function Level Authorization: https://owasp.org/API-Security/editions/2023/en/0xa5-broken-function-level-authorization/
