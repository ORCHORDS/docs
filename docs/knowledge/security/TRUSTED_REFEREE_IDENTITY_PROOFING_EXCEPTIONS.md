# Trusted Referee Identity-Proofing Exceptions

## Purpose

NIST SP 800-63A-4 formalizes trusted referees as a risk-based identity-proofing exception path for applicants who cannot complete the ordinary evidence, validation, or verification process for a defined Identity Assurance Level (IAL).

Trusted referees support accessibility and inclusion without turning exception handling into an undocumented bypass. Their use needs written eligibility rules, trained decision-makers, evidence review, session records, consistent attended-proofing controls, and an explainable final decision.

## Role boundary

A trusted referee is different from a routine proofing agent.

A proofing agent performs defined proofing activities and limited risk-based judgments in the standard process. A trusted referee receives additional training and authority to make risk-based decisions in exception scenarios, such as when:

- an applicant does not possess the ordinarily required identity evidence;
- an applicant cannot be found in an expected authoritative or credible record source;
- core attributes only partially match because of a legitimate change, such as a recent move or name change;
- an automated biometric or validation process fails; or
- the applicant's circumstances make the standard path inaccessible or impractical.

The trusted referee does not remove the need to determine what IAL was actually achieved.

## Accessibility objective

SP 800-63A-4 identifies trusted referees as an important way to support applicants who might otherwise be excluded from digital services. Examples can include people who:

- lack conventional identity evidence;
- have disabilities;
- are older;
- are experiencing homelessness;
- have limited access to devices or online services;
- lack conventional financial or credit histories;
- are victims of identity theft;
- are displaced by disasters; or
- are minors.

The existence of an exception path should be communicated clearly enough that eligible applicants can actually find and request it.

## Written eligibility rules

A credential service provider (CSP) should define which failures or exceptions can be routed to a trusted referee.

Document at least:

- eligible failure categories;
- proofing types and IALs supported by the exception path;
- additional evidence types a referee may consider;
- conditions that require escalation or rejection;
- limits on referee discretion;
- fraud indicators that require specialized review;
- whether remote attended, on-site attended, or both service modes are supported; and
- redress options following an adverse decision.

Do not rely on an unwritten practice in which individual staff members decide case-by-case what evidence is "good enough."

## Training and qualification

NIST requires CSPs that use trusted referees to train and certify them for risk-based decisions.

Training includes areas such as:

- identity-document formats and security features;
- indicators of document damage, tampering, fabrication, or forgery;
- visual facial image comparison;
- indicators of social engineering, distress, confusion, or coercion; and
- the organization's documented exception policies.

Where referees conduct visual evidence inspection or facial comparison, their abilities need periodic reassessment consistent with the NIST requirements. Keep training and assessment evidence current rather than assuming initial qualification remains sufficient indefinitely.

## Exception workflow

A reusable process can follow these stages:

1. **Detect the exception.** Record why the ordinary identity-proofing process could not be completed.
2. **Check eligibility.** Determine whether the documented policy permits trusted-referee handling for that failure.
3. **Route to an attended process.** Use the on-site or remote attended workflow supported for the target IAL.
4. **Provide context.** Give the referee relevant failure information without unnecessarily disclosing unrelated personal data.
5. **Review additional evidence.** Evaluate evidence for authenticity to the greatest degree supported by that evidence type.
6. **Reconcile attributes.** Where authoritative or credible sources are unavailable, compare available evidence for consistency; where attributes partially mismatch, review evidence supporting legitimate changes.
7. **Make the decision.** Record the risk-based result and rationale.
8. **Create the proofing record.** Record the referee identity, reason for use, evidence considered, processes completed, result, and negative rationale where applicable.
9. **Communicate outcome and redress.** Provide the applicant with the next step appropriate to the service.
10. **Feed recurring failures back into process improvement.** Repeated exception patterns may reveal accessibility, data-quality, fraud-control, or vendor problems in the standard path.

## Fraud-check failures

SP 800-63A-4 recommends offering trusted-referee services to applicants who fail certain fraud checks in unattended remote processes where the service supports that path.

When a referee handles a fraud-check failure, the referee should receive a useful summary of the failed checks to inform the risk decision. Do not expose unnecessary fraud-detection internals or treat the summary as an automatic instruction to reject the applicant.

A referee is an additional review path, not a mechanism for ignoring a confirmed fraud event.

## Additional evidence

If the CSP uses trusted referees to address evidence or attribute-validation failures, it needs a policy for additional evidence types.

Important controls include:

- define acceptable supplemental evidence before individual cases arise;
- train referees to assess the evidence types they may receive;
- examine supplemental evidence for authenticity as far as the medium allows;
- distinguish absence of a record from evidence of fraud;
- distinguish a legitimate attribute change from an unsupported conflicting claim; and
- retain enough decision evidence to explain why the case was accepted or rejected.

## Remote attended sessions

Remote attended exception handling inherits the security requirements that apply to remote attended identity proofing.

Referees need sufficient media quality and tools to inspect evidence and compare applicants. The remote workflow should also apply applicable protections for digital injection, forged media, protected communications, and human-in-the-loop challenges.

Accessibility accommodations should be designed into the process. A control that cannot be performed by a particular applicant should have a documented alternative when risk allows rather than forcing the applicant into an impossible path.

## Recordkeeping

NIST requires a record for proofing sessions involving a trusted referee. A reusable record should include:

- why the referee path was invoked;
- the trusted referee who handled the case;
- identity evidence presented;
- validation and verification activities completed;
- supplemental evidence considered;
- the decision;
- rationale for a negative decision; and
- the IAL ultimately associated with the subscriber account.

Protect these records according to their sensitivity and retention requirements. Exception handling often creates additional personal information and should be included in privacy-risk and records-management decisions.

## Independence and abuse controls

Because trusted referees can intervene in proofing decisions, organizations should address insider and collusion risks.

Useful controls can include:

- role separation where practical;
- case assignment controls;
- audit logging;
- supervisor review for defined high-risk cases;
- periodic sampling of decisions;
- conflict-of-interest handling;
- anomaly detection for unusual approval patterns; and
- removal or retraining when qualification standards are no longer met.

These are governance examples; the appropriate controls depend on the service and risk environment.

## Metrics and review

Track exception handling to improve both security and access. Useful measures can include:

- reason codes for referee use;
- acceptance and rejection rates by exception type;
- redress outcomes;
- confirmed fraud discovered through referee review;
- false failures in the standard process;
- processing time;
- accessibility issues; and
- recurring evidence or record-source gaps.

Metrics should be interpreted carefully. A high exception rate can reflect a population mismatch or poor standard-process design rather than applicant risk.

## Sources

- NIST SP 800-63A-4 — Identity Proofing and Enrollment: https://pages.nist.gov/800-63-4/sp800-63a.html
- NIST SP 800-63 Revision 4 publication hub: https://pages.nist.gov/800-63-4/

## Scope note

This article summarizes reusable trusted-referee governance from NIST SP 800-63A-4. It does not define eligibility for government benefits, make identity decisions about any individual, or claim that any ORCHORDS service implements a NIST-compliant trusted-referee process.