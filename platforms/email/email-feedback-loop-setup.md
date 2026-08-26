# email-feedback-loop-setup

**Issue:** When a recipient clicks "report spam", mailbox providers can tell the sender — but only if the sender has registered a Feedback Loop (FBL) with each provider and built a pipeline to ingest the resulting ARF (Abuse Reporting Format, RFC 5965) reports. Without this, a self-hosted or ESP-adjacent sender discovers complaint problems only after reputation collapses, because complaint signals arrive as machine-parseable email at an unmonitored mailbox (or not at all without registration) instead of flowing into the suppression list. The 2025-2026 landscape is fragmented: Yahoo/AOL offer a unified hashed-recipient FBL, Microsoft routes complaints through SNDS/JMRP with a non-standard format, and Gmail offers no traditional FBL at all, only a Postmaster Tools spam-rate metric.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## FBL landscape (2025-2026)

1. **Yahoo/AOL (Yahoo Sender Hub).** One registration covers Yahoo and AOL; reports arrive as standard ARF with the recipient address replaced by an unsalted hash per reporting address, so you must hash your own recipients with the same algorithm to identify complainers.
2. **Microsoft (SNDS + JMRP).** Complaint data comes through Smart Network Data Services (per-IP complaint metrics) and the Junk Mail Reporting Program (forwarded complaint messages). Historically JMRP used its own XML-ish forwarded-message format rather than clean ARF; parsers must handle both shapes.
3. **Gmail: no FBL exists.** Google's equivalent is the spam-rate dashboard in Postmaster Tools v2 — domain-level, no per-recipient identities. Threshold to police: keep spam complaints below 0.1% (0.3% is the hard ceiling per Gmail/Yahoo 2024+ bulk sender rules).
4. **Other providers.** Comcast, Spectrum/Time Warner, and some European providers still run classic ARF FBLs (M3AAWG maintains the current list); register for any provider exceeding ~1% of your list volume.
5. **ESP-hosted FBLs.** If sending through SendGrid/Mailgun/Postmark, their complaint webhooks (e.g., Spam Report events) are the FBL already processed — do not double-register provider FBLs unless you control your own infrastructure, or you will suppress twice.

## Registration prerequisites

1. **Working `postmaster@` and `abuse@` mailboxes on every sending domain.** Most FBL programs (and Gmail/Yahoo bulk requirements) require these role mailboxes to exist and accept mail before registration is approved.
2. **SPF + DKIM + DMARC on the registration domain.** Providers verify you actually control the domain reporting on behalf of; mismatched DKIM selectors between registration and production sends break report matching.
3. **A dedicated inbound mailbox or endpoint for reports.** Register a specific address (e.g., `fbl@sender.example`) able to receive the report volume — high-volume senders get thousands of ARF messages per day, which do not belong in a human's inbox.
4. **Verify per-provider requirements before applying.** Yahoo requires listing the sending domains/IPs; Microsoft SNDS requires IP ownership (reverse DNS matching helps auto-approval); each program re-verifies periodically, so keep the registration metadata in your infrastructure-as-code inventory.

## ARF report structure and parsing

1. **Reports are multipart MIME with three parts.** Per RFC 5965: (1) a human-readable `text/plain` explanation, (2) a `message/feedback-report` part with machine fields (`Feedback-Type: abuse`, `User-Agent`, `Arrival-Date`, `Reporting-MTA`), and (3) the original message headers (and optionally body) in `message/rfc822` or `text/rfc822-headers`. Parse fields from part 2, identities from part 3.
2. **Extract identity from DKIM headers, not From.** The `Authentication-Results` and original `DKIM-Signature` `d=`/`d` domain identify which of your sending domains was reported; the `From` may be a display alias. Match on DKIM domain + original recipient address (or its hash).
3. **Handle Yahoo's hashed recipients.** Yahoo ARF reports replace the recipient with a per-report-address hash. Store a hash-map of every sent message (hash computed with Yahoo's published algorithm keyed to your reporting address) so reports resolve back to list members.
4. **Microsoft's non-standard reports.** JMRP forwards arrive as Outlook-era forwarded messages or XML rather than clean `message/feedback-report`; keep a separate parser branch and fall back to regexing the original To: header.
5. **De-duplicate by feedback-type + message-id + recipient.** `Feedback-Type: abuse` is the spam complaint; `fraud`/`virus`/`miscategorized` types exist — route each differently, and collapse duplicate reports of the same campaign so one recipient's repeated reports do not count as multiple complainers.

## Processing pipeline

1. **Suppress immediately on `abuse`.** Any recipient whose report resolved (directly or via hash) goes onto the suppression list with reason `complaint` — permanent, non-re-addable. Re-emailing a complainer is the fastest route to escalation with the provider.
2. **Attribute complaints per campaign and per sending domain.** Parse the original headers for your campaign identifiers (List-Unsubscribe, custom X-headers) so complaint rate is computable per campaign: rate = complaints / delivered, not complaints / total list.
3. **Alert on rate thresholds.** Page/email ops when campaign complaint rate crosses 0.1% (warning) and 0.3% (pause-the-send critical, aligned with Google/Yahoo enforcement ceilings). Overall domain spam rate in Google Postmaster is the cross-check.
4. **Feed complaints back into segmentation.** Complaint-heavy campaign types and affiliate/user-generated content flows deserve targeted review before the next send; a spike localized to one campaign type usually means content or targeting, not infrastructure.
5. **Retain reports for audit.** Keep raw ARF (with PII handling per GDPR — complaint data is processing evidence, lawful basis: legitimate interest for deliverability protection) so you can prove suppression provenance to providers during a remediation conversation.

## Gotchas

1. **FBL registration is per provider, not global.** Approval takes days to weeks; do it during IP/domain warming, not after reputation drops, because most programs restrict or close enrollment for domains with active poor reputation.
2. **Complaints under-report reality.** Only a fraction of spam-clicking users is reported (estimates: 1 report per dozens of annoyed recipients), and Gmail — often 30-50% of a consumer list — contributes zero per-recipient signal; treat FBL volume as a lower bound and monitor Postmaster spam rate in parallel.
3. **Hashed reports without a hash-map are useless.** If you cannot resolve Yahoo hashes, you cannot suppress the complainer — build the sent-mail hash index before the first send, not after the first report.
4. **ARF mail itself is attackable input.** Reports embed attacker-influenced original headers; parse with a hardened MIME parser (no header injection into your own systems, size limits, content-type restrictions) or a crash-loop in the parser becomes a denial-of-service on your suppression pipeline.
5. **FBL ≠ unsubscribe requests.** Some programs occasionally deliver `miscategorized` or unsubscribe-intent feedback; only auto-suppress on `Feedback-Type: abuse` and route ambiguous types to review.
