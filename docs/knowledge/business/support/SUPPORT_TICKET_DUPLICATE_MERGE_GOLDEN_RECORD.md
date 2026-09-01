# Support Ticket Duplicate Merge Golden Record

## Scope

This article governs how the support desk merges duplicate tickets into a single golden record and how the merged record continues to satisfy the original case requirements. The article applies to every ticket that the support desk suspects duplicates an existing ticket: same customer, same product, same incident timeframe, or same underlying issue. It does not cover the detection step (which is a separate discipline) and does not cover the case of related but distinct tickets that should remain separate.

The discipline follows the incident handling practice in ITIL 4, where a single underlying incident is recorded once and any subsequent reports are linked rather than re-recorded. The golden record carries the authoritative state of the case, and the linked tickets carry the customer-side trail of how the issue was reported. The customer never sees the merge; from the customer's perspective, the issue has a single ticket that is being handled.

## Workflow or implementation guidance

The merge workflow begins with the identification of candidate duplicates. Detection may come from automated signals (the customer identifier matches, the keywords overlap, the timing aligns) or from an agent's observation (the customer contacts the desk about an existing open case). The candidate set is presented to the agent as a list of open tickets for the customer, with a similarity score and a brief excerpt of each.

The agent reviews the candidate set against the proposed merge target. The agent's review confirms that the tickets describe the same underlying issue, that the customer's identity is consistent across the tickets, that the channel is not a barrier (a customer who calls and then emails about the same issue is a single customer, not two), and that the timing is consistent with the issue being the same. If the review confirms the merge, the agent proceeds; if not, the agent rejects the merge and adds a comment that explains why the tickets are distinct.

The merge itself produces a golden record. The golden record is the ticket that the agent selects as the authoritative one; the other tickets are linked as duplicates. The golden record inherits the customer's most recent contact time, the most recent description, the most recent tag set, and the highest priority among the merged tickets. The other tickets retain their original identifier, their original channel, and their original contact timestamps, but their state changes to "merged" and their content is read-only from the perspective of the public reply.

The merge is reversible. If a later signal shows that the merged tickets describe distinct issues (the customer opens a second case about a different aspect of the product, or a colleague unmerges them as part of a dispute), the merge is undone, the golden record is preserved, and the linked tickets are returned to their own state. The unmerge action is logged with the actor, the reason, and the timestamp.

## Controls

Three controls protect the merge from error. The first is a confirmation step in the agent workflow: the merge action is staged, and the agent must confirm the merge target and the duplicate set before the merge is committed. The second is a periodic audit that compares the merge rate against the unmerge rate; a high unmerge rate is a signal that the detection step is too aggressive or that the agent review is too cursory. The third is a customer-side visibility rule: when the customer views the case, they see a single case with a single history, not a list of merged tickets.

A separate control protects against the merge of tickets that describe protected-category content. The detection step's similarity score does not consider protected-category text; if the merging logic were to favour a ticket because it contained such text, the merge could propagate a sensitive context into a less-protected record. The merge is performed on a ticket-level basis, not a text-similarity basis, so the protected content is not the deciding factor.

## Validation evidence

Validation evidence is collected continuously. The merge and unmerge actions are logged with the actor, the reason, and the affected tickets. The periodic audit reports the merge rate, the unmerge rate, and the median time between merge and unmerge. A small sample of recent merges is reviewed manually to confirm that the golden record is fit for purpose.

## Failure modes and correction

The most common failure is the merge of tickets that should have remained distinct. Two customers with the same name, or one customer with two unrelated issues at the same time, are merged because the detection signal is too coarse. The correction is the agent review step and the unmerge workflow. A high unmerge rate triggers a review of the detection model.

The second most common failure is the merge of tickets across customer identities. A customer who recently changed their identifier, or two customers in the same household, are merged because the identifying signal is misleading. The correction is the customer identity check in the agent review step.

The third most common failure is the loss of customer context in the merge. The golden record inherits the most recent description, but the earlier description may have carried information that the customer expected to be retained. The correction is to retain the linked tickets as read-only and to expose their content in the case history view.

## Limitations

The merge discipline assumes that the case-management tool can express the link between the golden record and the merged tickets. Where the tool only supports a single ticket per issue, the discipline degrades; the agent must choose which ticket survives, and the other is closed. The organisation should confirm that its tool supports the link representation before it commits to the discipline.

The discipline also assumes that the customer is identified. Where the customer is anonymous (for example, an inbound chat from a non-logged-in session), the merge is constrained to the channel-level session, and the cross-channel merge requires additional identification.

## Canonical sources

- AXELOS, ITIL 4 Incident Management Practice (publisher and title only; AXELOS publications are referenced via https://www.axelos.com/resource-hub/case-studies/itil-4-foundation).
- NIST SP 800-53 Rev. 5, System and Services Acquisition control family, https://csrc.nist.gov/pubs/sp/800/53/r5/upd1/final
- ENISA, Risk Management Resources, https://www.enisa.europa.eu/topics/risk-management
- W3C, Technical Report publication conventions, https://www.w3.org/TR/