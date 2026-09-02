# OpenSSF CII Best Practices Badge Governance

## Purpose

The OpenSSF (Open Source Security Foundation) CII Best Practices Badge is a program that allows open source projects to self-certify that they follow a set of best practices in software security. The badge criteria are organized into passing, silver, and gold tiers, covering areas such as code review, automated testing, vulnerability disclosure, security update process, and the project's governance. This article governs the application of the CII Best Practices Badge criteria so an open source project can pursue and maintain the badge with discipline.

## Scope

The badge applies to open source projects. Within this knowledge base, the article covers the badge criteria (passing, silver, gold), the evidence required for each criterion, the self-certification process, the public badge page, and the documentation of the project's conformance. It does not certify the project; the CII Best Practices Badge is self-certification with public disclosure.

## Workflow

1. Review the CII Best Practices Badge criteria for the target tier (passing, silver, gold).
2. For each criterion, identify the evidence the project has or must produce. Criteria include:
   - Project basics: license, source repository, public issue tracker, public discussion forum.
   - Automated testing: tests are run, the test suite is documented, and changes are gated by passing tests.
   - Code review: each change is reviewed before merging.
   - Security: vulnerabilities are disclosed privately and resolved; security updates are produced and communicated.
   - Quality: the project uses a recognized style guide; the code is analyzed for known vulnerabilities.
   - Governance: the project has a governance document, contributors are recognized, and the project has a clear decision-making process.
3. Implement any missing practices. Many projects need to add CONTRIBUTING, SECURITY, CODE_OF_CONDUCT, and governance documentation.
4. Document the evidence for each criterion. Each criterion has a defined evidence requirement.
5. Submit the badge application through the CII Best Practices Badge site. The application lists the evidence and the project's URL.
6. Maintain the badge. The CII Best Practices Badge requires periodic re-application to confirm the practices remain in place.

## Controls and evidence

Badge evidence is per criterion. Each criterion defines what evidence the project must produce — typically a URL to a document or repository. The application is public. The project should maintain the evidence and update it on changes.

## Validation

Validation should confirm the project's evidence is current, the practices are actually followed (e.g., the SECURITY file describes a real process, not aspirational language), and the badge is renewed. Periodic audits of the evidence confirm the badge's accuracy.

## Failure correction

Common failure modes: the badge is pursued but the practices are not actually implemented (correct: implement the practices before applying); the evidence is one-off and not maintained (correct: maintain the evidence and re-apply on each renewal); vulnerabilities are not disclosed (correct: implement a private disclosure mechanism — e.g., a SECURITY file with a contact); governance is implicit (correct: write down the governance process).

## Limitations

The CII Best Practices Badge is a self-certification; it does not certify the project's security. The badge criteria are minimum practices; following them does not guarantee the project is secure. The badge does not address every security concern (e.g., supply chain attacks, AI-specific risks).

## Scope note

This article summarizes project-neutral platform use of the OpenSSF CII Best Practices Badge. It does not assert any specific project's conformance or claim any certification outcome.

## Canonical sources

- OpenSSF — CII Best Practices Badge: https://www.bestpractices.dev/
- OpenSSF — CII Best Practices Badge Criteria: https://www.bestpractices.dev/en/criteria