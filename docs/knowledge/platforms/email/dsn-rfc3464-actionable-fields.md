# Delivery Status Notification Actionable Fields

A bounce is a structured document that most systems read like prose. The human-readable text is written for humans and varies wildly across generating MTAs, but underneath sits a machine-parsed `message/delivery-status` part whose fields carry the actual verdict: what was attempted, what happened, why, and whether retrying is worthwhile. RFC 3464 defines this structure, and the difference between a bounce pipeline that classifies accurately and one that guesses is whether it reads the structured fields or scrapes the text. Three per-recipient fields do most of the work - Status, Action, and Diagnostic-Code - and supporting fields supply the retry arithmetic. Getting their semantics exactly right separates correct suppression from permanent list damage.

## Scope

This article covers the actionable core of RFC 3464 delivery status notifications from the consuming side: the per-recipient field set, how Action and Status combine into a retry decision, what Diagnostic-Code contributes, and how the structure maps onto suppression logic. It applies to any system processing bounces at scale - senders, ESPs, list managers. It does not cover DSN generation obligations, MDN read receipts, internationalized DSN encoding, or the SMTP-level negotiation requesting DSNs.

## Workflow or implementation guidance

Bounce processing runs as a five-field extraction with a decision rule on top.

**1. Locate the structure.** A DSN arrives as a multipart/report message with report-type delivery-status. The `message/delivery-status` part contains a per-message field group (Reporting-MTA, Arrival-Date, optionally original envelope identifiers) followed by one or more per-recipient groups. Each per-recipient group is an independent verdict - a multi-recipient message can fail for one recipient and succeed for another, so parse all groups, never just the first.

**2. Read Action first.** Action is the disposition: `failed` (permanent), `delayed` (temporary, will be retried), `delivered` (success), `relayed` (passed to another administrative domain), and `expanded` (delivery to a mailing-list expander). The retry question is answered here before any code is examined: `delayed` means keep waiting; `failed` means stop; `delivered` and `relayed` are positive. Treat `delayed` as soft evidence - senders should not suppress on it.

**3. Read Status for the transport-independent code.** Status carries the three-numeric form class.subject.detail: class 4 temporary, 5 permanent, 2 success. Subject and detail refine the cause - 5.1.1 mailbox not found, 5.7.x security or policy refusals, 4.2.x busy timeouts. Cross-check against Action: a `failed` action with a 4-class status is contradictory and should be treated conservatively as temporary, since generating MTAs occasionally mislabel.

**4. Read Diagnostic-Code for the MTA's own words.** This field carries the transport-specific evidence - typically `smtp; 550 5.1.1 user unknown` or a provider's expanded text. It corroborates and refines, never replaces, the structured fields: providers embed proprietary codes and policy explanations here with no Status equivalent. Parse the embedded enhanced status code when present and harvest text for known provider patterns, but never let a regex over free text override a clean Action/Status pair.

**5. Apply the retry arithmetic.** Will-Retry-Until bounds how long a `delayed` recipient's sender keeps trying; Last-Attempt-Date timestamps the latest attempt; Remote-MTA identifies which host issued the verdict, which matters when a smarthost chain puts your own relay's name in Reporting-MTA and the truth is further in. Feed Action plus Status into the suppression policy: 5.x.x under `failed` suppresses, 4.x.x under `delayed` schedules, and anything unusual routes to manual review rather than a default bucket.

## Controls

- Parser requirement: per-recipient group enumeration with independent verdicts, verified against multi-recipient test DSNs.
- Precedence rule codified: Action and Status decide; Diagnostic-Code refines; free text never overrides.
- Contradiction handling: 4-class Status under `failed` action quarantined for review, not suppressed.
- Suppression policy table mapping (Action, Status class, provider diagnostic patterns) to outcomes, every entry dated and owned.
- Remote-MTA attribution check distinguishing your own relay's verdicts from downstream MTAs before suppressing.
- Rate-of-change alarm on classification mix: a sudden shift usually means a pipeline or provider change, not a real list event.
- Retention of raw DSNs behind the parsed store for dispute and audit windows.
- Per-recipient envelope encoding so the target is recoverable when providers omit Original-Recipient, which many do.

## Validation evidence

- A corpus of representative DSNs from major providers parsed with field-level assertions against hand-labeled ground truth.
- A multi-recipient test DSN with mixed verdicts producing independent per-recipient classifications.
- A contradiction fixture - `failed` plus 4.x.x - routed to review, not suppression.
- A round-trip test through the real pipeline using a provider that returns DSNs, confirming end-to-end mapping to suppression rows.
- An attribution test: a DSN generated by your own smarthost for a downstream failure classified by Remote-MTA, not suppressed against your infrastructure.
- Quarterly sample audit of suppressions traced back to their originating DSN fields.

## Failure modes and correction

Hard-suppressing addresses that later prove deliverable is the costly error, usually tracing to text-scraping over structured fields - a provider's colorful prose said "blocked" while Status said 4.x.x. Enforce the precedence rule and re-audit recent suppressions after any provider wording change. Bounces classified temporary forever indicate missing retry-limit accounting: pair `delayed` handling with an attempt ceiling and an eventual-decision rule. Missing recipient attribution means Original-Recipient was absent and the pipeline lacked envelope encoding; adopt per-recipient encoding at send time. `expanded` actions treated as failures silently destroy memberships that are merely alias expansions; classify them as delivered-equivalent for list purposes. A flood of one Status code after adding a relay to the chain is attribution drift, not list decay; fix the Remote-MTA logic. Providers whose DSNs are malformed at the MIME layer land in the unparseable bucket; keep that bucket visible and re-parse on parser updates rather than discarding. Over-aggressive suppression on 5.7.x policy blocks - blocklists, rate controls - poisons domains recoverable in hours; carve those into a timed-retry class by diagnostic pattern.

## Limitations

DSN fields are only as honest as the generating MTA, and both mislabeling and omission occur in the wild - diagnostic text is unregulated and enhanced codes advisory to generators. Many providers send reduced bounces or none, so bounce data undercounts true failure. The format predates modern provider policy complexity, so much of what matters operationally lives in Diagnostic-Code free text, where coverage is provider-specific and unstable. Original-Recipient is frequently absent, pushing recipient recovery onto envelope techniques the DSN does not provide. Success reporting is opt-in at submission and rare, so positive delivery confirmation cannot be relied on. Fields describe the last hop's verdict; behind relayed hops the truth may be further removed than the document admits.

## Canonical sources

- [RFC 3464: An Extensible Message Format for Delivery Status Notifications](https://www.rfc-editor.org/rfc/rfc3464.html)
- [RFC 5321: Simple Mail Transfer Protocol (enhanced status codes, null reverse-path)](https://www.rfc-editor.org/rfc/rfc5321.html)
- [RFC 3464 (IETF Datatracker record)](https://datatracker.ietf.org/doc/rfc3464.html)
- [M3AAWG best practices and published documents (bounce and list hygiene)](https://www.m3aawg.org/published-documents/)
- [RFC 3461: SMTP Service Extension for Delivery Status Notifications](https://www.rfc-editor.org/rfc/rfc3461.html)
