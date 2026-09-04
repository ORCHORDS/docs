# Secure Query Construction Review

## Trigger
Run before introducing a new database/data-access abstraction, after a SQL-injection finding, after major ORM/query-builder changes, and during periodic secure-coding review.

## Inputs
- Data-access technologies, ORMs, query builders, and database client libraries.
- Raw-query/escape-hatch API inventory.
- Secure coding standard and shared data-access helpers.
- Representative request-to-query data flows.
- Static-analysis and security-test capabilities.

## Procedure
1. Enumerate the supported ways application code can construct and execute database queries.
2. Identify which query paths can receive user-controlled or externally controlled data.
3. Verify ordinary data values use bound/parameterized query mechanisms instead of string concatenation or interpolation into SQL text.
4. Identify raw-query APIs, ORM escape hatches, hand-built query helpers, and other paths that can bypass the secure default.
5. Review dynamic identifiers such as table, column, sort, or direction choices and confirm they use explicit allowlists or another design appropriate to the database/API rather than treating them as ordinary untrusted query text.
6. Search the codebase for prohibited query-construction patterns using automated analysis plus targeted review of high-risk paths.
7. Exercise adversarial inputs through representative standard and raw-query paths and verify data cannot alter the intended SQL structure.
8. When a SQL-injection defect is found, search for the same construction pattern across the wider product and fix the class rather than only the reported call site.
9. Prefer shared safe data-access helpers/framework defaults and restrict or review exceptional raw-query usage.
10. Record legacy paths that cannot be immediately migrated with owners, deadlines, interim tests, and retest evidence.

## Escalation
Escalate user-controlled SQL string construction, ungoverned raw-query escape hatches, repeated injection-class findings, or legacy query paths that remain exposed without an owned migration plan.

## Evidence
- Query-construction path inventory.
- Raw-query/escape-hatch inventory.
- Static-analysis/search results.
- Adversarial test results.
- Class-wide follow-up search after any finding.
- Legacy migration/remediation evidence.

## Completion criteria
Untrusted values use parameterized/bound query mechanisms by default, exceptional query-construction paths are governed, and tests/analysis demonstrate that representative external input cannot become SQL syntax.

## Source basis
- NSA/CISA, Top Ten Cybersecurity Misconfigurations — secure coding and parameterized-query recommendation: https://www.cisa.gov/news-events/cybersecurity-advisories/aa23-278a
