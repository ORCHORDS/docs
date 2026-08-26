# plan-implementation-drift-reconciliation

**Issue:** An original business/architecture plan and the current repository describe materially different operating models, but neither source explicitly records which one supersedes the other.
**Date:** 2026-08-19
**Author:** ORCHORDS
**Status:** verified-live

## Symptom

A historical plan says one thing—for example, one payment rail, data store, integration set, tenancy model, or deployment architecture—while current code and execution documentation implement something different.

Teams often make one of two unsafe assumptions:

- the old plan is automatically authoritative because it came first; or
- the current code is automatically authoritative because it exists now.

Both can be wrong. The plan is evidence of intended business/architecture policy; the repository is evidence of implemented behavior. A contradiction between them is a decision gap until explicitly reconciled.

## Root cause

Long-lived products evolve through implementation constraints, security findings, vendor changes, cost decisions, regulatory changes, and product pivots. If those decisions are not captured as architecture/product decision records, the repository and original plan drift apart without a durable statement of authority.

## Reconciliation method

1. **Preserve the source plan as evidence of original intent.** Do not rewrite history to make it match the current implementation.
2. **Inventory the live repository by capability, not filenames.** Confirm what actually exists in APIs, schemas, workflows, tests, configuration, UI, runbooks, and integrations.
3. **Classify each plan item:** implemented as planned, implemented differently, partially implemented, missing, or owner/external-operation dependent.
4. **Separate missing implementation from policy contradiction.** A missing Azure collector is an implementation gap; “PostgreSQL primary” versus “D1 primary” is an architecture decision gap.
5. **Create an explicit decision issue/record for contradictions.** Present the viable models and the consequences of each; do not silently pick one during unrelated code work.
6. **Avoid production mutation while reconciling documentation.** A decision about payment rails or databases does not authorize changing credentials, moving live data, or enabling providers.
7. **After the owner decision, align all surfaces together:** code, tests, product copy, runbooks, schemas, billing/accounting behavior, recovery procedures, and public documentation.

## Decision record requirements

A useful reconciliation decision states:

- what the original plan required;
- what the current implementation does;
- why the two differ, if known;
- which model is now authoritative;
- which artifacts must change;
- migration/rollback implications;
- security, compliance, cost, data-residency, and operator impacts;
- what is explicitly *not* authorized by the decision alone.

## Examples of high-risk contradictions

### Payment rails

If the plan assigns different payment rails by commercial tier but current implementation routes every tier through one provider, do not infer the answer from whichever integration has more code. Record one canonical commercial policy first, then align checkout, invoices, activation, reconciliation, refunds, and documentation.

### Primary relational data store

If the plan names PostgreSQL but the application is implemented on another relational store, do not casually introduce a second database to "match the plan." Decide whether the new store superseded the plan or whether bounded workloads still require PostgreSQL. If two stores remain, define system-of-record ownership and prohibit ambiguous dual writes.

### Integration promises

A README or plan listing AWS, Azure, GCP, Jira, Slack, and ServiceNow does not prove those collectors exist. Verify concrete connector lifecycle, authentication boundary, collection logic, evidence mapping, tests, and operator runbooks per provider.

## Acceptance checklist

- [ ] Original plan is preserved and cited as historical intent.
- [ ] Current implementation is verified from repository/runtime evidence.
- [ ] Every material mismatch is classified as implementation gap or decision gap.
- [ ] Contradictions have one explicit owner decision instead of silent assumptions.
- [ ] No production data, credential, or provider setting changes occur merely to reconcile documents.
- [ ] After a decision, product copy, APIs, schemas, tests, runbooks, and recovery procedures converge on one model.
- [ ] Deprecated assumptions are marked as superseded rather than deleted from history.

## Anti-patterns

- "The code exists, therefore the business policy changed."
- "The old PDF says PostgreSQL, therefore add PostgreSQL now."
- Updating public pricing copy before payment-state behavior is decided.
- Treating a provider name in documentation as evidence of a working integration.
- Creating dual-write data paths before ownership and recovery semantics are defined.
- Copying confidential financial/corporate plan details into public issue trackers unnecessarily.

## Verification

Re-run the plan-to-repository matrix after each decision or implementation slice. A mismatch is resolved only when the authoritative decision and the implementation/documentation surfaces agree; closing an issue or adding a document alone is not sufficient.
