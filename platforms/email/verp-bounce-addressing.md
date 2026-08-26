# verp-bounce-addressing

**Issue:** Bounce (DSN) messages are sent to the envelope sender (`MAIL FROM`), so when a bulk or transactional send goes out with a single shared return path, every bounce lands in one undifferentiated mailbox and you must parse free-text DSN bodies to figure out *which* recipient bounced. That parsing is brittle across hundreds of receiving MTAs and languages. VERP (Variable Envelope Return Path) solves it by encoding the recipient (and campaign/message identifiers) into a unique per-recipient envelope sender, so the mere act of delivering the bounce back to you identifies the target — no body parsing required. Systems that suppress dead addresses, monitor complaint-worthy bounce spikes, or must attribute bounces per campaign need VERP-grade attribution.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Mechanism

1. **Encode recipient into the local part.** For a message to `alice@example.org`, the envelope sender becomes something like `b=aGVsbG8=@bounces.yourdomain.com` or the classic `bounces+alice=example.org@bounces.yourdomain.com` (with `@` rewritten to `=` so it survives as a local part). The bounce for that recipient is then delivered to that exact address.
2. **Use a dedicated bounce domain.** The return-path domain should be a subdomain dedicated to bounce processing (`bounces.` or `bounce.`), which you may also use for DMARC alignment, SPF `include`s, and DKIM signing separate from the visible From domain.
3. **Sign the address to prevent forgery.** Unsigned VERP addresses let anyone spoof a bounce to `b=...@bounces.yourdomain.com` and poison your suppression list. Include an HMAC over the recipient + message-id + expiry in the address (many implementations pack it into the token) and verify it before acting on any bounce.
4. **Keep addresses bounded in length.** The local part of the rewritten address must stay within the 64-octet limit conservative servers enforce. Base64url or short hash tokens keep it compact even for long internationalized recipient addresses.

## Implementation patterns

1. **Transactional sends: per-message VERP.** Each outbound message gets a fresh signed return path tied to the message ID in your database. When the bounce arrives, a single lookup maps token to message + recipient, giving you bounce reason, latency, and campaign in one row.
2. **Bulk sends: encode campaign too.** For lists, pack recipient and campaign into the token so a single inbound bounce attributes both. This lets you compute per-campaign bounce rates (the metric Gmail/Yahoo thresholds police) without joining on message logs.
3. **Catch-all inbound handler.** Configure the bounce subdomain's MX to route everything to one processor (a webhook, LMTP pipe, or catch-all mailbox polled via IMAP). Match on the encoded token, not on the display or header addresses — bounces arrive addressed to the envelope target, but DSN headers vary wildly.
4. **Prefer synchronous rejection where possible.** Many recipient servers now reject at the SMTP layer (4xx/5xx during the DATA/RCPT phase) instead of sending asynchronous DSNs. Capture those transport-level codes directly from your sending session; reserve VERP processing for the asynchronous remainder. Word to the Wise's 2026 writing on asynchronous bounces argues for minimizing them altogether — they generate backscatter and are increasingly dropped.
5. **Reuse token state machine, not ad-hoc flags.** Model per-recipient state as transitions: delivered, soft-bounced (with attempt count), hard-bounced, complained, unsubscribed. VERP events feed hard/soft classification; only repeated soft bounces (conventionally 3-5 over ~72 hours) escalate to suppression.

## Bounce processing pipeline

1. **Classify hard vs soft from the DSN status code.** Use the RFC 5965-enhanced status (`5.1.1` mailbox unavailable = hard; `4.2.1` greylisted = soft; `5.7.1` policy rejection may indicate reputation trouble, not a dead address). Persist the raw status string alongside the classification for later re-evaluation.
2. **Suppress hard bounces immediately and durably.** A hard bounce must never be re-sent, even by a different campaign. Suppression keyed on the normalized recipient address (lowercase, trimmed) wins over any later list import containing the address.
3. **Rate-limit your own processing.** A misconfigured remote can flood your bounce domain with a bounce storm. Token-bucket the inbound handler and alert on volume anomalies rather than processing unbounded streams into your database.
4. **Report and alert on spikes.** Per-campaign hard-bounce rate crossing 2-3% is both a deliverability red flag (Gmail/Yahoo expect <0.3% spam-complaint, low bounce) and a signal your acquisition source is bad. VERP makes the metric cheap; wire it into campaign dashboards.

## Edge cases and pitfalls

1. **Auto-responders are not bounces.** Out-of-office and challenge-response replies go to the same return path. Filter on `Auto-Submitted: auto-replied` headers and DSN `Action: failed` fields — do not suppress addresses merely because a machine replied.
2. **Late bounces arrive after state changes.** A recipient may unsubscribe between send and bounce; the VERP event must reconcile (do not "re-activate" an unsubscribed address because a stale bounce arrived, and do not re-send to a just-bounced address still in today's campaign batch).
3. **Some receivers rewrite or drop the return path.** A minority of forwarding setups break VERP by rewriting envelopes (SRS on their side); a small percentage of bounces will arrive unattributable. Accept the loss and monitor its rate — growth signals your mail is increasingly being forwarded.
4. **Do not put VERP addresses in headers.** The encoded address belongs only in the envelope. Header `Return-Path` is added by the *final* receiving MTA; writing it yourself confuses threading and leaks tokens.
5. **Keep SPF/DKIM aligned on the bounce domain.** Because VERP changes your envelope sender domain, that domain needs its own SPF and DKIM signing. Misaligned bounce-domain authentication shows up in DMARC reports as failures from your own infrastructure — a self-inflicted reputation hit.
