# Code Scanning — CodeQL Custom Queries and Security Analysis

**Date:** 2026-08-16
**Author:** the platform team
**Status:** published

## Symptom

Your repository has GitHub code scanning enabled with the default
CodeQL query suite, but it only catches generic vulnerabilities. You
have company-specific security patterns — custom authentication
middleware that must be called before database access, internal APIs
that should never receive user input directly, and framework-specific
patterns that the default queries do not understand. You need to write
custom CodeQL queries that encode your organization's security rules
and catch domain-specific vulnerabilities.

## Context

CodeQL is a semantic code analysis engine that treats code as queryable
data. It builds a database representation of your codebase — AST,
control flow graph, data flow graph, type information — and lets you
write queries in a SQL-like language (QL) to find patterns across
functions, files, and modules. In 2026, CodeQL 2.25+ ships 491
security queries covering 166 CWE categories across JavaScript,
TypeScript, Python, Java, C#, Go, Ruby, Swift, and C/C++. GitHub
Advanced Security includes CodeQL code scanning in pull requests, and
the query libraries are open source, allowing teams to write custom
queries for organization-specific patterns. Custom queries can be added
to code scanning workflows via query packs or configuration files.

## Default query suites

```
code-scanning (default):
  → High-confidence, low false-positive queries
  → Runs automatically on PRs and pushes
  → ~200 queries covering critical CWEs
  → Best for: most repositories

security-extended:
  → Default + lower-confidence security queries
  → More coverage, slightly higher false-positive rate
  → ~350 queries
  → Best for: security-sensitive repositories

security-and-quality:
  → Security + code quality queries
  → Maintainability, complexity, code smells
  → ~491 queries
  → Best for: repositories with quality gates
```

## GitHub Actions configuration

```yaml
name: CodeQL Analysis
on:
  push:
    branches: [main]
  pull_request:
    branches: [main]
  schedule:
    - cron: '0 6 * * 1'  # Weekly Monday 6am UTC

jobs:
  analyze:
    runs-on: ubuntu-latest
    permissions:
      security-events: write
      contents: read

    strategy:
      matrix:
        language: ['javascript', 'python']

    steps:
      - uses: actions/checkout@v4

      - name: Initialize CodeQL
        uses: github/codeql-action/init@v3
        with:
          languages: ${{ matrix.language }}
          queries: security-extended,./custom-queries

      - name: Autobuild
        uses: github/codeql-action/autobuild@v3

      - name: Perform Analysis
        uses: github/codeql-action/analyze@v3
        with:
          category: '/language:${{ matrix.language }}'
```

## Custom query structure

```ql
/**
 * @name SQL injection from user input
 * @description Finds SQL queries that include unsanitized user input
 * @kind path-problem
 * @problem.severity error
 * @security-severity 9.8
 * @precision high
 * @id myorg/sql-injection-custom
 * @tags security
 *       external/cwe/cwe-089
 */

import javascript
import semmle.javascript.security.dataflow.SqlInjectionQuery
import DataFlow::PathGraph

from SqlInjection::Configuration cfg, DataFlow::PathNode source, DataFlow::PathNode sink
where cfg.hasFlowPath(source, sink)
select sink.getNode(), source, sink,
  "This SQL query depends on $@.", source.getNode(), "user-provided value"
```

## Custom query examples

```ql
// Find unvalidated redirects (organization-specific)
/**
 * @name Open redirect via request parameter
 * @kind path-problem
 * @problem.severity warning
 * @id myorg/open-redirect
 */

import javascript
import semmle.javascript.security.dataflow.ServerSideUrlRedirectQuery
import DataFlow::PathGraph

from Configuration cfg, DataFlow::PathNode source, DataFlow::PathNode sink
where cfg.hasFlowPath(source, sink)
select sink.getNode(), source, sink,
  "Redirect URL comes from $@.", source.getNode(), "user input"
```

```ql
// Find missing authentication middleware (org-specific)
/**
 * @name Route handler without auth middleware
 * @kind problem
 * @problem.severity warning
 * @id myorg/missing-auth-middleware
 */

import javascript

class ExpressRoute extends DataFlow::CallNode {
  string method;
  ExpressRoute() {
    exists(DataFlow::SourceNode router |
      router.getAPropertyRead(method).getACall() = this and
      method in ["get", "post", "put", "delete", "patch"]
    )
  }

  predicate hasAuthMiddleware() {
    exists(DataFlow::Node arg |
      arg = this.getAnArgument() and
      arg.getALocalSource().toString().matches("%auth%")
    )
  }
}

from ExpressRoute route
where
  not route.hasAuthMiddleware() and
  not route.getArgument(0).getStringValue().matches(["/health", "/ready", "/metrics"])
select route, "Route handler missing authentication middleware."
```

## Query pack structure

```
my-custom-queries/
├── qlpack.yml
├── queries/
│   ├── security/
│   │   ├── MissingAuth.ql
│   │   ├── UnsafeDeserialization.ql
│   │   └── HardcodedSecrets.ql
│   └── quality/
│       ├── LargeFunction.ql
│       └── DeadCode.ql
└── lib/
    └── MyOrgSources.qll   # shared library
```

```yaml
# qlpack.yml
name: myorg/custom-security-queries
version: 1.0.0
libraryPathDependencies:
  - codeql/javascript-all
  - codeql/javascript-queries
extractor: javascript
defaultSuiteFile: suite.qls
```

```yaml
# suite.qls
- queries: queries/security
- queries: queries/quality
```

## Anti-patterns

- **Overly broad queries** — writing queries with low precision
  that flag hundreds of false positives. Engineers stop reviewing
  findings and real issues get lost. Aim for high precision (>90%)
  even if recall is lower.
- **Not using data flow analysis** — writing pattern-matching
  queries that look for specific function names without tracking
  whether tainted data actually reaches them. CodeQL's data flow
  libraries track values across function calls and assignments —
  use them.
- **Ignoring the default suite** — writing custom queries for
  patterns already covered by the default or extended suite.
  Review existing queries first. Customize when your patterns
  are domain-specific.
- **No test cases for custom queries** — deploying custom queries
  without test cases showing true positives and true negatives.
  CodeQL's testing framework lets you annotate expected results
  inline.

## Gotchas

- **Build required for compiled languages** — CodeQL needs to
  observe the build for Java, C#, C++, and Go. If autobuild fails,
  you must configure the build step manually. JavaScript and Python
  do not require a build step.
- **Analysis time on large repos** — CodeQL analysis can take
  15-45 minutes on large codebases. Schedule full analysis nightly
  and run a reduced query set on PRs for faster feedback.
- **Query compatibility across versions** — CodeQL library APIs
  change between versions. Pin your query pack's library
  dependencies and test after CodeQL upgrades. The 2.25 release
  broke Java/Kotlin custom queries with a CFG rewrite.
- **SARIF result limits** — GitHub code scanning limits results
  to 5,000 alerts per SARIF file. Large codebases with broad
  queries may hit this limit. Filter by severity or split analysis
  by directory.

## Verification

- Default query suite runs on every PR and push to main.
- Custom queries have test cases with annotated expected results.
- False positive rate is below 10% for custom queries.
- Security findings block PR merge via branch protection rules.
- Weekly scheduled scan catches issues not covered by PR analysis.
- Query pack is versioned and tested before deployment.

## Related

- `documentation/docs/policies/github/composite-actions-reusable-workflows.md`
- `documentation/docs/policies/security/owasp-top-10-2025.md`
- `documentation/docs/policies/testing/mutation-testing-stryker-pitest.md`

## Source URLs (verified 2026-08-16)

- GitHub CodeQL Review 2026: Semantic Security Analysis — https://appsecsanta.com/github-codeql
- Code Scanning with CodeQL — https://docs.github.com/code-security/code-scanning/introduction-to-code-scanning/about-code-scanning-with-codeql
- CodeQL Query Suites — https://docs.github.com/en/code-security/code-scanning/managing-your-code-scanning-configuration/codeql-query-suites
- CodeQL Libraries and Queries Repository — https://github.com/github/codeql
