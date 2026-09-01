# IETF RFC 3552 Security Considerations Governance

## Purpose

RFC 3552, *Guidelines for Writing RFC Text on Security Considerations*, is the Internet Engineering Task Force (IETF) Best Current Practice (BCP) 72 document that defines how RFC authors should discuss security in the Internet standards process. Published in July 2003 and unchanged in its BCP assignment, RFC 3552 remains the canonical primary authority for documenting security considerations in Internet Drafts and RFCs. The Internet Engineering Steering Group (IESG) requires a Security Considerations section in essentially every published RFC.

This article summarizes a governance pattern for adopting RFC 3552 practices beyond the standards-writing context. Adopting organizations can apply the same questions and structure to specification documents, internal architecture documents, threat models, and incident post-mortems to ensure that security-relevant trade-offs are visible to reviewers and downstream implementers. It does not assert compliance with any IETF process and does not replace RFC 3552 itself.

## Scope

RFC 3552 was written for the IETF standards process, but the questions it raises are universally applicable. A reusable program should document:

- which internal documents are required to include a Security Considerations section, and at what level of detail;
- the relationship between the Security Considerations section of an internal document and any external review (for example, customer-facing documentation, regulatory submission, or partner review);
- the roles responsible for the Security Considerations content (author, security reviewer, approver); and
- the boundary between security considerations, threat models, and risk registers. Threat models can be tightly focused on a specific component; Security Considerations are written for the reader of the document.

The publication does not prescribe specific threat actors, attacks, or mitigations for any specific technology. Those are addressed in technology-specific RFCs.

## Workflow

A reusable RFC 3552-aligned process runs as a small cycle.

1. **Identify the asset and stake.** Document what is being protected (a protocol, a service, an interface, a stored data set), why it matters, and who the relevant stakeholders are.
2. **Identify threats.** Catalog threats against the asset, using the asset-attacker-interface decomposition that RFC 3552 describes. Distinguish passive from active attackers, on-path vs. off-path, and insider from outsider.
3. **Identify mitigations.** Document the controls that address each threat, whether they are mandatory or optional, and where they are implemented.
4. **Identify residual risks.** Document what is *not* mitigated and why. Distinguish accepted risks from unanalyzed risks.
5. **Write the Security Considerations section.** Use the section structure that RFC 3552 recommends, with a clear set of threats, mitigations, and residual risks.
6. **Review.** Submit the document to a security reviewer who is not the author. Address review comments before approval.
7. **Approve and publish.** Record the approver, date, and version. Maintain version history so reviewers of older copies can see what changed.
8. **Update on change.** Reopen the Security Considerations section when the design, threat picture, or mitigations change.

## Controls and evidence

A program applying RFC 3552 to internal documents should map its controls to the publication's recommended structure and retain evidence accordingly.

| Section element | Typical content | Typical evidence |
|---|---|---|
| Asset description | What is being protected and why | Document section, design rationale |
| Threat model summary | Attacker classes, interfaces, attack surfaces | Threat-model diagram, threat catalog |
| Mitigations | Controls in design, with placement and rationale | Implementation evidence, configuration evidence |
| Residual risks | What is not mitigated and why | Risk register entry, accepted-risk record |
| Operational considerations | Deployment guidance, configuration caveats | Deployment guide, configuration baseline |
| Review and approval | Reviewer, approver, date | Review log, approval record |

A program should retain at minimum: the document under review, with version and date; the Security Considerations section as published; the threat catalog or model used to populate it; the review log; the approval record; and the schedule for the next review.

## Validation

Validation confirms that the Security Considerations section actually reflects the deployed system. Useful activities include:

- reviewing a sample of documents and confirming that each has a Security Considerations section;
- confirming that the threats listed in the section correspond to a current threat model rather than a historical snapshot;
- confirming that mitigations referenced in the section are actually implemented;
- reviewing residual risks for appropriate ownership and acceptance;
- reviewing the review log for an independent reviewer; and
- comparing the most recent document with the previous version to confirm Security Considerations are updated when the design changes.

Validation must distinguish compliant, non-compliant, and unable-to-assess states. A document that lacks a Security Considerations section should not be approved.

## Failure correction

When a Security Considerations control fails, follow a documented path.

1. Confirm the failure with reproducible evidence.
2. Identify the element that is missing or incorrect (asset description, threat, mitigation, residual risk, review).
3. Apply the corrective change to the document and any related artifacts.
4. Verify that the change is published and that downstream readers can see the updated section.
5. Update the template or training if the failure is systemic.

Common failure modes include:

- listing generic threats without grounding them in the specific document's interfaces and design choices;
- asserting that the design is "secure" without specifying what threats were considered;
- omitting residual risks, making it impossible for downstream readers to make informed deployment decisions;
- reviewing only by the author rather than by a separate security reviewer;
- failing to update the section when a protocol, API, or threat model changes; and
- treating Security Considerations as a compliance step at the end of writing rather than as a design input.

## Limitations

RFC 3552 predates many IETF security developments that have become operationally important, including:

- the IETF trust statements published in RFC 7258 ("Pervasive Monitoring Is an Attack") and RFC 7624 ("Confidentiality in the Face of Pervasive Surveillance");
- the security-relevant updates consolidated in RFC 9325 ("Recommendations for Secure Use of TLS and DTLS");
- the increasing use of formal security frameworks (for example the Internet Security Glossary published as RFC 4949 and updated material since).

RFC 3552 should be read alongside these newer documents rather than as a stand-alone, current reference.

## Canonical sources

- IETF RFC 3552 / BCP 72 — *Guidelines for Writing RFC Text on Security Considerations*, July 2003: https://datatracker.ietf.org/doc/rfc3552/
- IETF RFC 7258 — *Pervasive Monitoring Is an Attack* (BCP 188), complements the threat-model framing for Security Considerations: https://datatracker.ietf.org/doc/rfc7258/
- IETF RFC 4949 — *Internet Security Glossary, Version 2* (terminology for Security Considerations writing): https://datatracker.ietf.org/doc/rfc4949/

## Scope note

This article summarizes reusable governance practices derived from RFC 3552 / BCP 72. It is not a substitute for the IETF document, does not assert conformity with any IETF process, and does not constitute professional advice on the security of any specific protocol or system.
