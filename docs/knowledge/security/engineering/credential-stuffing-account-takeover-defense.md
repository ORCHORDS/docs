# credential-stuffing-account-takeover-defense

**Issue:** Attackers replay billions of username/password pairs harvested from third-party breaches against a login endpoint. The requests are individually "valid" — correct protocol, correct passwords for users who reuse them — so the attack exploits credential reuse, not a code flaw (OWASP OAT-008). Without layered defenses, a quiet list-testing run converts directly into account takeover (ATO): drained accounts, fraud, and spam sent from trusted identities. The 2025+ reality is that any login form without breached-password screening, bot management, and phishing-resistant MFA is a standing invitation.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Pre-authentication defenses

1. **Screen new and changed passwords against known-breach corpora.** Check k-anonymized against the Have I Been Pwned breach corpus (or an IdP's built-in check) at registration and password change; NIST 800-63B explicitly directs verifiers to reject passwords found in prior breaches — this is the single highest-value control.
2. **Enforce length-first composition policy.** Prefer 12+ character minimums and block the top common-password lists over forced symbol/rotation rituals that drive users to `Summer2024!` patterns; also block passwords containing the account's own email or username.
3. **Deploy phishing-resistant MFA — passkeys/WebAuthn first.** FIDO2 credentials cannot be replayed from a stuffed password alone; SMS OTP is better than nothing but is phishable and SIM-swappable, so rank it last.
4. **Rate-limit and credential-limit per identity, not just per IP.** Attackers rotate IPs cheaply; counters keyed on username and password-hash value (with caching) catch distributed low-and-slow spraying against the same account.
5. **Return generic failures with constant-ish timing.** Uniform "invalid email or password" responses and equalized work (always hash once against a dummy secret on unknown users) deny enumeration oracle behavior to list-testers.
6. **Add a progressive friction ladder.** Step up to CAPTCHA/Turnstile, device checks, or email confirmation after N failed attempts on an account or from a fingerprint — friction aimed at anomalies, not at every human.

## Detecting automated list-testing

1. **Treat OAT-008 as its own signal class.** Classic WAF logic looks for malformed requests; stuffing traffic is well-formed, so detection must be behavioral: failure ratios, credential velocity, and population-level patterns rather than single-request signatures.
2. **Watch the login funnel metrics.** Spikes in attempts-per-IP distribution, login failures concentrated on dormant accounts, identical user-agent strings across diverse ASNs, and improbably uniform timing (fixed intervals) are the canonical stuffing signatures.
3. **Fingerprint clients beyond IP.** TLS JA3/JA4 fingerprints, HTTP/2 settings order, header ordering, and navigator characteristics separate scripted clients from browsers even when the script runs through residential proxy pools.
4. **Instrument per-account anomaly signals.** Geographically impossible travel, new-device login plus immediate profile changes (email/password/MFA resets), and login followed by rapid enumeration actions are ATO indicators that should trigger step-up or session kill.
5. **Canary the dormant-account blast radius.** Stuffing lists are full of stale credentials; monitoring login attempts against long-inactive accounts gives a clean, low-noise early-warning channel.
6. **Centralize signals so IDP, WAF, and app see the same identity risk.** A risk score shared across login, password reset, and sensitive-action endpoints prevents attackers from pivoting to the weakest adjacent flow once login hardens.

## Response and recovery

1. **Kill and re-verify sessions on confirmed ATO.** Revoke all refresh tokens and passively-invalidated sessions for the account, force re-authentication with MFA, and notify the user out-of-band through a channel the attacker does not control.
2. **Undo the attacker's persistence first.** Rotate the email address, password, and MFA bindings they added; account recovery that skips this just hands the account back.
3. **Rate-limit and monitor the password-reset flow as fiercely as login.** Reset endpoints inherit email enumeration, token brute-force, and host-header poisoning risks — they are a primary ATO pivot and must not be the soft flank.
4. **Block check at password change, not just login.** If a stuffed session changes a victim's password, screen the new password against breach corpora and step-up authentication before accepting the change.
5. **Prepare credential-notification playbooks.** When your users' emails appear in a new breach dump, notify and nudge password change + passkey enrollment before attackers operationalize the list.
6. **Post-incident, measure stuffing attempts against accounts compromised.** That ratio is the KPI that tells you whether defenses are working; log it per incident.

## Verification

1. **Simulate a stuffing run** with a few hundred credentialed requests from rotating IPs against a test tenant; confirm rate limits, step-up triggers, and alerting all fire before the 20th attempt.
2. **Attempt registration with a known-breached password** (`P@ssw0rd`, top-100 list entries) and confirm rejection with actionable messaging.
3. **Confirm unknown-user and wrong-password responses are indistinguishable** in content, status code, and approximate latency.
4. **Exercise the ATO playbook end to end** — force-compromise a test account, verify session revocation, recovery takeover-undo steps, and user notification all execute in order.
5. **Verify passkey-only accounts cannot be entered with any password** — the login path for passkey accounts should not even accept password attempts.

**Source:** [OWASP Automated Threats — OAT-008 Credential Stuffing](https://owasp.org/www-project-automated-threats-to-web-applications/), [NIST SP 800-63B](https://pages.nist.gov/800-63-3/sp800-63b.html), [Have I Been Pwned Pwned Passwords](https://haveibeenpwned.com/Passwords).
