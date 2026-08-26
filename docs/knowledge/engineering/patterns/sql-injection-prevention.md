# sql-injection-prevention

**Issue:** SQL injection — what it is, how to prevent it
**Date:** 2026-08-09
**Status:** documented

## Symptom
A user submits a search query `' OR 1=1 --`. The SQL becomes
`SELECT * FROM users WHERE name = '' OR 1=1 --'`. The query
returns ALL users (not just the one matching the search). The
attacker has dumped the table.

## Root cause
**SQL injection** is when user-controlled input is concatenated
into a SQL string. The attacker injects SQL syntax to change
the query's meaning.

**Source:** OWASP — SQL Injection:
https://owasp.org/www-community/attacks/SQL_Injection

> "SQL Injection attacks ... consist of insertion or
> 'injection' of a SQL query via the input data from the
> client to the application."

## The classic attack

```ts
// ❌ Vulnerable: string concatenation
async function findUser(name: string, env: Env): Promise<User | null> {
  return env.DB!.prepare(
    `SELECT * FROM users WHERE name = '${name}'`
  ).first<User>();
}

// Attacker calls findUser("' OR 1=1 --")
// Query becomes:
// SELECT * FROM users WHERE name = '' OR 1=1 --'
// Returns ALL users.
```

## Fix: parameterized queries (prepared statements)

```ts
// ✅ Safe: parameterized query
async function findUser(name: string, env: Env): Promise<User | null> {
  return env.DB!.prepare(
    `SELECT * FROM users WHERE name = ?`
  ).bind(name).first<User>();
}
```

The `?` is a **placeholder**. The driver sends the query and
the parameter separately. The driver (and D1) handles escaping.
The user's input is always treated as data, never as SQL syntax.

For multiple parameters:
```ts
env.DB!.prepare(
  `SELECT * FROM users WHERE tenant_id = ? AND email = ?`
).bind(tenantId, email).first<User>();
```

For IN clauses with variable-length lists:
```ts
// D1 supports binding an array for IN
const ids = [1, 2, 3];
const placeholders = ids.map(() => '?').join(',');
env.DB!.prepare(
  `SELECT * FROM users WHERE id IN (${placeholders})`
).bind(...ids).all<User>();
```

For dynamic column names (e.g. sort by user-selected column):
```ts
// ❌ Vulnerable: dynamic column name
const orderBy = req.url.searchParams.get('orderBy');
env.DB!.prepare(
  `SELECT * FROM users ORDER BY ${orderBy}`
).all();

// ✅ Safe: whitelist
const ALLOWED_COLUMNS = new Set(['id', 'name', 'email', 'created_at']);
const orderBy = req.url.searchParams.get('orderBy');
if (!ALLOWED_COLUMNS.has(orderBy)) throw new Error('Invalid column');
env.DB!.prepare(
  `SELECT * FROM users ORDER BY ${orderBy}`
).all();
```

Column names can't be parameterized. **Whitelist them.**

## Additional defenses

### 1. Least privilege
The DB user the app uses should have minimal permissions:
- `SELECT`, `INSERT`, `UPDATE`, `DELETE` on specific tables
- No `DROP`, `ALTER`, `GRANT`
- No access to other databases

For D1, this is implicit (D1 doesn't have multiple users).
For Postgres/MySQL, configure the user carefully.

### 2. Input validation
Even with parameterized queries, validate input:
```ts
function validateUserId(id: string): void {
  if (!/^u_[a-zA-Z0-9]{20,}$/.test(id)) {
    throw new Error('Invalid user ID');
  }
}
```

Reject obviously bad input. This is defense in depth.

### 3. Output encoding
For data that's reflected in HTML, encode it:
```ts
function htmlEncode(s: string): string {
  return s
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}
```

(This is for XSS prevention, not SQLi, but related.)

### 4. WAF
Cloudflare WAF has built-in SQL injection rules. Enable them:
- Security → WAF → Managed Rules → Cloudflare Managed Ruleset
- The "Cloudflare Specials" ruleset includes SQLi detection

## Verification
- **Test:** `test/sql-injection.test.ts > classic OR-1=1
  injection returns no extra rows` — passes
- **Test:** `test/sql-injection.test.ts > UNION SELECT injection
  blocked` — passes
- **Live:** WAF logs show 0 successful SQLi attacks
- **Pen test:** Annual third-party SQLi scan

## Gotchas
- **Stored procedures are not a defense.** They can be
  vulnerable if they concatenate input.
- **ORMs are not a defense.** They can be vulnerable if they
  expose raw query building.
- **The "trust boundary" matters.** Input from the user is
  untrusted. Input from your own DB (after parameterization)
  is trusted. The boundary is the parameterized query.
- **WAF is a layer, not a substitute.** A WAF can be bypassed.
  Parameterized queries are the real defense.
- **D1 (SQLite) has different SQL dialect** than Postgres.
  `||` is string concat in SQLite, `concat()` in Postgres.
  Test on your target engine.

## Related
- `log-injection-prevention.md` (related injection)
- `secrets-encryption-at-rest.md` (PII protection)
- OWASP: https://owasp.org/www-community/attacks/SQL_Injection
- OWASP Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/SQL_Injection_Prevention_Cheat_Sheet.html
