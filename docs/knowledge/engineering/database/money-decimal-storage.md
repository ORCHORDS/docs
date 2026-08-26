# money-decimal-storage

**Issue:** Financial amounts stored in the wrong column type produce bugs that are invisible until reconciliation fails: `float` accumulates cents-level drift across millions of rows, Postgres's `money` type changes rendering when the locale changes, and integer-cents schemes break on currencies with zero or three decimal places (JPY, KWD) or on fractional-cent pricing like fuel and FX spreads. Choosing and consistently applying a money representation is a schema decision that is expensive to reverse after the ledger fills.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Choosing the base type

1. **Never float/double for money.** Binary floating point cannot represent 0.10 exactly; `0.1 + 0.2 != 0.3`, and the error compounds through aggregates. This is the one rule with no exceptions in any serious guidance (PostgreSQL docs, Crunchy Data's money guide, Stack Overflow consensus).
2. **Avoid the `money` type in Postgres.** It is locale-dependent for formatting, has a fixed 2-decimal fraction (fails JPY and BHD), and breaks on `lc_monetary` changes; the official docs effectively steer you to `numeric`, `int`, or `bigint` instead.
3. **Default to `numeric`.** `numeric(12,2)` (or `(19,4)` when FX or fractional cents are in play) is the safest general choice: exact arithmetic, arbitrary scale, no overflow. The 2025-era consensus (Crunchy Data, and Otar Shanidze's contrarian defense of numeric over integer dogma) treats numeric as the pragmatic default.
4. **Integer minor units as a deliberate optimization.** `bigint` cents is compact and fast; accept it only with a single-currency or fixed-exponent model, whole-cent arithmetic, and a documented bigint range check (int overflows past ~$21M in cents).
5. **Never mix representations in one schema.** A ledger in cents joining a prices table in `numeric(10,2)` guarantees conversion bugs; pick one internal unit and convert only at boundaries.

## Multi-currency realities

1. **Decimal places vary: 0, 2, 3, and sometimes 4.** JPY/KRW have no minor unit, BHD/KWD use 3, and crypto/FX prices need far more; a fixed 2-decimal assumption is a USD-centric bug.
2. **Store the currency code with every amount.** Columns travel as pairs (`amount`, `currency CHAR(3)` ISO 4217); an amount without a currency is uninterpretable and cannot be correctly converted or rounded later.
3. **Normalization is application logic.** Decide per currency whether inputs arrive in major or minor units and normalize at the edge; a field meaning "cents" in one endpoint and "dollars" in another is a classic double-multiply incident.
4. **Never store computed FX results as if authoritative.** Cross-currency conversions belong in a snapshot table with rate, timestamp, and source so historical amounts can be re-derived and audited.

## Arithmetic, rounding, and constraints

1. **Round once, at the final step.** Compute in full-precision `numeric` and round only when persisting or displaying; rounding per-line then summing diverges from summing then rounding, and finance teams notice.
2. **Pick and document a rounding mode.** Postgres `round()` does half-away-from-zero for numeric; banker's rounding (half-to-even) or half-up must be implemented explicitly if your domain requires it. Chargebee-style billing bugs from mismatched rounding modes are legendary.
3. **Constraint the domain.** `CHECK (amount >= 0)` on quantities/prices, `numeric(12,2)` bounds to reject fat-finger 10^10 entries, and `CHECK (currency ~ '^[A-Z]{3}$')` catch whole classes of bad writes.
4. **Beware int division and avg().** `SUM(amount)/COUNT(*)` on integer cents silently truncates — cast to numeric before dividing; `AVG` on numeric is fine but on integer types it also truncates.
5. **Money equality is scale-sensitive.** `10.0 = 10.00` is true for numeric (value equality), but string comparisons and some ORM equality hooks compare representations; normalize scale before diffing snapshots.

## Designing ledgers around the amounts

1. **Immutable, append-only ledger entries.** Balances are derived (or maintained with constraints), never edited in place; an updateable `balance` row is an audit failure waiting for a concurrent writer.
2. **Double-entry discipline.** Every movement credits one account and debits another in the same transaction, with a `CHECK` that a transfer's legs sum to zero — this catches application bugs at commit time.
3. **Store the display string's ingredients, not the string.** Locale formatting (negative placement, separators) is presentation; the DB keeps numeric + currency and renders per locale at the edge.
4. **Version prices, don't overwrite.** Products with changing prices need a price-history table keyed by time so old orders retain what was actually charged.
5. **Test with hostile values.** 0.005, 999999999999.99, negative refunds, JPY with decimals supplied, and float-typed API inputs should all be part of the schema's test suite before the first real dollar flows.
