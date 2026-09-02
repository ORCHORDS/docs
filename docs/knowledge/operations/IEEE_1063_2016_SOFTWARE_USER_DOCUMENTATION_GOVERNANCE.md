# IEEE 1063-2016 Software User Documentation Governance

## Purpose

IEEE 1063-2016, "Standard for Software User Documentation," defines requirements and recommendations for the content, structure, and life cycle of software user documentation. The standard addresses the documentation plan, the content (introduction, procedures, reference, troubleshooting, glossary), the organization, the style, the accessibility, the testing of documentation, and the maintenance of documentation as the software evolves. This article governs the application of IEEE 1063 so user documentation is produced and maintained as a controlled deliverable, not as an afterthought.

## Scope

The standard applies to user documentation for software products. Within this knowledge base, the article covers the documentation process (plan, design, draft, review, test, publish, maintain), the content categories the standard identifies, the accessibility requirements, and the documentation maintenance discipline. It does not cover API documentation specifically (the standard focuses on user-facing documentation); API documentation may be covered by other standards (OpenAPI, AsyncAPI).

## Workflow

1. Develop a documentation plan: the documentation scope, the audience, the format (HTML, PDF, both), the tools, the schedule, the responsibilities, and the quality criteria.
2. Design the documentation structure: introduction (what the product is, who it is for, how to get started), procedures (task-based instructions), reference (alphabetical or topic-based), troubleshooting, and glossary.
3. Draft the content following the documentation plan. Use a consistent voice, terminology, and structure.
4. Review the documentation for technical accuracy, completeness, clarity, accessibility, and style consistency.
5. Test the documentation: a tester or user follows the procedures using the documentation alone. Identify gaps and ambiguities.
6. Publish the documentation in the chosen format. Use version control and a publishing pipeline that matches the engineering pipeline.
7. Maintain the documentation: each change to the software that affects user behavior is paired with a documentation update before release.

## Controls and evidence

Documentation evidence includes the documentation plan, the draft documents, the review records, the test reports, the published artifacts, and the maintenance records. Each documentation change should be traceable to the corresponding software change.

## Validation

Validation should confirm the documentation plan is current, the content covers the categories the standard lists, the documentation passes the test procedure, the published version matches the software version, and the maintenance discipline operates. Periodic documentation audits confirm the documentation remains accurate.

## Failure correction

Common failure modes: documentation is published but not maintained (correct: enforce the documentation update requirement for each software change); documentation is not tested (correct: integrate documentation testing into the release process); documentation is fragmented across multiple sources (correct: consolidate into a single documentation site); documentation is not accessible (correct: apply accessibility standards and test with assistive technology); documentation is for the developer, not the user (correct: review the audience and adjust the style).

## Limitations

IEEE 1063 is a process and content standard for user documentation; it does not certify any documentation. The standard does not prescribe a specific documentation tool (DITA, Markdown-based static site generators); readers should select the tool that fits their context. The standard does not address API documentation specifically.

## Scope note

This article summarizes project-neutral operations use of IEEE 1063-2016. It does not assert any specific documentation's conformance or claim any certification outcome.

## Canonical sources

- IEEE 1063-2016 — Standard for Software User Documentation: https://standards.ieee.org/ieee/1063/6034/