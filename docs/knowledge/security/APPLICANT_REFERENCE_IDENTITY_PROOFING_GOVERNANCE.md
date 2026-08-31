# Applicant Reference Identity-Proofing Governance

## Purpose

NIST SP 800-63A-4 defines an applicant reference as a representative of an applicant who can support identity proofing by vouching for the applicant's identity, specific attributes, or circumstances when ordinary evidence, validation, or verification is unavailable or insufficient.

An applicant reference is not a credential service provider (CSP) decision-maker and is not the same role as a trusted referee. The reference represents the applicant and supplies supporting statements or relationship evidence; the CSP remains responsible for the identity-proofing process and its assurance decision.

## When applicant references can help

NIST permits applicant references at IAL1 and IAL2 when the CSP and relying party (RP) support them and the applicable requirements are met.

Potential use cases include situations where the reference can:

- vouch for one or more claimed core attributes;
- vouch for the identity of an applicant who lacks sufficient identity evidence; or
- vouch for a relevant condition or circumstance, such as homelessness or a disaster-related displacement, when that information helps the proofing risk decision.

The reference's statement supports identity proofing. NIST explicitly separates this from using the statement to establish eligibility for a benefit, legal status, or entitlement.

## Public and documented process

If applicant references are supported, the CSP should make the option discoverable and explain any relationship requirements.

Document:

- which IALs and service channels permit applicant references;
- acceptable uses of a reference;
- prohibited uses;
- required relationship, if any;
- how the reference is identity-proofed;
- evidence required to confirm a relationship when relationship confirmation is necessary;
- statements, acknowledgements, or signatures that are recorded;
- privacy and retention treatment; and
- the redress path when the reference process cannot support a successful proofing decision.

CSP and RP contracts or trust agreements should describe all acceptable applicant-reference uses where the capability is offered.

## Proofing the reference

NIST requires an applicant reference to be identity-proofed to the same or a higher IAL than the intended IAL for the applicant.

This prevents a weak or anonymous reference path from being used to establish a stronger identity claim for another person.

A reusable control sequence is:

1. determine the target applicant IAL;
2. identity-proof the reference to at least that IAL;
3. record a stable reference identifier suitable for linking the proofing event to the subscriber account;
4. apply privacy and retention controls to the reference's information; and
5. re-evaluate stale or invalid reference proofing when policy requires it.

Do not assume a professional title, personal relationship, or possession of a contact method is equivalent to identity proofing the reference.

## Relationship confirmation

Not every service needs to prove the relationship between the applicant and the reference. NIST makes relationship confirmation risk-based.

If the CSP or RP requires relationship confirmation, define the acceptable evidence before an individual case begins.

The process should:

- state which relationships are acceptable for the use case;
- publish or otherwise provide the acceptable evidence types to the reference;
- request evidence appropriate to the claimed relationship;
- review the evidence under documented criteria; and
- record the evidence used to establish the relationship in the subscriber account after successful proofing.

Examples of relationship evidence can include formal authority documents or professional credentials, but appropriate evidence depends on the context and jurisdiction.

## Reference statements

The CSP needs a record of the role the applicant reference played in the proofing event.

Depending on legal and operational needs, the record can include:

- statements or assertions made by the reference;
- the attributes or identity facts the reference supported;
- the condition or circumstance the reference described;
- a digital or physical signature;
- consent or acknowledgement; and
- information provided to the reference about legal or liability implications.

NIST requires the CSP to make clear and understandable information about potential legal or liability implications available to the reference.

Avoid asking references to make broad declarations that are unnecessary for the identity-proofing purpose.

## Privacy risk assessment

Information collected about applicant references can itself be sensitive personal information.

NIST requires the information collected, recorded, and retained to identity-proof applicant references to be included in the CSP's privacy risk assessment.

Consider:

- why each reference attribute is necessary;
- whether relationship information creates sensitive inferences;
- retention duration;
- who can access the record;
- whether the reference information can be used for other purposes;
- whether third parties process the information; and
- how the record is deleted or de-linked when no longer required.

The reference process should not become a secondary data-collection channel unrelated to identity proofing.

## RP risk decision

NIST requires the RP to assess the business requirements and risks associated with including or excluding applicant references.

Questions include:

- Does excluding references create disproportionate access barriers for the user population?
- What fraud scenarios could exploit the reference path?
- What types of reference relationships provide useful assurance for the service?
- Are the CSP's proofing, recordkeeping, and privacy controls adequate for the RP's risk tolerance?
- Does the RP need restrictions beyond the CSP's general policy?

Record the resulting requirements in the relevant trust or service agreement.

## Subscriber-account record

When an applicant reference is used, the subscriber account should retain the information needed to understand the proofing history.

NIST requires recording use of the applicant reference and maintaining a record of the reference and their relationship to the applicant. The broader subscriber-account record also needs enough information to reconstruct important proofing steps.

A reusable record can include:

- reference identifier;
- reference IAL;
- role played by the reference;
- relationship and how it was established, when required;
- statements or attributes supported;
- evidence considered;
- proofing date;
- target and achieved applicant IAL; and
- applicable consent or acknowledgement records.

## Minors

SP 800-63A-4 contains additional requirements for identity proofing people under 18 and requires support for applicant references when interacting with minors.

Services involving minors should separately evaluate applicable child-privacy and consent laws and should not assume that the general adult reference workflow is legally sufficient in every jurisdiction.

## Abuse and collusion considerations

An applicant-reference process can be targeted by coordinated fraud.

Risk controls can include:

- detecting one reference used unusually often;
- detecting clusters of references and applicants sharing suspicious data or devices;
- limiting unsupported changes to core attributes;
- reviewing high-risk reference patterns;
- separating identity-proofing decisions from reference statements; and
- investigating confirmed abuse without automatically treating legitimate high-volume professional reference roles as fraudulent.

Controls should be tested for unintended exclusion or bias as well as fraud-prevention effectiveness.

## Operational workflow

A practical workflow is:

1. Determine that the standard proofing path cannot be completed or that policy otherwise permits a reference.
2. Explain the reference option and requirements to the applicant.
3. Confirm that the proposed reference meets role and relationship criteria.
4. Identity-proof the reference to the required IAL.
5. Confirm the relationship when risk policy requires it.
6. Capture only the statements and evidence needed for the allowed use.
7. Evaluate the applicant's proofing case using the reference information as one part of the evidence.
8. Record the reference's role and the final proofing decision.
9. Provide redress or an alternative path if proofing cannot be completed.
10. Review reference usage patterns for fraud, privacy, accessibility, and process-quality issues.

## Sources

- NIST SP 800-63A-4 — Identity Proofing and Enrollment: https://pages.nist.gov/800-63-4/sp800-63a.html
- NIST SP 800-63 Revision 4 publication hub: https://pages.nist.gov/800-63-4/

## Scope note

This article summarizes reusable applicant-reference governance from NIST SP 800-63A-4. It does not establish benefit eligibility, legal guardianship, legal authority, or a specific person's identity and does not claim that any ORCHORDS service implements a NIST-compliant applicant-reference process.