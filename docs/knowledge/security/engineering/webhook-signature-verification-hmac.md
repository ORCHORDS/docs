# webhook-signature-verification-hmac

**Issue:** The app exposes a public, unauthenticated HTTP endpoint to receive provider webhooks (payments, git hosts, messaging). Without signature verification, anyone who discovers the URL can forge events — fake "payment succeeded" deliveries, injected commands into deploy pipelines, or data exfiltration via crafted payloads. Teams that do verify often do it wrongly: comparing HMACs with `==`, verifying a re-serialized body instead of the raw bytes, skipping timestamp checks, or accepting events after the secret has rotated.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Correct verification mechanics

1. **HMAC the exact raw request body, never a re-serialization.** Compute HMAC-SHA256 over the untouched byte stream the provider sent; JSON re-parsing and re-stringifying changes key order and whitespace, guaranteeing signature mismatch. In Express, mount `express.json()` after the webhook route or use `express.raw({ type: 'application/json' })` on it; in Next.js App Router, read `await req.text()`/`arrayBuffer()` and disable the body parser on that route.
2. **Compare digests in constant time.** Use `crypto.timingSafeEqual` (Node), `hmac.compare_digest` (Python), or the provider SDK's verify function; `===` comparison leaks the signature byte-by-byte to an attacker who can measure response times.
3. **Extract the signature from the correct header with the correct scheme.** Stripe uses `Stripe-Signature: t=<timestamp>,v1=<hmac>` (signed payload is `t + '.' + body`); GitHub uses `X-Hub-Signature-256: sha256=<hex>`; Slack uses `X-Slack-Signature` with its own basestring. Read the provider's spec — do not guess the basestring.
4. **Check all delivered signatures, not just the first.** Stripe sends multiple `v1` values during secret rotation; succeed if any matches the current secret, and log which one matched so you can retire old secrets.
5. **Reject unsigned or malformed headers explicitly.** A missing `v1`, unparsable timestamp, or wrong digest length must produce a 400 — silent acceptance of anything unparsable is how verification code degrades into a no-op.

## Replay protection

1. **Enforce a timestamp tolerance window.** Stripe's tolerance default is 5 minutes: reject deliveries whose `t=` timestamp is outside the window, because a captured valid request is otherwise replayable forever.
2. **Deduplicate by event ID.** Providers retry on failure and deliver at-least-once; store processed event IDs (with TTL ≥ tolerance window × retry span) in Redis/KV and short-circuit repeats idempotently — this closes both replay-after-capture and duplicate-processing bugs.
3. **Bind the event to the endpoint secret of record.** An event signed by an old, revoked secret must fail after rotation cutover; keep a strict date when the previous secret stops being accepted rather than accepting both indefinitely.
4. **Reject events for other accounts/endpoints.** Check the provider account ID or webhook UUID inside the payload matches yours; cross-tenant event injection has happened even when signatures were valid for the provider.
5. **Log rejected deliveries with reason codes** (bad signature vs expired vs duplicate) — an attacker probing your verification is visible in that distribution long before they succeed.

## Operational hardening

1. **Return 2xx fast, process async.** Acknowledge after durable enqueue, not after business processing; slow handlers cause provider retry storms that amplify into duplicate events and rate-limit pain.
2. **Make every handler idempotent by design.** Treat each event as "the provider now claims state X" — fetch authoritative state via API before acting on high-value events like payment confirmation; never trust webhook payload amounts alone for fulfillment.
3. **Rotate endpoint secrets like credentials.** Use the provider's dual-secret window (register new secret, accept both, retire old), store secrets in a secret manager — not env files in git — and rotate on a schedule and on staff change.
4. **Pin webhook routes behind a dedicated middleware.** One shared verify-with-raw-body middleware applied to all `/webhooks/*` routes prevents the "new route forgot verification" failure mode; make the unverified route fail closed in tests.
5. **Monitor delivery health from both sides.** Alert on verification-failure rate spikes and on provider-reported endpoint failure rates; a verifier that starts failing 100% is an outage, and one that starts passing 100% after a framework upgrade deserves a second look.
6. **Never expose webhook endpoints on internal services without an additional network gate.** Signature verification plus an IP allowlist of the provider's published webhook ranges is defense in depth — either control failing leaves the other standing.

## Verification

1. **Forge an event with no signature and a wrong signature** — both must 400 without side effects.
2. **Replay a captured valid delivery after the tolerance window** and confirm rejection by timestamp, and again inside the window to confirm dedupe-by-ID handling.
3. **Ship a body-parser ordering test** — POST the same signed body through the full framework stack (Next.js/Express as deployed) and confirm verification still passes; this catches middleware-mutation regressions that unit tests on the verify function miss.
4. **Exercise secret rotation end to end** — events signed with the old secret pass during overlap and fail after retirement, with logs identifying the matching version.
5. **Measure verification on the timing side** — responses to wrong-signature attempts must not get measurably slower as attacker-controlled prefixes approach the real signature.

**Source:** [Stripe webhook signature verification](https://docs.stripe.com/webhooks/signature), [GitHub validating webhook deliveries](https://docs.github.com/en/webhooks/using-webhooks/validating-webhook-deliveries).
