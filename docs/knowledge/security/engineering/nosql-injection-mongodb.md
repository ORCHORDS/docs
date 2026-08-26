# nosql-injection-mongodb

**Issue:** MongoDB queries built from user-controlled objects allow operator injection to bypass authentication and exfiltrate data
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Unlike SQL injection (string-based), MongoDB NoSQL injection works via operator injection in JSON/object queries. An attacker sends `{"$gt": ""}` as a password to bypass equality checks, or uses `$where` with JavaScript to exfiltrate data.

## Pattern / Solution
```javascript
// INSECURE — direct object spread allows operator injection
const user = await User.findOne({
  username: req.body.username,
  password: <redacted-secret>  // if body.password = {"$gt": ""} → always matches
});

// SECURE — cast to expected types
const user = await User.findOne({
  username: String(req.body.username),
  password: <redacted-secret>
});

// SECURE — use schema validation (Mongoose)
const UserSchema = new mongoose.Schema({
  username: { type: String, required: true },
  password: { type: String, required: true },
});
// Mongoose coerces values to schema types — objects become "[object Object]"

// SECURE — sanitize with mongo-sanitize
const sanitize = require('mongo-sanitize');
const clean = sanitize(req.body);
const user = await User.findOne(clean);
```
```javascript
// Disable $where operator globally (MongoDB 3.6+)
// mongod.conf
security:
  javascriptEnabled: false
```

## Gotchas
- `express-mongo-sanitize` middleware removes keys starting with `$` from `req.body`, `req.query`, `req.params`.
- Mongoose schema type coercion is not sufficient alone — validate at the API boundary too.
- `$where` and `mapReduce` execute JavaScript server-side — disable `javascriptEnabled` if not needed.
- GraphQL input objects passed directly to MongoDB queries are a common vector.

## Related
- `ldap-injection-prevention.md`
- `sql-injection-deep-dive.md`
- `graphql-introspection-disable.md`
