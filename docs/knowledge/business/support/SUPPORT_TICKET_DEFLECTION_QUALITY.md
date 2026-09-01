# Support Ticket Deflection Quality Measurement

Measuring ticket deflection without rewarding containment harm or dead-end self-service. Deflection is a cost outcome, not a service outcome; treating it as a target in isolation invites the desk to hide the contact channel, starve hard customers of human help, or declare success when a customer gave up rather than succeeded. This article defines a deflection measure that pairs every unit of avoided contact with a completion signal, so the desk learns whether self-service actually resolved the underlying need.

## Scope

This article covers the measurement and governance of self-service deflection for a customer support desk: how a deflected contact is counted, how the count is paired with a completion or outcome signal, and how the desk guards against the two canonical distortions (rewarding containment harm and rewarding dead ends). It applies to help-center articles, search results, contact-prevention interstitials, chatbots and assistants, community answers, and account-portal task flows that substitute for a ticket.

It does not cover channel-mix strategy, the decision to offer or withdraw a human channel, marketing claims about self-service rates, or the design of individual knowledge articles (covered by knowledge-centered service articles in this folder). It assumes the desk can observe, at least in aggregate, both the self-service session and the subsequent contact stream for the same customer and topic.

## Workflow or implementation guidance

Define the defensible unit first: a deflection candidate is a self-service session in which the customer reached a step that could plausibly end the need (article read to depth, task flow completed, assistant conversation closed with a resolution offer), followed by an observation window in which no contact on the same topic arrives from the same customer. A common observation window is 72 hours for low-complexity topics and seven days for complex or billing-adjacent ones; the window must be long enough that a genuine failure would surface as a contact.

Run measurement in five steps:

1. Segment deflection candidates by topic and by entry point (search, article link, assistant, portal task), because aggregate rates hide the dead ends.
2. For each candidate, record the terminal event: completed task, article read to depth, assistant ended without resolution offer, session abandoned mid-flow. Only the first two are countable without further evidence; the third and fourth are inconclusive, not successes.
3. Join the candidate to the contact stream by customer identifier and topic tag across the observation window. A same-topic contact within the window reclassifies the candidate as a failed deflection attempt regardless of what the session telemetry said.
4. Compute, per topic and entry point, the assisted-completion rate (candidates that ended the need) and the recurrence rate (candidates that converted to contact). Report deflection only as the product of the candidate volume and the assisted-completion rate, never as raw candidate volume.
5. Publish the paired figures together on one page: deflection volume, assisted-completion rate, recurrence rate, and the volume of inconclusive sessions. Any report that shows deflection without its pair is returned for rework.

Treat "contact prevented" as the leading indicator and "need resolved" as the confirmatory one. Where the join key is weak (anonymous sessions, shared accounts), mark the segment as low-confidence and exclude it from headline numbers rather than guessing.

## Controls

Four controls keep the measure honest:

- Pairing rule: no deflection number is reported without its assisted-completion and recurrence counterpart for the same slice and period. This is enforced in the reporting layer, not left to analyst discretion.
- Channel-access invariant: deflection initiatives may not be scored until it is confirmed that the human contact path remains discoverable within the same journey (for example, the contact link is still present in the help center and reachable from the article that deflected the session).
- Inconclusive-bucket accounting: abandoned mid-flow sessions and assistant conversations that ended without a resolution offer are counted and reported separately, and a rise in this bucket triggers a content or flow review even when headline deflection looks healthy.
- Topical false-victory review: each period, a sample of high-deflection topics is manually traced end to end (article read, no contact) to confirm the topic genuinely ended the need rather than the customer surrendering. The sample report names the topics, the tracer, and the verdict per topic.

A further control prohibits individual-level targets: no agent, team, or bot-tuning objective may be paid or evaluated on deflection volume alone, because that pressure reliably produces link-hiding and answer-withholding.

## Validation evidence

Evidence that the measure is trustworthy includes: the join coverage (share of deflection candidates successfully joined to the contact stream), which must be reported alongside every figure; a reconciliation showing that same-topic contacts inside the observation window were reclassified as failures; the manual trace sample with per-topic verdicts; and a periodic falsification test in which a known-friction topic is deliberately left unfixed and the measure is expected to show its recurrence. A measure that never shows failure is audited for broken joins before it is believed.

## Failure modes and correction

Containment harm: contact options are buried, the chatbot loops, or article pages omit the path to a human, so raw deflection rises while customer harm rises. The correction is the channel-access invariant plus monitoring of escalation-toned contacts and complaint volume on deflected topics; a deflection win that coincides with a complaint spike is reversed, not celebrated.

Dead-end self-service: the customer reads the article, cannot act on it, and gives up without contacting. The correction is the inconclusive-bucket accounting and the manual trace sample; dead ends cluster on stale, wrong-version, or prerequisite-heavy articles and are fixed by content work, not by more deflection pressure.

Window gaming: choosing an observation window too short to catch recurrence, or resetting the topic tag to break the join. The correction is a fixed window per topic class under change control, and a periodic re-run of a longer window on a sample to detect late recurrence the standard window missed.

## Limitations

The measure depends on topic tagging quality; mistagged contacts escape the join and inflate success. Anonymous and cross-device sessions weaken the customer join and must be handled as low-confidence segments. Some needs genuinely end without observable confirmation, so the assisted-completion rate is a conservative floor rather than the truth. The observation-window approach cannot see customers who resolve elsewhere (community, social, chargeback) and count as deflected when they were merely lost to sight.

## Canonical sources

- NIST SP 800-53 Rev. 5, System and Services Acquisition control family, https://csrc.nist.gov/pubs/sp/800/53/r5/upd1/final
- NIST SP 800-137, Information Security Continuous Monitoring (ISCM) for Federal Information Systems and Organizations, https://csrc.nist.gov/pubs/sp/800/137/final
- W3C, Web Content Accessibility Guidelines (WCAG) 2.2, https://www.w3.org/TR/WCAG22/
