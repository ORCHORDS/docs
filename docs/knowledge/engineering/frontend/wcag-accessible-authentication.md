---
title: "WCAG 2.2 Accessible Authentication (Minimum)"
owner: "Documentation Maintainer"
status: "approved"
classification: "public"
last-reviewed: "2026-09-01"
review-cycle: "90 days"
next-review: "2026-11-30"
---

# WCAG 2.2 Accessible Authentication (Minimum)

## Requirement
SC **3.3.8 Accessible Authentication (Minimum)** is **Level AA**. An authentication process must not require a cognitive function test unless at least one exception applies: an **Alternative** method avoids such a test; a **Mechanism** assists completion; the test is **Object Recognition**; or the test identifies non-text content the user personally supplied.

Cognitive tests include remembering a password, transcribing an OTP, solving arithmetic, or reproducing a pattern. The criterion does not prohibit passwords: permitting password managers and paste provides a mechanism. CAPTCHAs are not automatically exempt; object recognition is an exception, while distorted-text transcription needs an accessible alternative or assistance. SC 3.3.9 is the stricter AAA criterion without the object-recognition and personal-content exceptions.

## Implementation
Use `autocomplete="username"`, `current-password`, `new-password`, and `one-time-code` correctly. Permit paste into password and code fields. Avoid JavaScript that clears values populated by managers. Support WebAuthn/passkeys as a non-memory path, while ensuring account recovery does not reintroduce inaccessible puzzles. Magic links avoid transcription when the link itself completes authentication; requiring the user to memorize a code does not.

If risk controls challenge a login, offer an equivalent method at the same assurance level. Do not make users fail a CAPTCHA before discovering the alternative. Describe recovery prerequisites before lockout.

## End-to-end test
Complete sign-in, MFA, password reset, account recovery, reauthentication, and suspicious-login challenges using a password manager or paste and without unaided recall, calculation, transcription, or puzzle solving. Test keyboard and screen reader operation, expired codes, resend, device switching, and manager-generated passwords. Inspect event handlers for blocked clipboard events and nonstandard fields that defeat autofill.

For each cognitive step, record the exact exception relied upon and demonstrate it. A “paste allowed” result needs evidence that the complete value can be inserted and submitted, not merely that the paste event fires. Common failures include splitting OTP fields that reject full-code paste, disabling managers through custom controls, and offering audio transcription as the only CAPTCHA alternative.

## Sources
- [WCAG 2.2 — SC 3.3.8](https://www.w3.org/TR/WCAG22/#accessible-authentication-minimum)
- [Understanding Accessible Authentication](https://www.w3.org/WAI/WCAG22/Understanding/accessible-authentication-minimum.html)
