# Android app-access-risk response

**Issue:** Play Integrity app-access-risk signals can indicate apps that may capture, control, or overlay a protected flow. Treating a verdict as infallible or blocking without recovery can lock out legitimate accessibility and support tools.

**Date:** 2026-08-18
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Controls and implementation
Request and verify integrity tokens server-side, bind nonce/request details to the protected action, enforce freshness and replay resistance, and interpret only documented verdict values. Use graded responses: warn, mask sensitive data, require stronger confirmation, or block the narrow high-risk action. Provide an accessible recovery path and avoid enumerating installed apps.

## Verification
Test missing/stale/replayed tokens, unknown verdicts, accessibility services, screen sharing, overlays, rooted/emulated environments, API outage, and retry. Confirm ordinary low-risk use still works when the signal is unavailable.

## Gotchas
A risk verdict is contextual evidence, not malware detection or identity proof. Policies and verdict availability can change.

## Sources
- Android Developers, [App access risk verdict](https://developer.android.com/google/play/integrity/app-access-risk)
- Android Developers, [Play Integrity standard requests](https://developer.android.com/google/play/integrity/standard)
