# Support Inbound Social Media Triage Handover

## Scope

This article governs how the support desk triages inbound social media contacts and hands them over to the appropriate handling queue. The scope covers every social channel that produces a customer-facing interaction: public posts on the brand's owned channels, mentions on third-party platforms, direct messages, and private replies. It does not cover outbound social activity (which is governed by separate content and brand rules).

The discipline follows the incident management practice in ITIL 4, where an incident is recorded once and any subsequent reports are linked to the canonical case. In the social context, the "incident" is often a public statement that requires a public response, and the canonical case is the private handling record that contains the customer-side detail. The handover is the bridge between the social conversation and the case record.

## Workflow or implementation guidance

Triage begins at the social monitoring tool. The tool flags inbound contacts that match a defined signal set: customer sentiment, account verification status, mention of a product or service, mention of a competitor, mention of a regulatory body, or any other pattern the brand has set as significant. Each flag opens a triage record with the channel, the timestamp, the customer handle, the post body, and the signal that triggered the flag.

The triage record is reviewed by a social-trained agent. The agent confirms that the contact is genuine (not a bot, not a parody account, not a duplicate of an existing flag), that the customer is reachable through the channel, and that the contact warrants a response. The agent selects a routing path: a public reply, a private reply, a hand-off to the standard support queue, or a hand-off to a specialist queue (security, fraud, legal, regulatory).

A hand-off to the standard support queue produces a case. The case record carries the social triage identifier, the channel, the customer handle, the original post body, the triage agent's identifier, and any private context the customer has shared in a direct message. The case record is keyed to the customer's existing case history if the customer is identified; otherwise, the case is created with a temporary identifier and reconciled later.

A hand-off to a specialist queue produces a different case record. The specialist queue is small, the response time is shorter, and the case is governed by the specialist's discipline (security, fraud, legal, regulatory). The social triage agent's role is to provide the specialist with enough context to act, not to make the specialist's decision.

A public reply is made on the brand's owned channel. The reply is short, on-brand, and refers the customer to a private channel for case handling. The public reply never carries case-identifying information, customer-identifying information beyond the public handle, or any content the customer would not want broadcast. The public reply is logged with the post identifier, the agent identifier, and the timestamp.

## Controls

Three controls protect the handover. The first is the verification of the customer's account: the agent confirms the account is genuine, that the customer has a real relationship with the brand, and that the contact warrants a response. The second is the separation of public and private content: the public post body is captured in the case, but private messages are captured separately and only the specialist who needs them has access. The third is the channel-appropriateness check: the agent confirms that the response is appropriate for the channel (a public reply on a regulated topic is not appropriate, and the case is escalated before any reply is posted).

A separate control protects against the unauthorised public reply. A public reply that names a customer, discloses case detail, or commits the brand to an action is reviewed by a second agent before it is posted. The review is logged.

## Validation evidence

Validation evidence is collected continuously. The social triage log records every flag, every triage decision, and every public reply. The case record carries the hand-off metadata. A periodic audit compares the public reply log against the social channel's actual posts, confirming that every public reply was authorised and that no reply was posted without a recorded triage decision. A tabletop exercise simulates a regulatory inquiry: the organisation must be able to produce, in a defined short window, a list of cases handed off from social, the public replies associated with each, and the authorisation log.

## Failure modes and correction

The most common failure is the public reply that carries too much context. An agent who wants to be helpful includes case detail or customer detail in the public reply, and the customer is exposed. The correction is the second-agent review and the channel-appropriateness check.

The second most common failure is the hand-off that loses context. The specialist queue receives a case without the social context, and the specialist makes a decision that contradicts the customer's expectation. The correction is the case record carrying the social triage identifier and the original post body, and the specialist reviewing the social context before acting.

The third most common failure is the silent triage decision. An agent reads the contact, decides not to respond, and the decision is not recorded. The correction is the log requirement and the periodic audit.

## Limitations

The handover discipline assumes that the social monitoring tool can produce a triage record that the case-management tool can consume. Where the integration is weak, the social agent works from a separate tool and the case record is incomplete. The organisation should confirm that its tool supports the integration before it commits to the discipline.

The discipline also assumes that the brand has defined a social escalation policy. Where the policy is undefined, the social agent makes decisions on a case-by-case basis and the audit has no baseline. The social escalation policy should be documented and reviewed with the same cadence as the case-management policy.

## Canonical sources

- AXELOS, ITIL 4 Incident Management Practice (publisher and title only; AXELOS publications are referenced via https://www.axelos.com/resource-hub/case-studies/itil-4-foundation).
- NIST SP 800-53 Rev. 5, System and Communications Protection control family, https://csrc.nist.gov/pubs/sp/800/53/r5/upd1/final
- ENISA, Risk Management Resources, https://www.enisa.europa.eu/topics/risk-management
- W3C, Technical Report publication conventions, https://www.w3.org/TR/