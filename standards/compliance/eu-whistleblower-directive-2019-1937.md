# EU Whistleblower Directive 2019/1937

**Date:** 2026-08-16
**Author:** the platform team
**Status:** published

## Symptom

Your organization operates in the EU with 50+ employees but has no
structured internal reporting channel. Employees who report breaches of EU
law face retaliation, and the company has no process to receive, track, or
investigate whistleblower reports within the 90-day statutory window.

## Context

Directive (EU) 2019/1937 on the protection of persons who report breaches
of Union law ("the Whistleblower Directive") entered into force on
16 December 2019. Member States had until 17 December 2021 to transpose it
into national law (entities with 250+ employees) and 17 December 2023 for
entities with 50-249 employees. All 27 member states have now transposed
the directive, though the average member state was more than a year late.

## Scope

The directive applies to any private or public organization with 50 or more
employees in an EU member state. It covers reports of breaches across a
wide range of EU law areas: public procurement, financial services, product
safety, transport safety, environmental protection, food safety, public
health, consumer protection, data protection, and — since August 2026 —
violations of the EU AI Act (Article 87).

## Core requirements

### Internal reporting channels

Organizations must establish an internal reporting channel that:

- Accepts reports from employees, contractors, suppliers, shareholders,
  board members, volunteers, and former staff.
- Guarantees confidentiality of the reporter's identity.
- Is operationally separate from regular HR channels.
- Allows anonymous reporting if the local transposing law permits (varies
  by member state — France, Germany, and Italy allow anonymous reports;
  others may differ).
- Acknowledges receipt within 7 days.
- Provides feedback on actions taken within 3 months (90 days).

### Investigation obligations

- Every report must be investigated — there is no materiality threshold.
- The investigation must be conducted by an impartial person or department.
- Records of reports must be retained in compliance with GDPR, but must be
  accessible for the statutory period (typically 2-5 years depending on
  member state).

### Anti-retaliation protections

The directive prohibits all forms of retaliation: dismissal, demotion,
suspension, intimidation, harassment, blacklisting, withholding of
training, negative performance assessment, failure to convert a temporary
contract, and early termination of contracts for goods or services.

The burden of proof is reversed — the employer must prove that any
detrimental action was not connected to the report.

## 2026 developments

- **AI Act expansion** — from 2 August 2026, Article 87 of the EU AI Act
  applies Directive 2019/1937 to infringements of the AI Act. Organizations
  deploying or providing AI systems must accept whistleblower reports about
  AI Act violations through the same channels.
- **Cross-border enforcement** — the European Commission is monitoring
  enforcement quality and has initiated infringement proceedings against
  member states with inadequate transposition.

## Anti-patterns

- **Routing reports through HR** — the reporting channel must be
  independent from the department being reported on. A generic HR inbox
  fails the impartiality requirement.
- **No written procedures** — verbal-only processes make it impossible to
  demonstrate compliance with the 7-day acknowledgment and 90-day feedback
  deadlines.
- **Ignoring anonymous reports** — even where anonymous reporting is not
  mandated, dismissing anonymous reports creates legal risk if the
  underlying breach is substantiated.
- **One-size-fits-all across member states** — each member state's
  transposition has local variations (anonymous reporting, penalties,
  scope extensions). A single EU-wide policy must account for local
  differences.

## Gotchas

- **External reporting channels** — if the organization fails to act,
  reporters can escalate to national authorities (external channels) or
  make public disclosures. The directive protects reporters at all three
  tiers (internal → external → public).
- **Penalties vary widely** — Germany: fines up to EUR 50,000 for
  obstructing reports; France: criminal penalties up to 2 years
  imprisonment; Italy: fines up to EUR 50,000 from ANAC. Check each
  jurisdiction.
- **Data protection interaction** — whistleblower reports contain personal
  data of both the reporter and the accused. GDPR data subject access
  requests from the accused must not reveal the reporter's identity.
- **Group-level shared channels** — companies with 50-249 employees in the
  same member state may share reporting channels. Companies with 250+
  employees cannot.

## Verification

- Internal reporting channel is accessible and tested quarterly.
- Acknowledgment of receipt is sent within 7 days (automated).
- Feedback is provided within 90 days — tracked in a case management tool.
- Anti-retaliation policy is documented and communicated to all staff.
- AI Act violations are explicitly included in the reporting scope.
- Data retention policy for whistleblower records complies with local law.

## Related

- `documentation/categories/compliance/gdpr-data-subject-rights.md`
- `documentation/categories/compliance/eu-ai-act-article-5-prohibited-practices.md`
- `documentation/categories/security/secrets-detection-pre-commit.md`

## Source URLs (verified 2026-08-16)

- EU Whistleblowing Directive — https://commission.europa.eu/topics/human-rights/your-fundamental-rights-eu/protection-whistleblowers_en
- AllVoices 2026 Compliance Guide — https://www.allvoices.co/blog/new-eu-whistleblowing-protection-directive
- WeMoral 2026 Transposition Report — https://wemoral.com/reports/eu-whistleblower-transposition/wemoral-report-2026
- Confidly Complete Guide — https://confidly.eu/eu-directive/
