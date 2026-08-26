# double-entry-ledger-payments

**Issue:** Payment systems accumulate money-moving features — charges, refunds, subscriptions, wallets, payouts, fees, FX — and eventually nobody can answer "what is this customer's balance and how did it get here?" A mutable balances column per user collapses under scale: lost updates, unexplainable drift, no audit trail, and no way to retroactively explain a dispute. The industry answer, used by Stripe, Shopify, Adyen, and purpose-built databases like TigerBeetle, is an immutable double-entry ledger: every movement of value is an append-only set of debits and credits across accounts, and balances are derived sums. This article covers the design of a ledger that serves as the source of truth for a payments platform.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Core model

1. **Accounts, entries, transactions — three concepts only.** An account is a bucket of value (customer balance, platform revenue, processor clearing, fees, tax payable) with a normal balance side. A transaction is a business event (a 10.00 charge) that posts two or more entries. Each entry is (account, amount, direction debit-or-credit). Martin Fowler's accounting patterns call this journal entry plus postings; the naming varies, the invariant does not.

2. **Every transaction balances to zero.** The sum of debits equals the sum of credits within a single transaction, always. A charge of 10.00 posts debit 10.00 to your processor receivable and credits split across customer prepaid (if wallet-funded), platform revenue, processor fee expense, and tax payable. If a proposed transaction does not balance, it is rejected at write time — this is the ledger's built-in bug detector.

3. **Append-only and immutable.** Entries are never updated or deleted. Corrections are new reversing transactions that mirror the original with a reference to it. This gives you an audit trail by construction and makes balance reconstruction possible at any point in time (sum entries up to timestamp T).

4. **Integer minor units, one currency per account.** Store amounts as bigint minor units (cents); never floats. Each account is single-currency, with FX handled by paired entries across a currency-specific account pair plus an FX gain/loss account. TigerBeetle pushes this discipline further with 128-bit amounts and per-account currency flags to make cross-currency postings unrepresentable.

## Balances and integrity

1. **Balances are cached sums, not truth.** Maintain debits_posted/credits_posted counters on each account (TigerBeetle's model) updated transactionally with the entries, but treat the entry set as the authority. A nightly or continuous job re-sums entries per account and compares to the cached balance; any mismatch pages an engineer. Drift caught early is a bug; drift caught late is an incident.

2. **Enforce available vs pending balances.** Authorizations and holds post pending entries that do not count toward available balance until they capture (or expire as reversals). Two-phase posting (pending then post/void) is how TigerBeetle's transfer model and card-system practice both represent this; a naive ledger without pending states double-spends on holds.

3. **Prevent negative balances where the domain requires it.** Customer spendable accounts should reject transactions that would drive available balance below zero (a constraint check at post time). Internal clearing and expense accounts may legitimately go negative — decide per account category, and encode it as an account flag rather than application logic scattered around.

4. **Idempotency at the transaction level.** Each ledger transaction carries the initiating event id (payment id, webhook event id, payout item id) with a unique constraint, so a redelivered webhook or retried job cannot post the value twice. The ledger is the last line of defense for idempotency even when upstream layers already dedupe.

## Design decisions

1. **Chart of accounts first.** Decide the account taxonomy — per-customer sub-ledger accounts, processor clearing accounts per PSP, revenue by product line, fee expense, tax liability, FX gain/loss, suspense — before writing code. Retro-fitting accounts into a live ledger is a migration project; most pain in homegrown ledgers comes from an ad-hoc chart.

2. **A suspense account is mandatory.** When money arrives or leaves and cannot yet be attributed (processor settlement lump vs individual charges, unknown bank credit), post to suspense and clear it via reconciliation. Resist the temptation to drop unattributed amounts into a misc account where they rot.

3. **Effective-dated entries for a bi-temporal view.** Store both the event time and the posting time. Disputes and audits ask "what did we know when" — a chargebacks officer disputing a June balance needs the ledger as-of the statement date, not as-of today including later corrections.

4. **Event-sourced domain, ledger as projection — or ledger as the event store.** Both architectures work; the mistake is keeping two competing sources of truth that can disagree. If domain events (payment.succeeded) drive ledger postings, the posting process must be exactly-once and monitored for lag; if the ledger is primary, domain state derives from it.

## Operations

1. **Continuous reconciliation is the product.** Match ledger balances daily against PSP reports and bank statements; every unmatched item ages in a queue with an owner. A ledger without reconciliation is just a slower spreadsheet — the value is the guarantee that every cent is explained.

2. **Never fix data in place.** All corrections through reversing/re-posting transactions, even for one-cent drift, and even in production incidents. An UPDATE against ledger rows destroys the audit property that justified building the ledger.

3. **Snapshot balance proofs.** Periodically store per-account balance snapshots with the hash/checkpoint of entries summed; this speeds point-in-time queries and gives tamper-evidence for the entry log.

4. **Plan the migration from mutable balances.** Moving from a balances table to a ledger: freeze writes, snapshot balances as opening entries, then replay or dual-write going forward. Run both systems in parallel with diff alerting for a full billing cycle before cutting reads over.
