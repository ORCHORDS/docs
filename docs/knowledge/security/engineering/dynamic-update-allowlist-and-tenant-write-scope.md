# Dynamic update allowlists and tenant write scope

**Category:** Security
**Author:** ORCHORDS
**Primary source:** [OWASP SQL Injection Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/SQL_Injection_Prevention_Cheat_Sheet.html)

## Problem

Parameter binding protects values, not SQL identifiers. A partial-update endpoint that interpolates a requested column name can still be injectable. A prior tenant-scoped read also does not authorize a later mutation unless the mutation itself carries the tenant predicate.

## Practice

- Bind every value through the database driver.
- Represent editable fields with a fixed mapping from public field names to legal SQL identifiers; reject unknown fields before building SQL.
- Build the SET list exclusively from that mapping, never from a caller-provided identifier.
- Include the tenant or owner constraint in every UPDATE and DELETE WHERE clause, even when an earlier query validated access.
- Check affected-row count and return a non-disclosing not-found or conflict result when it is zero.
- Give the workload database identity only the least privileges required for that mutation path.

## Verification

1. Submit unrecognized, quoted, and SQL-looking field names; all must be rejected before a query runs.
2. Attempt to mutate a record from another tenant using a valid record ID; the affected-row count must be zero.
3. Test a valid update, an already-current update, a missing record, and a cross-tenant record so the public contract is intentional.
4. Review generated SQL and confirm only mapped identifiers can appear in it.

## Failure modes

- Binding values while concatenating a column or sort identifier still permits SQL injection.
- An authorization check separated from the mutation becomes vulnerable to logic drift or a missing tenant predicate.
- A generic identifier validator accepts names that are legal SQL but not legal for this endpoint.

## Related

- [OWASP SQL Injection Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/SQL_Injection_Prevention_Cheat_Sheet.html)
