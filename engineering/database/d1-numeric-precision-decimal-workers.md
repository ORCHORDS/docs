# D1 Numeric Precision and Decimal Storage in Workers

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case
Financial totals stored in D1 come back with floating-point drift (e.g. `$10.30` becomes `10.299999999999999`), or arithmetic on monetary values produces results that are off by a cent. You need a reliable strategy for storing and computing on decimal values in a Workers + D1 stack.

## Context
D1 inherits SQLite's numeric type affinity model. SQLite has no native `DECIMAL` or `NUMERIC` type that preserves exact decimal arithmetic — all `REAL` values are IEEE 754 double-precision floats, which cannot represent most decimal fractions exactly. The standard remedies are: store cents (integers), store values as `TEXT`, or use integer-scaled arithmetic. Workers also has access to JavaScript's `BigInt` for safe integer arithmetic beyond the 53-bit `Number.MAX_SAFE_INTEGER` limit.

---

## SQLite Type Affinity Recap

SQLite resolves column types to five affinities: `TEXT`, `NUMERIC`, `INTEGER`, `REAL`, `BLOB`. Columns declared `DECIMAL(10,2)` get `NUMERIC` affinity, which stores integers as integers and floats as floats — it does **not** enforce two decimal places or prevent drift.

```sql
-- Both of these use REAL storage — decimal drift is possible
CREATE TABLE prices_bad (
  amount REAL,
  amount2 DECIMAL(10,2)   -- affinity=NUMERIC, not fixed-precision
);

-- Insert and immediately read back:
INSERT INTO prices_bad VALUES (0.1 + 0.2, 0.1 + 0.2);
-- Returns: 0.30000000000000004 in REAL column
--          0.30000000000000004 in DECIMAL column too
```

---

## Strategy 1: Store Minor Units (Integers)

The most robust approach: store all monetary values as integers representing the smallest currency unit (cents for USD, pence for GBP, etc.). No decimal ever touches the database.

```sql
CREATE TABLE invoices (
  id           INTEGER PRIMARY KEY,
  user_id      INTEGER NOT NULL,
  total_cents  INTEGER NOT NULL CHECK(total_cents >= 0),   -- e.g. $12.34 = 1234
  currency     TEXT    NOT NULL DEFAULT 'USD',
  created_at   TEXT    NOT NULL DEFAULT (datetime('now'))
);
```

```typescript
// Helper: convert display amount to storage integer
function toCents(dollars: number): number {
  // Use Math.round to handle float input from user forms
  return Math.round(dollars * 100);
}

// Helper: convert storage integer to display string
function fromCents(cents: number, currency = 'USD'): string {
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency,
    minimumFractionDigits: 2,
  }).format(cents / 100);
}

// Insert
async function createInvoice(
  db: D1Database,
  userId: number,
  amountDollars: number
): Promise<number> {
  const result = await db
    .prepare(
      `INSERT INTO invoices (user_id, total_cents) VALUES (?, ?) RETURNING id`
    )
    .bind(userId, toCents(amountDollars))
    .first<{ id: number }>();

  return result!.id;
}

// Read and display
async function getInvoiceTotal(db: D1Database, id: number): Promise<string> {
  const row = await db
    .prepare(`SELECT total_cents, currency FROM invoices WHERE id = ?`)
    .bind(id)
    .first<{ total_cents: number; currency: string }>();

  if (!row) throw new Error('Not found');
  return fromCents(row.total_cents, row.currency);
}
```

All arithmetic in the database is exact integer arithmetic:

```sql
-- Sum totals: always exact
SELECT SUM(total_cents) FROM invoices WHERE user_id = 42;

-- Apply a 10% discount: use integer division, track remainder separately
SELECT CAST(total_cents * 0.9 AS INTEGER) FROM invoices WHERE id = 1;
-- Note: CAST truncates; use ROUND() if you want nearest cent
SELECT CAST(ROUND(total_cents * 0.9) AS INTEGER) FROM invoices WHERE id = 1;
```

---

## Strategy 2: Store as TEXT (Exact Decimal Strings)

When you receive decimal values from external APIs (e.g. Stripe amounts like `"10.30"`) and must preserve them exactly as-is without conversion:

```sql
CREATE TABLE stripe_charges (
  id       TEXT PRIMARY KEY,
  amount   TEXT NOT NULL,   -- stored as '10.30', never converted to float
  currency TEXT NOT NULL
);
```

```typescript
interface StripeCharge {
  id: string;
  amount: string;  // comes from API as string
  currency: string;
}

async function storeCharge(db: D1Database, charge: StripeCharge): Promise<void> {
  await db
    .prepare(`INSERT INTO stripe_charges (id, amount, currency) VALUES (?, ?, ?)`)
    .bind(charge.id, charge.amount, charge.currency)
    .run();
}

// To aggregate in TypeScript (not SQL) using Decimal.js or similar:
async function totalCharges(db: D1Database): Promise<string> {
  const rows = await db
    .prepare(`SELECT amount FROM stripe_charges`)
    .all<{ amount: string }>();

  // Manual summation without a decimal library:
  let totalCents = 0n;  // BigInt for safe summation
  for (const row of rows.results) {
    const [whole, frac = '00'] = row.amount.split('.');
    const paddedFrac = frac.padEnd(2, '0').slice(0, 2);
    totalCents += BigInt(whole) * 100n + BigInt(paddedFrac);
  }
  const dollars = totalCents / 100n;
  const cents = totalCents % 100n;
  return `${dollars}.${String(cents).padStart(2, '0')}`;
}
```

The downside: SQL `SUM()`, `AVG()`, and comparison operators on TEXT columns do not produce meaningful numeric results. All arithmetic must happen in the Worker.

---

## Strategy 3: Integer-Scaled Arithmetic in SQL

When you need SQL-level aggregation on exact decimals, use a scale factor stored alongside the value:

```sql
CREATE TABLE exchange_rates (
  from_currency TEXT NOT NULL,
  to_currency   TEXT NOT NULL,
  rate_scaled   INTEGER NOT NULL,  -- rate * 1_000_000 (6 decimal places)
  scale         INTEGER NOT NULL DEFAULT 1000000,
  effective_at  TEXT    NOT NULL,
  PRIMARY KEY (from_currency, to_currency, effective_at)
);

-- Rate of 1.234567 stored as 1234567 with scale 1000000
INSERT INTO exchange_rates VALUES ('USD', 'EUR', 1234567, 1000000, datetime('now'));

-- Recover the rate: rate_scaled / CAST(scale AS REAL)
SELECT from_currency, to_currency,
       CAST(rate_scaled AS REAL) / scale AS rate
FROM exchange_rates;
```

---

## BigInt and Large Integer Sums in Workers

SQLite `INTEGER` is a 64-bit signed integer. JavaScript `Number` can only represent integers exactly up to 2^53 − 1 (≈ 9 quadrillion). For large-scale financial systems, read integer columns into `BigInt`:

```typescript
// D1 returns INTEGER columns as JS number by default.
// For very large values, use the raw text interface or cast in SQL.

async function largeCentsSum(db: D1Database): Promise<bigint> {
  // Cast to TEXT in SQL to avoid JS float coercion
  const row = await db
    .prepare(`SELECT CAST(SUM(total_cents) AS TEXT) AS total FROM invoices`)
    .first<{ total: string }>();

  return BigInt(row?.total ?? '0');
}
```

---

## Rounding Modes

SQLite's `ROUND(x, d)` uses "round half away from zero" (symmetric arithmetic rounding), not banker's rounding. For financial work, this is usually acceptable, but document the choice:

```sql
SELECT ROUND(2.5, 0);   -- returns 3.0
SELECT ROUND(3.5, 0);   -- returns 4.0
SELECT ROUND(-2.5, 0);  -- returns -3.0  (away from zero)
```

If you need banker's rounding (round half to even), implement it in TypeScript:

```typescript
function bankersRound(value: number, decimalPlaces: number): number {
  const factor = 10 ** decimalPlaces;
  const shifted = value * factor;
  const floor = Math.floor(shifted);
  const diff = shifted - floor;

  if (diff === 0.5) {
    // Round to even
    return (floor % 2 === 0 ? floor : floor + 1) / factor;
  }
  return Math.round(shifted) / factor;
}
```

---

## Anti-patterns

- **Storing money as `REAL`** — `0.1 + 0.2` in IEEE 754 is `0.30000000000000004`. Even a single `REAL` column for a price field will eventually produce visible drift.
- **Dividing cents by 100 inside SQL then summing** — `SUM(total_cents / 100.0)` introduces float conversion before aggregation. Sum the integers, divide once at display time.
- **Comparing TEXT decimal strings with `<` or `>`** — `'9' > '10'` in text comparison. Always convert to integer or REAL for range queries when storing as TEXT.
- **Using `NUMERIC` affinity and assuming it behaves like PostgreSQL `NUMERIC(p,s)`** — in SQLite, `NUMERIC` just selects a storage class; it does not enforce precision.

---

## Gotchas

- **`CAST(total_cents AS REAL) / 100`** — this is safe for values under 2^53 but introduces a float. Prefer keeping the integer form until the display layer.
- **Negative amounts** — ensure `CHECK(amount >= 0)` is on credit/charge columns and store refunds as separate rows rather than negative values, to avoid signed integer edge cases in `SUM`.
- **D1 Studio display** — D1's web console displays `REAL` values with full float precision, which can surface drift that was always present but hidden in formatted display strings.
- **Multi-currency schema** — always store the currency code alongside the amount. Two `total_cents` columns from different currencies cannot be summed without conversion.

---

## Verification

```sql
-- Confirm no float drift in INTEGER storage
INSERT INTO invoices (user_id, total_cents, currency) VALUES (1, 1030, 'USD');
SELECT total_cents, CAST(total_cents AS REAL) / 100 AS display FROM invoices;
-- total_cents = 1030 (exact), display = 10.3 (float, acceptable for display)

-- Verify SUM is exact
INSERT INTO invoices (user_id, total_cents) VALUES (1, 10), (1, 20), (1, 7);
SELECT SUM(total_cents) FROM invoices WHERE user_id = 1;
-- Must return 1067, not 1066.9999...

-- Check rounding behaviour
SELECT ROUND(10.335, 2), ROUND(10.345, 2);
-- SQLite: 10.34, 10.35 (subject to float representation of 10.335)
```

---

## Related

- `d1-check-constraint-domain-validation-workers.md`
- `d1-column-default-autoincrement-patterns-workers.md`
- `d1-strict-tables-type-enforcement-workers.md`
- `d1-json-column-patterns.md`
- `money-decimal-storage.md`

## Sources

- https://developers.cloudflare.com/d1/
- https://www.sqlite.org/datatype3.html
- https://www.sqlite.org/lang_corefunc.html#round
- https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Global_Objects/BigInt
