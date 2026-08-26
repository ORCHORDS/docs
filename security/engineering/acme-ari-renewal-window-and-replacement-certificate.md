# ACME ARI Renewal Window and Replacement Certificate

**Issue:** Fixed certificate-renewal schedules ignore CA incident guidance and can create synchronized load. ACME Renewal Information lets a CA recommend a randomized renewal window and identify replacements.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** draft

## Controls

- Query ARI when supported and select a random renewal time within the suggested window.
- Persist renewalInfo state and use replaces when obtaining a replacement certificate as specified.
- Fall back to a conservative renewal policy when ARI is unavailable or invalid.
- Never delay beyond certificate validity or local safety margins.

## Verification

- Serve normal, urgent, malformed, expired, and unavailable ARI responses.
- Verify fleet renewal times spread across the window.
- Confirm replacement requests reference the intended prior certificate.

## Gotchas

- ARI is guidance from the CA, not permission to ignore expiry.
- Clock error and scheduler outages still require local margin.

## Official sources

- https://www.rfc-editor.org/rfc/rfc9773.html
