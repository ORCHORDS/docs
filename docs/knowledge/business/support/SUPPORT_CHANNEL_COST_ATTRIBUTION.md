# Support Channel Cost Attribution

Knowing what a contact costs per channel is prerequisite knowledge for every channel strategy decision: what to automate, where to push self-service, whether chat is really cheaper than email, and what a phone-only customer segment actually costs to serve. The number is easy to get wrong, because most support costs are shared, and attribution choices silently decide the answer before the arithmetic begins. This article defines a disciplined method and the distortions to avoid.

## Scope

This article covers the attribution of cost to individual contacts across support channels: which cost pools are included, how shared costs are allocated, how the cost-per-contact figure is computed and conditioned, and which uses of the figure are legitimate. It applies to phone, chat, email, portal tickets, social, and assistant-handled contacts.

It does not cover pricing, product cost of goods, customer lifetime-value modeling, or the decision of which channels to offer (which consumes this article's output). It assumes a chart of accounts and workforce data at usable granularity; where financial data is coarse, the limitations section governs.

## Workflow or implementation guidance

Build the attribution in six steps:

1. Define the contact unit per channel. A contact is one customer-initiated issue episode, not one message, not one call attempt, and not one ticket touch. An email thread of six messages is one contact; a call with a callback is one contact. Without a consistent unit, cross-channel comparison is meaningless, so the episode definition (same customer, same issue, within a defined window) is written down and applied identically to every channel.
2. Inventory cost pools. Three tiers: direct (channel platform licenses, telephony carriage, telephony numbers, chat platform, per-contact vendor fees), semi-direct (agents' compensation for time logged to the channel, channel-specific QA and training), and shared/indirect (desk management, knowledge management, workforce management, facilities, IT support, HR overhead, tooling used across channels).
3. Choose and justify allocation keys for shared pools. The default keys are usage-based and must be stated: agent-logged hours per channel for management and training; contact volume for per-contact vendor items; headcount for facilities and HR. Arbitrary keys (equal split across channels) are prohibited; where no usage basis exists, the pool is reported separately as unallocated overhead rather than forced into per-contact figures.
4. Measure the denominator. Count contacts per channel by episode definition, excluding internal test contacts and non-customer contacts, and reconcile the count against the systems of record.
5. Compute and condition. Cost per contact equals allocated cost divided by contact count, computed per channel per period. Crucially, also compute conditioned variants: cost per resolved contact (excluding contacts that ended without resolution), cost per segment (customer tier, issue type), and the channel mix over time, because a raw blended figure hides mix shifts that masquerade as efficiency gains.
6. Publish with lineage. The published figure carries its basis: period, cost pools included, allocation keys, contact unit definition, and the unallocated remainder. Figures published without lineage are withdrawn.

Interpretation rules matter as much as arithmetic. Channels differ in contact quality: a phone contact often carries issues self-service could not resolve, so its higher cost reflects harder work, not waste. Assisted-to-resolution cost (total attributed cost divided by resolved episodes) is the more honest comparator when channels serve different difficulty mixes.

## Controls

- Fixed contact-unit definition: the episode rule is versioned; any change restates prior periods or the series breaks.
- Allocation-key register: every shared pool's key is documented with rationale and review date; a key change requires finance and operations sign-off and triggers restatement of comparative figures.
- Unallocated remainder disclosure: the share of total desk cost not attributed to any contact is reported alongside per-contact figures, so improvements cannot be manufactured by narrowing the pool.
- Denominator reconciliation: contact counts are tied to the systems of record each period with variance thresholds; large variances freeze publication.
- Anti-misuse rule: cost-per-contact figures may not be used as agent or team performance targets, because that pressure shifts contacts between categories to game attribution.

## Validation evidence

Evidence for an attribution run: the cost-pool inventory mapped to the chart of accounts for the period; the allocation-key register in force; contact-count reconciliation with variance; computed per-channel figures with their conditioned variants; the unallocated remainder percentage over time; and a sensitivity note showing how each figure moves under the next-most-reasonable allocation key, which tells decision-makers how much of the apparent channel difference is method rather than reality. An annual review recomputes one quarter end to end from raw financials as a reproduction check.

## Failure modes and correction

Equal-split allocation is the standard distortion: shared overhead is divided by channel count, the small channels look absurdly cheap, and investment flows to them for fictional reasons. Correction: usage-based keys with the register, and the unallocated remainder for pools without a defensible basis.

Contact-unit inconsistency is second: chat counts sessions, email counts messages, and the comparison is nonsense. Correction: the single episode definition enforced in reporting code, not left to each channel team.

Mix-shift blindness is third: blended cost falls because easy contacts moved to self-service, and the remaining expensive contacts are labeled inefficiency. Correction: conditioned variants by issue type and segment, and cost-per-resolved-contact as the primary comparator.

Denominator gaming is fourth: contacts are reclassified to lower-cost categories, or non-resolved contacts dropped from counts, to flatter the ratio. Correction: denominator reconciliation and the anti-misuse rule.

Hidden subsidy is fifth: one channel's cost sits in another's pool (chat platform licensed under an IT bundle booked to email) and distorts both. Correction: the annual pool inventory that traces licenses and fees to their actual consuming channels.

## Limitations

Attribution precision is bounded by financial data granularity; over-precise decimals imply knowledge the ledger does not contain. Channel costs interact: deflecting easy contacts raises the average cost of the remaining ones, so figures must be re-derived after mix changes rather than extrapolated. Some strategic costs (building a knowledge base that benefits all channels) resist attribution and belong in the unallocated remainder. Cross-subsidy between customer segments is visible only if segment conditioning is computed. Finally, cost attribution measures input economics only; it says nothing about customer outcome or accessibility value, and decisions based on cost alone will optimize toward channels some customers cannot use.

## Canonical sources

- NIST SP 800-53 Rev. 5, System and Services Acquisition control family, https://csrc.nist.gov/pubs/sp/800/53/r5/upd1/final
- W3C, Web Content Accessibility Guidelines (WCAG) 2.2, https://www.w3.org/TR/WCAG22/
- IETF RFC 2119, Key words for use in RFCs to Indicate Requirement Levels, https://www.rfc-editor.org/rfc/rfc2119.html
