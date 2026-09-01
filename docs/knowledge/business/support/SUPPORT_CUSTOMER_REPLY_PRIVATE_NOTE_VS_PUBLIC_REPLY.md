# Support Customer Reply Private Note Vs Public Reply

## Scope

This article governs the decision of whether a customer-facing message from the support desk goes into the public reply thread of the case or into a private note attached to the case. The decision matters for two reasons. First, a public reply becomes part of the customer-visible history of the case and may be referenced in later communications, audits, or disputes. Second, a private note is internal context that is not visible to the customer and is governed by a different access regime. The discipline applies to every channel that produces a customer-facing response: email, chat, in-product messaging, social reply, and ticket comments.

The principle behind the split follows the data minimisation discipline found in GDPR Article 5 and in analogous privacy frameworks. The principle is that information not needed for the customer's understanding should not be exposed to the customer; conversely, information the customer needs to act on should be in the public reply, not buried in an internal note.

## Workflow or implementation guidance

The decision rule is straightforward: anything the customer needs to read in order to resolve their case belongs in the public reply. Anything the agent needs to record for their own continuity, for a colleague who picks up the case, or for an audit belongs in the private note. The rule is not a style preference; it is a routing rule enforced at the tool layer.

The agent is given two input areas: a public reply box and a private note box. The boxes are visually distinct, and the agent's case-management tool highlights which field is which before send. The public reply is sent to the customer through the channel; the private note is persisted with the case for the agent population that has access to the case. The two are not merged at send time; the public reply never carries internal context, and the private note never carries content the customer should see.

When in doubt, the agent applies a three-question test: does the customer need this to act, do other agents need this to continue the case, and does the organisation need this for audit. If only the third question is yes, the content belongs in the private note. If the first question is yes, the content belongs in the public reply. If the second and third are yes but the first is no, the content is private. The test is documented in the agent training material and reinforced in the case-management tool with a tooltip.

There are content classes that almost always belong in the private note. These include: sentiment observations (the customer is angry), inferred motivation (the customer is likely to churn), agent speculation (the customer may have misconfigured the device), agent-only shorthand (case codes, internal references, follow-up flags), and any content that references a third party by name. The private note is also the right home for any content the customer asked the agent not to put in the reply.

## Controls

The controls are designed to prevent the two most common errors: leaking internal context into the public reply and burying customer-relevant information in a private note. At the tool layer, the case-management application offers a linter that scans the public reply for a small set of internal-marker patterns (for example, an internal reference number, an agent shorthand, a sentiment adjective). The linter warns the agent and offers to move the content to the private note. At the storage layer, the private note is keyed to a separate access role list from the public reply; the private note is not exportable through the customer-facing export path. At the audit layer, a periodic sampling review confirms that a random set of recent cases had the right content in each field.

A separate control prevents the agent from using the private note as a dumping ground. A private note that is excessively long is a signal that the agent is writing for themselves, not for the case. The sampling review reports the average and 95th-percentile private-note length; a length that exceeds the policy threshold triggers a coaching intervention.

## Validation evidence

Validation evidence is collected continuously. The linter produces a log of warnings and the agent's response; the log is reviewed by the team lead. The sampling review produces a per-agent and per-channel picture of how the two fields are used. A periodic tabletop exercise tests the customer-facing export path: when a customer requests their case history, the public reply history is exported, and the private note is excluded. The exercise confirms the access regime is correctly enforced.

## Failure modes and correction

The most common failure is the agent pasting internal context into the public reply because it is faster than rephrasing. The correction is the linter warning plus targeted training; the agent is reminded that the public reply is permanent.

The second most common failure is the agent hiding customer-relevant information in the private note because they are unsure whether the customer should see it. The correction is the three-question test and a culture of clarity: when in doubt, the information goes in the public reply with a brief acknowledgement that the situation is being investigated.

The third most common failure is the private note leaking into downstream systems through an export that is not role-scoped. The correction is the storage-layer separation and the periodic audit of exports.

## Limitations

The two-field model assumes that the agent is disciplined and that the case-management tool provides the affordances. Where the tool does not provide two distinct fields, the discipline degrades; the agent will conflate the two and the audit will fail. The organisation should confirm that its tool supports the two-field model before it commits to the discipline.

The model also assumes that the customer and the agent share a common language for the public reply. Where the customer writes in a language the agent does not write natively, the public reply is a translation, and the three-question test must be applied to the translated text rather than the source-language draft.

## Canonical sources

- GDPR Article 5, Principles relating to processing of personal data, https://gdpr-info.eu/art-5-gdpr/
- NIST SP 800-53 Rev. 5, Access Control control family, https://csrc.nist.gov/pubs/sp/800/53/r5/upd1/final
- ENISA, Risk Management Resources, https://www.enisa.europa.eu/topics/risk-management
- W3C, Privacy Interest Group guidance on data minimisation (publisher and title only; canonical W3C landing https://www.w3.org/mission/privacy/).