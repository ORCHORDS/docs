# Row Level Security Policy Execution Order

## Scope

This article covers the order in which PostgreSQL row-level security (RLS) policies are evaluated during query planning, the `PERMISSIVE` versus `RESTRICTIVE` semantics, and the practical consequences of multiple policies on the same table. It addresses the canonical pitfalls: policies that combine to deny everything when they should not, policies that interact with `BYPASSRLS` and `FORCE ROW LEVEL SECURITY`, and the interaction between policies and views, joins, and CTEs. It excludes column-level security (which is a different Postgres feature) and the use of RLS as an external audit or authentication layer (which it is not designed to be).

## Workflow or implementation guidance

1. **Enable RLS, then force it for the table owner too.** `ALTER TABLE orders ENABLE ROW LEVEL SECURITY;` enables RLS but exempts the owner by default, which surprises developers running migrations as the owner. `ALTER TABLE orders FORCE ROW LEVEL SECURITY;` removes that exemption and is the right setting in nearly every case.
2. **Use `PERMISSIVE` policies for additive access and `RESTRICTIVE` for global constraints.** A `PERMISSIVE` policy contributes an `OR` term to the access expression; multiple `PERMISSIVE` policies are OR-ed together. A `RESTRICTIVE` policy contributes an `AND` term and is the right tool for a global "this user can never see archived rows" constraint that should apply on top of any permissive policy.
3. **Default-deny by leaving `ENABLE ROW LEVEL SECURITY` without a permissive policy.** New tables with RLS enabled but no policy accessible to the application role will silently return zero rows; the canonical mistake is enabling RLS, forgetting to add the application role to a policy, and shipping the migration. A migration must include the policies that grant the application's access in the same change.
4. **Test the combination, not just the parts.** When more than one policy applies, the resulting predicate is the OR of all `PERMISSIVE` policies AND the AND of all `RESTRICTIVE` policies. Visualise the truth table for the role-by-policy combinations to catch the "every condition fails" cases.
5. **Use `current_setting()` and dedicated GUCs to inject context.** A common pattern is `SET LOCAL app.user_id = '...'` at the start of the request and policies that read `current_setting('app.user_id', true)::uuid`. The policy then references the request context without round-tripping the value through every query. The `, true` argument makes the read return `NULL` instead of erroring when the GUC is unset; the policy must handle that NULL.
6. **Avoid RLS for performance-critical predicates that are also indexed.** RLS predicates are applied as `Filter:` on the chosen plan, not as `Index Cond:`. A policy that filters by `tenant_id = current_setting('app.tenant_id')` after an index scan is correct but may not be cheap; the planner may not push the policy into the index condition. Some workarounds (BYPASSRLS roles for service accounts, partition pruning keyed on tenant_id) can shift the cost.
7. **Cooperate with the connection pooler.** A transaction-mode pooler can reassign a server connection, losing `SET LOCAL` between transactions. Set the GUC at the start of each transaction, or use session-mode pooling for connections that need RLS context, or pass the context as a query parameter.
8. **Bypass RLS for service accounts that legitimately need cross-tenant access.** A service role with `BYPASSRLS` skips all RLS, including restrictive ones; use this sparingly and audit the role membership. `FORCE ROW LEVEL SECURITY` makes the bypass apply even to the table owner.
9. **Combine RLS with grants.** A role without `SELECT` on the table sees zero rows regardless of policy. RLS is row-level, not table-level; the table-level grant must exist first.
10. **Profile the plan.** When RLS makes a query slow, run `EXPLAIN (ANALYZE, BUFFERS)` to see the predicate applied; if the policy is expensive (a function call against a session GUC, a join against another table), consider a denormalised column indexed for the policy.

## Controls

1. **Default-deny audit.** A lint that flags any table with `ENABLE ROW LEVEL SECURITY` but no `PERMISSIVE` policy for any non-superuser role that the application uses.
2. **`FORCE ROW LEVEL SECURITY` policy.** Migration check that RLS-enabled tables in production are also `FORCE`d; a missing `FORCE` is a hole for the owner.
3. **Policy combination documentation.** A diagram or table mapping roles to policies, listing the resulting boolean expression; reviewed when a policy is added or removed.
4. **Plan-time observability.** CI test that runs hot queries as different roles and asserts the row counts are correct and the plan is not degenerate (e.g., index still used).
5. **`BYPASSRLS` membership review.** A periodic audit of which roles have `BYPASSRLS`; alerts on additions.
6. **Pooler interaction note.** A documented expectation that session GUCs set with `SET LOCAL` do not survive across pooler reassignments; the data-access layer re-sets them.

## Validation evidence

1. **Default-deny test.** Run the application's role against the table with no permissive policy; assert zero rows; confirms the safety net is in place.
2. **Permissive OR test.** Add two permissive policies with different predicates; assert a row matching either is visible; confirms OR semantics.
3. **Restrictive AND test.** Add a restrictive policy that excludes archived rows; assert that a row visible under permissive policies is hidden when it is archived; confirms AND semantics.
4. **Owner exemption test.** With RLS enabled but not `FORCE`d, query as the owner and assert all rows are visible; with `FORCE`d, assert the policy is applied to the owner too.
5. **Pooler interaction test.** Under a transaction-mode pooler, set `app.user_id` in one transaction and assert it does not leak into the next transaction's query, evidencing the SET LOCAL discipline.

## Failure modes and correction

1. **All rows hidden after enabling RLS.** Symptom: queries return zero rows; reports break. Correction: add the application's roles to the policies; do not disable RLS in production as a fix.
2. **Owner sees everything while the application sees nothing.** Symptom: a developer's `psql` session (as owner) shows rows; the application does not. Correction: add `FORCE ROW LEVEL SECURITY` to the migration and review owner-vs-non-owner behaviour.
3. **Multiple permissive policies combine to expose rows the model did not intend.** Symptom: a row visible under one permissive policy is visible even when another policy should have hidden it. Correction: add a `RESTRICTIVE` policy that enforces the global constraint.
4. **RLS predicate makes the query slow.** Symptom: an index that should have been used is bypassed because the policy filter applies after the index scan. Correction: denormalise the value the policy checks against into a column with an index, or use `BYPASSRLS` for service accounts that legitimately need fast cross-tenant access.
5. **`SET LOCAL` lost across pooler reassignment.** Symptom: a policy that reads `current_setting('app.user_id')` sees NULL or another user's value. Correction: set the GUC at the start of every transaction; design the request context to be request-scoped, not connection-scoped.
6. **A `RESTRICTIVE` policy inadvertently blocks service accounts.** Symptom: a service account with `BYPASSRLS` does not see rows that it should. Correction: re-check the policy combination; `BYPASSRLS` should override all policies, so the symptom points to a misconfiguration of bypass or to a restrictive policy misread.

## Limitations

1. **RLS is not a substitute for application-level authorization.** Policies are correct as long as the database is the source of truth; if the application makes decisions based on rows that RLS should have hidden but did not (because of a misconfigured policy), RLS did not help.
2. **Policies are SQL fragments evaluated per row.** Complex policies are slow and may be hard to read; consider the model's clarity as well as the performance.
3. **`BYPASSRLS` is a sledgehammer.** Use sparingly and audit.
4. **RLS does not apply to views created `WITH CHECK OPTION` unless the view's defining query and the underlying table's policies agree.** A view that selects `*` does not bypass the underlying policies.
5. **RLS predicates cannot reference session GUCs that are unset in `current_setting()` without an explicit default;** test the unset case, do not assume.

## Canonical sources

- PostgreSQL Documentation, Row Security Policies: https://www.postgresql.org/docs/current/ddl-rowsecurity.html
- PostgreSQL Documentation, CREATE POLICY: https://www.postgresql.org/docs/current/sql-createpolicy.html
- PostgreSQL Documentation, ALTER ROLE (BYPASSRLS): https://www.postgresql.org/docs/current/sql-alterrole.html