# Support First Contact Resolution Definition Integrity

First contact resolution (FCR) is one of the most quoted and most quietly redefined support metrics. Because it is easy to move the number by moving the definition, the definition itself must be governed: the reopen window, the channel scope, the counting unit, and the exclusion list must be fixed in writing before any FCR figure is published. This article defines that governance and the defenses against gaming.

## Scope

This article covers the definition, measurement, and integrity controls for FCR (and its sibling, one-touch resolution) at a multi-channel support desk. It governs how the desk decides which contacts count as resolved on first contact, how reopens and follow-ups void a count, how channels are included, and how the definition is changed.

It does not cover the operational improvement of FCR (coaching, tooling, empowerment matrices), customer satisfaction measurement, or SLA credit calculations. It assumes the ticketing system records contact timestamps, agent touch history, and reopen events with stable semantics.

## Workflow or implementation guidance

Fix the definition in five decisions, each recorded in a definition document under change control:

1. Counting unit. FCR is measured per issue, not per ticket and not per message. A merged ticket counts once; a customer writing twice about the same issue before any response is one contact, not two. The issue key is the join across touches, and the desk states how it derives that key (ticket identifier plus issue tag).
2. The contact that starts the clock. Only inbound-initiated contacts are eligible. Outbound proactive contacts and agent-initiated follow-ups are excluded from the denominator because they are not tests of first-contact capability.
3. Reopen window. A resolved contact qualifies only if the same issue does not return within a fixed window counted from the resolution timestamp, in business or calendar hours as stated. Common choices are 24 to 72 hours for synchronous channels and 5 to 7 days for email and portal. The window is chosen from observed reopen-latency distributions, not negotiated after seeing results.
4. Channel scope. The desk declares which channels are in scope (phone, chat, email, portal, social, assistant) and computes FCR per channel, then a stated aggregate. Channel-silently-excluded FCR is prohibited: any exclusion (for example, a new channel with unstable tagging) is noted on the same report with its volume share.
5. Voiding conditions. A count is voided by: a reopen on the same issue key within the window; a second touch by any agent on the same issue before resolution (except documented handoffs defined as within-first-contact by policy); a customer reply indicating the problem persists; or a same-issue contact through another channel within the window (cross-channel recurrence).

With the definition fixed, measurement is mechanical: extract contacts with resolution timestamps, join to the issue key's subsequent events through the window, apply voiding conditions, and report eligible contacts, resolved-on-first, voided-by-reopen, voided-by-cross-channel, and the FCR ratio. Every published FCR number carries its definition version, so a definition change is visible rather than silent.

Definition changes follow a governed path: a written proposal stating the old and new definition, the measured effect on the historical series, approval by the support operations owner, and a restatement of at least one prior period under both definitions so trend readers can see the discontinuity.

## Controls

- Definition versioning: each published FCR figure is tagged with the definition version; reports mixing versions are rejected.
- Denominator disclosure: every report shows the eligible contact count and the share excluded by scope decisions, so a rising ratio cannot be manufactured by narrowing scope.
- Reopen-latency monitoring: the desk periodically plots reopen latency; if a material share of reopens arrives just after the window boundary, the window is revisited rather than celebrated as validated.
- Void-reason audit: a monthly sample of counted-as-FCR contacts is read end to end to confirm no disguised reopen (a new ticket for the same issue, a "thanks, but" reply treated as closure) inflated the count.
- Anti-pressure rule: FCR never appears as an individual agent performance target without its voiding conditions computed automatically; manual marking of "resolved" by the resolving agent alone cannot create an FCR count.

## Validation evidence

Evidence includes: the definition document with version history and change approvals; reopen-latency distribution charts supporting the chosen window; per-period extraction showing eligible, resolved-first, and voided counts with void reasons; the cross-channel recurrence rate; and the monthly end-to-end sample audit with verdicts. A strong integrity signal is a back-test: recompute the last quarter under a one-step-stricter definition and publish both numbers side by side, demonstrating the desk tolerates a lower, more honest figure.

## Failure modes and correction

Silent redefinition is the canonical failure: the window shortens, a channel drops out, or a "resolution" becomes whatever the agent marked, and the number improves while service does not. Correction: definition versioning, denominator disclosure, and the change-control path with dual-period restatement.

Reopen suppression is second: reopens are handled as new tickets or absorbed into merged cases so they never void an FCR count. Correction: the issue-key derivation must survive ticket creation (customer and topic match within the window), and the void-reason audit specifically looks for same-issue new tickets.

Premature resolution marking is third: the agent closes at first response, the customer replies within the window, and the system treats the reply as a new thread. Correction: threading rules that attach in-window customer replies to the original issue key, and voiding on persistence-indicating replies.

Over-aggregation is fourth: a healthy chat FCR averages away a broken email FCR. Correction: per-channel reporting as the primary view, aggregate as derived.

## Limitations

FCR is undefined for genuinely multi-session work (complex diagnostics, staged migrations); the desk should scope these out explicitly rather than force-fit them, and state the excluded volume. Cross-channel recurrence detection depends on customer identification and tagging quality and undercounts for anonymous contacts. The reopen window is a proxy: some issues recur later than any affordable window, so FCR is an estimate with a stated horizon, not a truth. Benchmark comparisons across companies are unreliable because definitions differ; the desk should benchmark against its own history.

## Canonical sources

- NIST SP 800-53 Rev. 5, System and Services Acquisition control family, https://csrc.nist.gov/pubs/sp/800/53/r5/upd1/final
- NIST SP 800-137, Information Security Continuous Monitoring (ISCM) for Federal Information Systems and Organizations, https://csrc.nist.gov/pubs/sp/800/137/final
- IETF RFC 2119, Key words for use in RFCs to Indicate Requirement Levels, https://www.rfc-editor.org/rfc/rfc2119.html
