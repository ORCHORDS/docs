# Parameterized Queries Must Be the Default, Not an Option

**Issue:** A product supports parameterized database queries, but raw query strings and string concatenation remain common escape hatches, so SQL injection risk depends on every developer remembering the safe path every time.

**Date:** 2026-09-04
**Author:** ORCHORDS
**Status:** documented

## The lesson

CISA secure-coding guidance recommends parameterized queries rather than including user input in query strings. The strongest implementation of that principle is to make safe query construction the normal platform path and explicitly govern the exceptional APIs that can bypass it.

## Engineering rule

- Pass untrusted values through bound/parameterized query APIs rather than SQL string construction.
- Standardize data-access helpers and framework patterns that make parameterization the default.
- Inventory raw-query and escape-hatch APIs instead of assuming an ORM automatically eliminates injection risk.
- Use explicit allowlists or another appropriate design for dynamic identifiers that cannot be represented as ordinary bound values.
- Add code-review and automated checks for unsafe query-building patterns.
- Treat any SQL-injection finding as a trigger to review the whole query-construction class, not just the vulnerable line.

## Verification

- Search representative services for raw query strings and concatenation involving request/user-controlled data.
- Exercise adversarial inputs through both standard ORM paths and raw-query escape hatches.
- Confirm the engineering standard and tooling detect prohibited query-construction patterns.

## Official source

- NSA/CISA, Top Ten Cybersecurity Misconfigurations — secure coding and parameterized-query recommendation: https://www.cisa.gov/news-events/cybersecurity-advisories/aa23-278a
