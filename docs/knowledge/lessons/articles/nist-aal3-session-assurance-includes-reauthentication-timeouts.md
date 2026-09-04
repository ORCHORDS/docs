# NIST AAL3 Session Assurance Includes Reauthentication Timeouts

**Issue:** A service performs strong AAL3 authentication once and then treats the authenticated browser or application session as indefinitely equivalent to that initial assurance event.

**Date:** 2026-09-04
**Author:** ORCHORDS
**Status:** documented

## The lesson

NIST SP 800-63B-4 includes periodic reauthentication in the assurance model. For AAL3, the overall timeout for reauthentication SHALL be no more than 12 hours, the inactivity timeout SHOULD be no more than 15 minutes, and AAL3 reauthentication follows the same AAL3 requirements as initial authentication.

## Engineering rule

- Treat session lifetime and reauthentication as part of assurance-level conformance, not as a separate convenience setting.
- Track both overall session age and inactivity according to the target NIST level.
- Preserve AAL3 requirements during reauthentication instead of silently falling back to a weaker factor.
- Reassess long-lived API, desktop, and browser sessions that claim to preserve AAL3 assurance indefinitely.

## Verification

- Measure the configured overall and inactivity timers for AAL3 sessions.
- Confirm a session exceeding the required overall limit cannot continue without AAL3 reauthentication.
- Confirm reauthentication retains phishing resistance, replay resistance, non-exportable-key requirements, and authentication intent as applicable to AAL3.

## Official source

- NIST SP 800-63B-4, AAL3 Reauthentication: https://pages.nist.gov/800-63-4/sp800-63b.html
