# session-replay-privacy-engineering

**Issue:** Session replay tools (rrweb-based SDKs, PostHog, FullStory, LogRocket, Hotjar, Pendo, Amplitude, Dynatrace) record DOM mutations, keystrokes, and mouse movements to reproduce what users experienced. That recording power is exactly what makes replay a privacy hazard: free-text fields capture emails, card numbers, and health details; the screen itself can display PII that no schema knows about; and courts and regulators treat replay data as personal data processing under GDPR. Legal analyses published in 2025 frame replay risk around consent, transparency, data minimization, and contractual safeguards, with class-action exposure for products that ship replay without masking. The engineering problem is making replay privacy-safe by default: mask before capture in the browser, gate recording on consent, sample aggressively, retain briefly, and control access, so the debugging value survives without collecting a liability.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Masking strategy

1. **Proactive, not reactive masking.** Configure masking for any field where users might enter personal data, not only fields known to contain it; vendor guidance is consistent that the safe default is mask-everything, then unmask deliberately named, provably non-sensitive elements.
2. **Passwords and payment fields are non-negotiable.** Password inputs must be masked by default by the tool; if a vendor requires configuration to do this, treat it as a compliance blocker and fix it before enabling recording anywhere.
3. **Prefer blocking over masking for high-risk regions.** Masking replaces content while keeping layout; blocking (a blockSelector or the vendor equivalent) replaces the entire element with a placeholder. Use blocking for identity panels, payment iframes, and message bodies where even structure or length leaks information.
4. **Mask in the browser, before capture.** Redaction must happen client-side at record time, because once an unmasked frame leaves the page, no server-side scrubber can reliably remove it from an encoded DOM-mutation stream.
5. **Defense in depth server-side.** Client masking can be bypassed by bugs or DOM changes, so also run pattern-based redaction (emails, phone numbers, card numbers with Luhn validation) in the ingestion pipeline before storage, and quarantine replays that trip it.

## Consent and legal basis

1. **Replay is personal data.** Treat every recording as personal data processing under GDPR even with masking, because re-identification through screen content, user IDs, or URL parameters is realistic; pseudonymous is not anonymous.
2. **Explicit opt-in consent for identifiable replay.** Consent must be freely given, informed, and specific; implied consent from continued use is a weak defense that legal commentary specifically flags as high-risk, so tie recording start to an affirmative consent signal.
3. **Honor refusal and control signals.** If the user declines the consent banner, the recording SDK must not initialize at all rather than record-and-delete-later, and GPC-style browser signals should suppress recording where applicable.
4. **Document a DPIA.** Run a Data Protection Impact Assessment for replay tooling before launch, and keep vendor DPAs and subprocessor lists on file, since replay vendors process this data on your behalf.
5. **Support DSARs end to end.** Be able to find, export, and delete every replay tied to a given user identity, which means recording a consented user identifier alongside the replay and honoring erasure requests within your retention system.

## Sampling for value and exposure

1. **Record a small fraction of sessions.** One to ten percent sampling is the common range; every recorded session is both cost and privacy surface area, so blanket recording is the wrong default even where consent exists.
2. **Trigger-based capture beats random capture.** Start or retain recordings disproportionately when something valuable happens: an error, a rage-click burst, a failed funnel step, or a support ticket linkage, which gets diagnostic value from a fraction of the volume.
3. **Never let error-triggered capture bypass consent.** Rage-click and error triggers are sampling aids, not a separate legal basis; a consented-out user must still never be recorded.

## Retention and access control

1. **Short, enforced retention.** Keep recordings for a defined, limited period (30 to 90 days is typical) with automated deletion; indefinite retention of masked-but-identifiable replays undermines the minimization argument entirely.
2. **RBAC plus audit logs on replay viewing.** Restrict who can watch replays by role, log every view with viewer identity, and periodically review those logs; replay libraries are frequently the most abused dataset in an organization when access is open.
3. **Region pinning where required.** For EU-facing products, confirm recordings can be stored and processed in-region and that the vendor's cross-region replication can be constrained or contractually bounded.
