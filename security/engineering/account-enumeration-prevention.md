# account-enumeration-prevention

**Issue:** Account enumeration leaks whether a username or email exists in a system through observable differences in responses. A login endpoint that says "user not found" versus "wrong password", a registration flow that says "email already registered", or a password-reset request that responds faster for existing accounts each confirm to an attacker that an account exists. Enumeration is the reconnaissance step that makes credential stuffing, targeted phishing, and password spraying dramatically more effective: attackers filter stolen credential dumps against your endpoints and only pay for attacks on real accounts. OWASP's authentication and forgot-password cheat sheets treat identical responses (content and timing) as the baseline control, and real advisories (for example, a Directus password-reset timing flaw, GHSA-jr94-gj3h-c8rf) show the class remains live in 2025-era codebases. The engineering challenge is that "just return the same message" conflicts with usable error UX, signup validation, and password-reset UX, so each flow needs deliberate design.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Enumeration Vectors

1. **Login response divergence.** Distinct messages or codes for unknown-user versus wrong-password is the textbook vector; even a different error ID, field name, or localization key in the JSON body is enough signal.
2. **Registration collision handling.** Rejecting signup with "email in use" hands attackers a free oracle that doubles as a contact-discovery tool for phishing; verification should move to an email side-channel instead.
3. **Password-reset response asymmetry.** Anything that differs for known versus unknown addresses — response body, status code, whether an email token is generated, or how long the request takes — enumerates accounts (the Directus GHSA-jr94-gj3h-c8rf flaw was exactly a timing leak in reset handling).
4. **Timing side channels.** Existing accounts trigger a database hit plus password hashing; unknown accounts fail fast. Per-account hash work is hundreds of milliseconds, so the delta is measurable over the public internet with statistical averaging.
5. **Behavioral and out-of-band tells.** Password-reset emails that arrive only for existing accounts, MFA prompts that appear only for provisioned users, and different rate-limit responses after N attempts against a real account all confirm existence indirectly.

## Response Normalization

1. **One generic message per flow.** Login returns the same "invalid credentials" response for every failure mode; password reset always answers "if an account exists, instructions have been sent"; registration always claims success and resolves conflicts by email.
2. **Normalize the whole response, not just the text.** Status code, headers, body shape, error codes, and timing must match across branches — attackers diff responses mechanically, and any byte or millisecond of divergence is a signal.
3. **Do not leak via side channels at the edge.** Ensure CDN caching, compression, or WAF rules do not treat the branches differently (for example, caching one variant), which reintroduces divergence even when application code is uniform.
4. **Centralize the pattern.** Implement generic-response handling once in a shared middleware or response helper so every new endpoint inherits it, rather than relying on each controller to remember.

## Timing Side Channels

1. **Perform equivalent work for unknown identities.** When the user does not exist, hash a dummy password with the same algorithm and parameters (the same Argon2 configuration used for real accounts) so both branches take the same time; OWASP's forgot-password guidance recommends exactly this dummy-work approach.
2. **Fix versus mitigate.** Dummy work narrows the gap but does not perfectly equalize database lookups, allocation, and serialization; treat it as mitigation and add per-source rate limits so statistical timing needs more samples than an attacker can afford. Prefetch or precompute hashes where possible to tighten equality.
3. **Measure, then enforce a budget.** Add a CI or canary test that times both branches over many iterations and fails if the distributions separate beyond a threshold — timing regressions are silent otherwise.
4. **Mind downstream variance.** Queue latency, DB connection pools, and retry logic amplify branch differences; keep the dummy path executing the same subsystems as the real path to whatever extent the design allows.

## Registration and Password Reset Hardening

1. **Always-register pattern.** For unverifiable identities, create a "pending" record with identical outward behavior and send an email explaining the account already exists or offering to claim it, so the HTTP response never differs.
2. **Deliver everything by side channel.** Reset tokens, activation links, and "you tried to sign up" notices go to the email address and never appear in HTTP responses; the response body carries no account state at all.
3. **Opaque, single-purpose tokens.** Reset tokens are high-entropy, single-use, short-lived, and reveal nothing about account existence in their format; a token-submit endpoint must also avoid diverging between "expired" and "unknown" where feasible.
4. **Uniform rate limits.** Apply identical throttling to known and unknown identifiers so attacker probing cannot use limit-hit differences as an oracle, and key limits on request cost, not on account existence.

## Layered Controls

1. **Rate limiting and lockout on the identifier.** Enumeration is high-volume by nature; progressive per-source and per-identifier throttling plus CAPTCHA/Turnstile on suspicious bursts raises the cost above the value of the oracle.
2. **Breach-password screening.** Pair enumeration resistance with checking candidate passwords against compromised-credential lists, since the end goal of most enumeration is credential abuse.
3. **Monitoring for enumeration-shaped traffic.** Alert on many distinct identifiers from one source, unusual ratios of unknown-to-known identifiers, or latency-averaging patterns (many slow repeated probes) that indicate timing analysis.
4. **Test it like an attacker.** Automated checks should replay registration, login, and reset for existing and non-existing identities and assert byte-identical responses plus statistically indistinguishable timings before every release.
