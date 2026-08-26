# sql-injection-deep-dive

**Issue:** SQL injection — patterns, prevention, ORMs
**Date:** 2026-08-09
**Status:** documented

## Symptom
A user submits: `'; DROP TABLE users; --`. The query
becomes: `SELECT * FROM users WHERE name = ''; DROP
TABLE users; --'`. The table is dropped.

## Root cause
**User input is concatenated into SQL.** Use
parameterized queries.

**Source:** OWASP SQLi.

## The "parameterized query" pattern

For D1, use prepared statements:
```ts
// ❌ Bad: string concatenation
const query = `SELECT * FROM users WHERE email = '${userInput}'`;
const user = await env.DB!.prepare(query).first();

// ✅ Good: parameterized
const user = await env.DB!.prepare(
  `SELECT * FROM users WHERE email = ?`
).bind(userInput).first();
```

The user input is bound, not concatenated.

**Source:** D1 prepared statements:
https://developers.cloudflare.com/d1/platform/bindings/

## The "type binding" pattern

For type binding:
```ts
const user = await env.DB!.prepare(
  `SELECT * FROM users WHERE id = ? AND age > ?`
).bind(
  String(userId),  // Explicit type
  Number(age),      // Explicit type
).first();
```

The types are explicit.

## The "name binding" pattern

For named parameters (D1 supports this):
```ts
const user = await env.DB!.prepare(
  `SELECT * FROM users WHERE id = :id AND email = :email`
).bind({ id: userId, email: userEmail }).first();
```

The named parameters are clearer.

## The "no string concat" anti-pattern

For string concat:
```ts
// ❌ Bad
const query = `SELECT * FROM users WHERE email = '${userInput}'`;

// ❌ Bad: even with escaping
const query = `SELECT * FROM users WHERE email = '${userInput.replace(/'/g, "''")}'`;

// ✅ Good: parameterized
const query = `SELECT * FROM users WHERE email = ?`;
const user = await env.DB!.prepare(query).bind(userInput).first();
```

Always use parameterized.

## The "WHERE IN" pattern

For IN clauses:
```ts
// ❌ Bad
const placeholders = ids.map(() => '?').join(',');
const query = `SELECT * FROM users WHERE id IN (${placeholders})`;
const users = await env.DB!.prepare(query).bind(...ids).all();
```

The IN is parameterized.

## The "ORDER BY" anti-pattern

For ORDER BY, the column name can't be a parameter:
```ts
// ❌ Bad: user controls the column
const orderBy = userInput;  // 'email; DROP TABLE users; --'
const query = `SELECT * FROM users ORDER BY ${orderBy}`;

// ✅ Good: allow-list
const ALLOWED_COLUMNS = ['id', 'email', 'displayName', 'createdAt'];
const orderBy = ALLOWED_COLUMNS.includes(userInput) ? userInput : 'id';
const query = `SELECT * FROM users ORDER BY ${orderBy}`;
```

The column is allow-listed.

## The "LIMIT" anti-pattern

For LIMIT, the number can't be a parameter in some
DBs. In D1, it can:
```ts
// ✅ D1 supports parameterized LIMIT
const query = `SELECT * FROM users LIMIT ?`;
const users = await env.DB!.prepare(query).bind(20).all();
```

The LIMIT is parameterized.

## The "ORM" pattern

For an ORM:
- **Drizzle:** Type-safe, lightweight
- **Prisma:** Mature, type-safe
- **Kysely:** Type-safe query builder
- **D1 raw:** Use the prepared statements

```ts
// Drizzle
import { eq } from 'drizzle-orm';

const user = await db.select().from(users).where(eq(users.email, userInput)).get();
```

The ORM handles the binding.

**Source:** Drizzle:
https://orm.drizzle.team/

## The "input validation" pattern

For input validation, allow-list:
```ts
function isValidEmail(s: string): boolean {
  return /^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$/.test(s);
}

if (!isValidEmail(userInput)) {
  throw new Error('Invalid email');
}
```

The input is validated.

## The "stored procedure" pattern (not recommended)

Stored procedures can prevent SQLi, but they have
their own issues. Parameterized queries are the
right answer.

## The "least privilege" pattern

For DB user, the least privilege:
- **App user:** SELECT, INSERT, UPDATE, DELETE
- **No DROP, ALTER, GRANT**

```sql
CREATE USER app_user WITH ENCRYPTED PASSWORD '...';
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO app_user;
REVOKE DROP, ALTER, CREATE ON SCHEMA public FROM app_user;
```

The DB user is restricted.

## The "query monitoring" pattern

For query monitoring:
- **Slow queries:** Log
- **Suspicious queries:** Alert (e.g. `1=1`)
- **Errors:** Log

```ts
const start = Date.now();
try {
  const result = await env.DB!.prepare(query).bind(...).all();
  if (Date.now() - start > 1000) {
    logEvent('db.slow_query', 'warn', { query, durationMs: Date.now() - start });
  }
} catch (err) {
  logEvent('db.error', 'error', { query, error: String(err) });
  throw err;
}
```

The queries are monitored.

## The "SQL injection test" pattern

For testing, use sqlmap (an open-source tool):
```bash
# Test the endpoint
sqlmap -u "https://api.example.com/users?id=u_1" --batch
```

**Source:** sqlmap:
https://sqlmap.org/

## The "SQL injection anti-pattern" anti-patterns

### 1. String concatenation
- **Issue:** SQLi
- **Fix:** Parameterized

### 2. Dynamic column names
- **Issue:** SQLi
- **Fix:** Allow-list

### 3. Dynamic table names
- **Issue:** SQLi
- **Fix:** Allow-list

### 4. No input validation
- **Issue:** Bad data
- **Fix:** Validate

### 5. DB user with admin
- **Issue:** Compromise = total
- **Fix:** Least privilege

## Verification
- **Test:** SQLi attempts are blocked
- **Test:** All queries are parameterized
- **Live:** Query monitoring
- **Audit:** Annual review

## Gotchas
- **The "string concatenation" anti-pattern.** Always
  parameterized.
- **The "dynamic column" anti-pattern.** Allow-list.
- **The "no validation" anti-pattern.** Validate.

## Related
- `sql-injection-prevention.md`
- `sql-injection-prevention-detail.md`
- `feature-cookbook-data-modeling.md`
- `feature-cookbook-search-detail.md`
- OWASP: https://owasp.org/www-community/attacks/SQL_Injection
- Drizzle: https://orm.drizzle.team/
- sqlmap: https://sqlmap.org/
