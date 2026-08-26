# srs-sender-rewriting-scheme

**Issue:** SPF evaluates the envelope sender (`MAIL FROM`) against the IP of the *last* sending server. When your service forwards mail — a custom domain alias, a mailing list, a support-inbox redirector — the message keeps its original `MAIL FROM` but now originates from your IP, so SPF fails at the final receiver and legitimate forwarded mail lands in spam or is rejected. The Sender Rewriting Scheme (SRS) fixes this by cryptographically rewriting the envelope sender to your forwarding domain at the hop where you resend, while encoding the original sender so bounces can still return to the true origin. Implemented naively it breaks DMARC alignment, forges bounce paths, or rewrites too aggressively; implemented well it pairs with ARC to preserve authentication end to end.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## The problem SRS solves

1. **SPF is hop-by-hop and forwarding breaks it.** The original domain's SPF record authorizes the original sender's servers, not yours. Any intermediate that re-sends (forwarders, mailing lists, filters that re-inject) invalidates SPF for downstream receivers.
2. **Bounce routing constrains the fix.** You cannot just rewrite `MAIL FROM` to a bare address of your own, because then bounces for mail that the original sender caused would go to you forever — you become a backscatter source. SRS encodes the original address inside the rewrite so you can decode and re-inject the bounce toward the true originator.
3. **DMARC changed the calculus.** Rewriting the envelope sender alone can make DMARC *pass* on your domain for mail you do not author (alignment now points at you) — useful for deliverability, dangerous if it launders spoofed mail. Microsoft 365's SRS-based SMTP forwarding has documented loopholes where spoofed input passes DMARC after a forwarding hop; forwarders carry responsibility for what they re-sign.
4. **Headers must stay intact.** SRS rewrites only the envelope. The `From:` header, DKIM signature, and message body are untouched — DKIM survives forwarding (which is why receivers rely on it), and SRS exists purely to repair the envelope-level SPF/bounce mechanics.

## Address formats

1. **SRS0 for the first hop.** Format `SRS0=HHH=TT=domain=local@forwarder.example`, where `HHH` is a keyed HMAC over the following fields, `TT` is a date stamp limiting the address's validity (typically a few days), then the original domain and local part with `@` folded to `=`. Bounces decoded at your forwarder are re-aimed at `local@domain` after hash and timestamp validation.
2. **SRS1 for subsequent hops.** A second forwarder that sees an `SRS0=` local part must not wrap it again in SRS0 (or addresses grow unboundedly). Instead it rewrites to `SRS1=HHH=forwarder-one=HHH=TT=domain=local@forwarder-two` — embedding the first forwarder's rewrite under a new outer signature.
3. **Rewrite only when resending.** Addresses you merely relay (transparent proxying without generating a new SMTP session) do not need SRS; the rewrite belongs at the hop that initiates a fresh outbound SMTP transaction under your control.
4. **Keep the rewrite reversible and time-bounded.** The timestamp field is the anti-replay guard: a bounce arriving for an SRS0 address past validity should be discarded (with logging) rather than forwarded — infinite bounce loops between two misconfigured forwarders are a classic failure mode otherwise.

## Implementation guidance

1. **Use a maintained library, not hand-rolled crypto.** `pysrs`, Perl's SRS modules, or the SRS support built into Postfix (via `sender_canonical_maps` with SRS patches), OpenSMTPD, and commercial forwarders implement the HMAC scheme; subtle key or format bugs silently strand bounces.
2. **Dedicate a rewrite subdomain.** Rewritten senders should use a dedicated subdomain (e.g., `srs.forwarder.example`) with its own SPF (`v=spf1 ip4:<your IPs> -all`) and, if you sign it, DKIM. This isolates the rewritten-mail reputation from any first-class sending domains.
3. **Publish correct SPF for the rewrite domain.** Since all forwarded mail now has an envelope from your subdomain, its SPF must authorize your forwarding servers with a hard-fail — the whole point is that this hop now passes SPF legitimately.
4. **Handle bounces in both directions.** Inbound: decode SRS0/SRS1 addresses, verify hash and timestamp, and generate a new DSN to the embedded originator (rate-limited). Outbound: never let a bounce to an SRS address be double-rewritten into another SRS address.
5. **Microsoft 365 operators inherit SRS implicitly.** Exchange Online has applied SRS to SMTP (mailbox) forwarding since 2023 rather than rewriting the forwarding mailbox — if you build on M365 forwarding, you are already emitting SRS0 addresses from `*.mail.onmicrosoft.com`-style tenants; verify what your outbound envelope actually looks like.

## SRS, DMARC, and ARC interplay

1. **SRS fixes SPF but can fake DMARC alignment.** After rewriting, the envelope domain is yours, so SPF-based DMARC alignment credits your forwarding domain — a spoofed original message can appear DMARC-passing to the final receiver (the documented M365 loophole). This is why forwarders must validate DMARC on *inbound* before resending, quarantining what fails.
2. **Preserve DKIM, always.** Never modify the body or signed headers of forwarded mail. If your forwarder adds footers, subject tags, or footer-removal logic, you are breaking the signature that lets the final receiver authenticate the true author — the one mechanism that survives forwarding untouched.
3. **Add an ARC seal at the rewrite hop.** Authenticated Received Chain (RFC 8617) lets your forwarder cryptographically attest the inbound authentication results (what SPF/DKIM/DMARC said *before* the rewrite). Receivers that validate ARC can then trust the original verdicts instead of the laundered post-rewrite ones. SRS plus ARC is the 2025-2026 standard pairing for serious forwarding infrastructure.
4. **Forward abuse reports and DMARC feedback to the original sender where possible.** If you forward mail for other domains, their DMARC aggregate reports will follow the rewritten envelope to you; publishing ARR (Authenticated Received Chain)-aware tooling or at least honoring `RFC5321.ORCPT`-style accounting helps senders see that their mail was forwarded, not rejected.
5. **Decide policy for unauthenticated inbound.** Define explicitly what happens when inbound mail fails the original sender's DMARC (p=quarantine/reject) before you forward it: honoring the original policy (do not forward, or forward into a quarantine-visible path) is the abuse-safe default; blanket forwarding plus SRS makes you a laundering service.

## Operational pitfalls

1. **Key rotation with grace.** Rotate the HMAC secret periodically but accept addresses signed by the previous key for one overlap window; otherwise every in-flight bounce dies at rotation.
2. **Monitor decode failures.** Alert on bounce-volume spikes hitting invalid SRS addresses — usually a symptom of key mismatch across a forwarder pool (different pods with different secrets) or an upstream loop.
3. **Test the loop path end to end.** Chain two of your own forwarders, force a bounce, and verify the DSN arrives at the true originator exactly once. Bounce loops and doubled DSNs are integration bugs that only appear in the multi-hop case.
4. **Keep envelope and headers coherent in logs.** Log both the original `MAIL FROM` and the rewritten address on every forwarded message; deliverability forensics (why did this receiver reject?) are impossible when you only recorded one side.
5. **Do not SRS your own outbound application mail.** SRS is for mail you forward on behalf of third parties. Your own transactional sends should use stable, dedicated return paths (see VERP) — wrapping them in SRS0 adds nothing and complicates bounce attribution.
