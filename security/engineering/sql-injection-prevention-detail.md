# sql-injection-prevention-detail

**Issue:** SQL injection — prevention, types, examples
**Date:** 2026-08-09
**Status:** documented

## Symptom
A user enters their email in a search box. The query
becomes `SELECT * FROM users WHERE email LIKE '%${userInput}%'`.
The user types `' OR '1'='1`. The query becomes
`SELECT * FROM users WHERE email LIKE '%' OR '1'='1%'`. The
user sees all users' data.

## Root cause
**User input is concatenated into the query.** The
attacker injects SQL.

**Source:** OWASP — SQL Injection:
https://owasp.org/www-community/attacks/SQL_Injection

> "SQL injection is a code injection technique that
> exploits security vulnerabilities in an application's
> database layer."

## The "parameterized query" rule

The ONLY safe way to include user input in a SQL query is
parameterized queries:
```ts
// ❌ String concatenation (vulnerable)
const query = `SELECT * FROM users WHERE email = '${userInput}'`;

// ✅ Parameterized query (safe)
const query = `SELECT * FROM users WHERE email = ?`;
await env.DB!.prepare(query).bind(userInput).first();
```

The user input is a parameter; it's never interpreted as
SQL.

## The "D1 binding" pattern

D1's `bind()` is the safe API:
```ts
await env.DB!.prepare(
  `SELECT * FROM users WHERE id = ? AND tenant_id = ?`
).bind(userId, tenantId).first<User>();
```

The values are bound as parameters; no string interpolation.

## The "ORDER BY" gotcha

`ORDER BY` cannot be parameterized (column name is SQL, not
a value). Validate against a whitelist:
```ts
// ❌ Vulnerable
const query = `SELECT * FROM users ORDER BY ${sortBy}`;

// ✅ Safe (whitelist)
const validSorts = ['id', 'email', 'display_name', 'created_at'];
if (!validSorts.includes(sortBy)) {
  return new Response('Invalid sort', { status: 400 });
}
const query = `SELECT * FROM users ORDER BY ${sortBy}`;
```

The column name is validated; it's a known safe value.

## The "LIMIT + OFFSET" gotcha

Same issue with LIMIT + OFFSET. But these are integers:
```ts
// ❌ Vulnerable
const query = `SELECT * FROM users LIMIT ${limit}`;

// ✅ Safe (parse + validate)
const limitNum = Math.min(Math.max(parseInt(limit) || 20, 1), 100);
const query = `SELECT * FROM users LIMIT ?`;
await env.DB!.prepare(query).bind(limitNum).all();
```

The value is parsed as an integer; the integer is bound.

## The "second-order SQL injection" pattern

For user data that's stored and later used in a query:
```ts
// 1. User signs up with display name "Alice'; DROP TABLE users;--"
// 2. The display name is stored (no harm yet)
// 3. Later, a query uses the display name in a LIKE
// ❌ Vulnerable
const query = `SELECT * FROM posts WHERE author = '${user.displayName}'`;

// ✅ Safe (parameterized)
const query = `SELECT * FROM posts WHERE author = ?`;
await env.DB!.prepare(query).bind(user.displayName).all();
```

The data is stored as-is; the query is parameterized. The
attacker can't exploit it.

## The "stored procedure" pattern

For complex queries, use stored procedures:
```sql
CREATE PROCEDURE get_user_by_email(IN email_param TEXT)
BEGIN
  SELECT * FROM users WHERE email = email_param;
END;
```

The procedure is parameterized internally.

## The "ORM" pattern

For most apps, use an ORM (Drizzle, Prisma, Kysely):
```ts
import { eq } from 'drizzle-orm';
import { users } from './schema';

const user = await db.select().from(users).where(eq(users.email, userInput)).limit(1);
```

The ORM generates parameterized queries.

## The "stored XSS + SQL injection" combination

If user input is rendered in HTML AND used in a query:
```ts
// ❌ Both vulnerable
const html = `<p>${userInput}</p>`;  // XSS
const query = `SELECT * FROM users WHERE name = '${userInput}'`;  // SQLi

// ✅ Both safe
const html = `<p>${escapeHtml(userInput)}</p>`;  // XSS-safe
const query = `SELECT * FROM users WHERE name = ?`;
await env.DB!.prepare(query).bind(userInput).first();
```

Both protections are needed.

## The "search" pattern

For search, use FTS5 (parameterized) or a search engine:
```ts
// FTS5 (parameterized)
const query = `SELECT * FROM users_fts WHERE users_fts MATCH ?`;
await env.DB!.prepare(query).bind(searchTerm).all();

// Algolia / Meilisearch
const results = await searchIndex.search(searchTerm, { filters: ... });
```

The search is parameterized.

## The "WAF" pattern

For an extra layer, use a WAF (Cloudflare's WAF):
- Block known SQL injection patterns
- Custom rules for app-specific endpoints
- Rate limit suspicious requests

CF's WAF has built-in rules for SQL injection.

## The "audit" pattern

For audit, log every query with parameters:
```ts
const start = Date.now();
const result = await env.DB!.prepare(query).bind(...params).all();
const duration = Date.now() - start;

logEvent('db.query', 'debug', {
  query: query.replace(/\s+/g, ' ').slice(0, 200),
  duration,
  rowCount: result.results.length,
});
```

The log shows the query + duration + row count. Anomalies
(very long queries, very many rows) are detectable.

## The "SQL injection" anti-patterns

### 1. String concatenation
```ts
// ❌ Always vulnerable
const query = `SELECT * FROM users WHERE email = '${email}'`;
```

### 2. Whitelisting in the wrong place
```ts
// ❌ Doesn't work
if (userInput.includes("'")) throw new Error('Invalid input');
// (There are many other ways to inject SQL)
```

### 3. Stored procedures with concatenation
```ts
// ❌ Stored proc with string concat is still vulnerable
CALL get_user_by_email('${userInput}');
```

### 4. Trusting the column name
```ts
// ❌ Vulnerable
const query = `SELECT ${columns} FROM users WHERE id = ?`;
```

### 5. Using a string builder
```ts
// ❌ SQL builders can still be vulnerable if not used correctly
const qb = knex('users').where('email', userInput);  // OK
const qb2 = knex.raw(`SELECT * FROM users WHERE email = '${userInput}'`);  // NOT OK
```

## Verification
- **Test:** Every query is parameterized
- **Test:** Sort/limit/offset inputs are validated
- **Pen test:** SQL injection fuzzing
- **Audit:** Quarterly review of queries

## Gotchas
- **The "stored XSS enables SQL injection" anti-pattern.**
  The attacker can't see SQL errors; they can't exploit.
  Wait, they can. The error is in the response.
- **The "D1 binding is safe" gotcha.** D1's `bind()` is
  safe. The `raw()` method is not.
- **The "ORM is safe" gotcha.** ORMs are safe for
  parameterized queries. `.raw()` is not.
- **The "WAF is enough" anti-pattern.** A WAF is defense
  in depth, not a substitute for parameterized queries.
  An attacker can bypass the WAF.
- **The "no error in response" anti-pattern.** SQL errors
  can leak schema. Don't show them to the user.

## Related
- `sql-injection-prevention.md`
- `xss-prevention.md`
- `secure-defaults.md`
- `database-index-strategies.md`
- OWASP: https://owasp.org/www-community/attacks/SQL_Injection
- Drizzle: https://orm.drizzle.team/
- Prisma: https://www.prisma.io/
