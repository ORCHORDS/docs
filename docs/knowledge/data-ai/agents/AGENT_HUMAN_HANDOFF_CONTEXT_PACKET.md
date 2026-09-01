# Human Handoff Context Packet Using the A2A Task Handoff Message Format

## Scope

Some agent tasks must be handed to a human. Authorization boundaries, ambiguity, policy violations, or simple operational limits all trigger a handoff. A handoff that arrives with insufficient context is worse than no handoff at all, because the human starts from a worse position than the user did. A handoff that arrives with too much context, or with sensitive context exposed, is a different kind of failure.

The A2A protocol defines a task and message model for inter-agent communication, with explicit handling for handoffs between parties. This article applies the A2A task and message format to the agent-to-human handoff as a structured context packet. The handoff is a message in the protocol sense: it carries task identifier, sender, recipient, content parts, and metadata sufficient for the recipient to act.

## Workflow or implementation guidance

1. Treat handoff as a first-class task state, not as an exception. The agent's runtime should know when it is handing off, where the handoff is going, and what handoff means in terms of the task lifecycle. Handoffs outside the model are visible, auditable, and testable.
2. Construct the context packet as a structured A2A message: task identifier, originating context, current state, attempted actions, expected next steps, authorization boundary encountered, and the question that requires human judgment. Free-form prose may be included as a content part, but the structured fields are what make the handoff actionable.
3. Include only the context the human needs to act. The full conversation transcript is usually not needed; a summary with cited evidence is. Include enough that the human can reconstruct what happened without re-running the agent, but not so much that sensitive content is exposed by default.
4. Apply redaction at the handoff boundary, not at the human's terminal. A redacted packet should not become unredacted at display. Define redaction rules per recipient role and per task sensitivity tier, and apply them as part of the handoff construction.
5. Provide bidirectional continuation. The human should be able to act, return a decision, and have the agent resume from the documented state. The packet is part of a conversation, not a one-way notification.
6. Record the handoff as an audit event with actor, reason, and authorization. A human's involvement changes accountability; the audit log must reflect that the agent handed off and that the human accepted or returned the work.
7. Standardize handoff types. A handoff for policy review, a handoff for ambiguous user intent, a handoff for authorization escalation, and a handoff for tool unavailability each carry different context requirements. Treating them as a single "human in the loop" event loses information the operator needs.
8. Allow human override of the agent's framing. The handoff packet should not lock the human into the agent's interpretation; it should include the human's space to record disagreement or new context. The human's record is part of the evidence for downstream review.

## Controls

Authorization to hand off and to accept handoffs is a control, not a metadata tag. Define who can accept a handoff in each role, and what authority they exercise when they accept. A handoff that anyone in a recipient role can silently absorb is not a controlled handoff.

SLA on handoffs is necessary because handoffs without response times become abandoned work. Set response expectations by handoff type, and surface breaches to operators rather than letting them accumulate. A handoff queue without SLA is a queue that grows until it is cleaned by accident.

Retention of handoff packets aligns with retention of task evidence. A packet should be retained for the same window as the task itself, and redaction should be applied consistently across the lifecycle. A redacted packet that loses its source context in retention is not auditable.

## Validation evidence

Demonstrate the structured format. A handoff constructed under the rules yields a packet that includes the required fields, that is parseable as an A2A message, and that the recipient system can render meaningfully. Demonstrate that the same handoff type produces the same structured fields across runs.

Demonstrate redaction. Sensitive content present in the agent's full context is absent from the handoff packet, and the recipient role has a defined view of the remaining content. Demonstrate that redaction is irreversible at display: a UI customization does not unredact the packet.

Demonstrate continuation. A handoff is returned with a human decision, the agent resumes from the documented state, and the resumption is recorded with the human actor and reason. Demonstrate that an abandoned handoff is detected: the SLA timer expires, the queue is alerted, and the work is either re-routed or escalated.

## Failure modes and correction

A common failure is the unstructured handoff: a free-text note that depends on the recipient knowing the agent's history. Correct by enforcing a structured packet and validating the required fields at handoff time, not at recipient review time.

A second failure is over-disclosure. The agent hands off everything it knows because the rules for what is needed are unclear. Correct by enumerating required fields per handoff type and treating everything else as a redaction candidate unless explicitly justified.

A subtler failure is the abandoned handoff. The agent hands off and forgets; no SLA, no escalation, no resumption logic. Correct by treating handoff as a long-running task with explicit response expectations, and by alerting on breaches. The handoff should be testable end to end, not assumed to work because the message was sent.

## Limitations

The A2A protocol specifies message structure but does not dictate what is appropriate to include in a human-directed packet. Governance of handoff content remains an organizational responsibility. The handoff is also limited by the protocol's assumption that the recipient can interpret the packet correctly; for sensitive cases, additional training may be required. Finally, handoff discipline does not substitute for designing the agent to handle as many cases as possible without handoff in the first place; handoff should be a deliberate choice, not a default.

## Canonical sources

- **A2A Protocol, specification home:** https://a2a-protocol.org/
- **A2A Protocol, current specification (task object and message model):** https://a2a-protocol.org/latest/specification/
- **Model Context Protocol, specification index (interoperable agent ecosystem context):** https://modelcontextprotocol.io/specification/2025-11-25
