# feature-cookbook-versioning

**Issue:** Versioning — SemVer, API versions, schema versions
**Date:** 2026-08-09
**Status:** documented

## Symptom
You release v1.0. You add a feature. The API changes.
Users complain: "My code broke!" You revert. The new
feature is delayed.

## Root cause
**Breaking changes break clients.** Use versioning.

**Source:** SemVer spec:
https://semver.org/

## The "SemVer" concept

SemVer is `MAJOR.MINOR.PATCH`:
- **MAJOR:** Breaking changes
- **MINOR:** New features, backwards compatible
- **PATCH:** Bug fixes, backwards compatible

```json
{
  "version": "2.4.1",
  "major": 2,
  "minor": 4,
  "patch": 1,
}
```

The version is meaningful.

## The "breaking change" pattern

A breaking change is:
- ❌ Remove a function
- ❌ Change a function signature
- ❌ Change a behavior
- ❌ Add a required field
- ❌ Change a status code

A non-breaking change is:
- ✅ Add an optional field
- ✅ Add a new function
- ✅ Add a new endpoint
- ✅ Fix a bug
- ✅ Improve perf

## The "API versioning" pattern

For API versions, choose a strategy:

### URL versioning
```
/api/v1/users
/api/v2/users
```

**Pros:** Simple, visible
**Cons:** Multiple code paths

### Header versioning
```
GET /api/users
Accept: application/vnd.myapi.v2+json
```

**Pros:** Same URL, no path duplication
**Cons:** Hidden

### Query parameter
```
/api/users?version=2
```

**Pros:** Simple
**Cons:** Hidden, can be cached wrong

For most apps, **URL versioning** is the most
maintainable.

## The "API deprecation" pattern

For deprecation:
1. **Announce:** 6 months in advance
2. **Sunset header:** `Sunset: Sat, 01 Aug 2026 00:00:00 GMT`
3. **Warning header:** `Deprecation: true`
4. **Docs:** Mark as deprecated
5. **Migration guide:** How to upgrade
6. **Sunset:** Remove the version

```ts
app.get('/api/v1/users', (req, res) => {
  res.setHeader('Deprecation', 'true');
  res.setHeader('Sunset', 'Sat, 01 Aug 2026 00:00:00 GMT');
  res.setHeader('Link', '</api/v2/users>; rel="successor-version"');
  // ... handle
});
```

The deprecation is communicated.

## The "schema versioning" pattern

For schema changes:
- **Add:** New column (non-breaking)
- **Deprecate:** Mark as deprecated (non-breaking)
- **Remove:** Drop the column (breaking, requires new major)

```sql
-- Add a column (non-breaking)
ALTER TABLE users ADD COLUMN phone TEXT;

-- Deprecate (use new column)
ALTER TABLE users RENAME COLUMN old_column TO new_column;

-- Remove (breaking, next major)
ALTER TABLE users DROP COLUMN old_column;
```

Schema changes are versioned.

## The "DB schema versioning" pattern

For DB migrations:
```
/migrations
  0001_initial.sql
  0002_add_phone.sql
  0003_drop_old.sql  -- Major version bump
```

The migrations are versioned + applied in order.

## The "feature versioning" pattern

For features behind flags:
```ts
if (await isFeatureEnabled('new_billing', user, env)) {
  return newBillingFlow(user, env);
} else {
  return legacyBillingFlow(user, env);
}
```

The new feature is opt-in; the old is opt-out.

## The "contract versioning" pattern

For contracts (API + schema):
```ts
// API contract v1
interface UserV1 {
  id: string;
  email: string;
  displayName: string;
}

// API contract v2
interface UserV2 {
  id: string;
  email: string;
  displayName: string;
  // New optional field
  preferences?: UserPreferences;
}
```

The contract is explicit.

## The "changelog" pattern

For a changelog:
```markdown
# Changelog

## [2.0.0] - 2026-08-09
### Changed
- **BREAKING:** User.email is now required
- **BREAKING:** Removed legacy `getUser` endpoint

### Added
- New `getUserProfile` endpoint
- New `preferences` field on User

## [1.4.2] - 2026-07-20
### Fixed
- Login was failing for users with old passwords

## [1.4.0] - 2026-07-01
### Added
- New `preferences` field on User
```

The changelog is human-readable.

**Source:** Keep a Changelog:
https://keepachangelog.com/

## The "version in code" pattern

For version in code:
```ts
// package.json
{
  "version": "2.4.1"
}

// In the code
import pkg from './package.json';
const VERSION = pkg.version;
```

The version is in the package.

## The "version in API" pattern

For version in API response:
```json
{
  "data": {...},
  "meta": {
    "version": "2.4.1",
    "requestId": "req_abc123"
  }
}
```

The version is in the response.

## The "backwards compat" pattern

For backwards compat:
- **Add, don't remove:** Add new fields; keep old
- **Default to old behavior:** If the client doesn't
  specify, use the old behavior
- **Translate:** Have the new code understand the old
  format

```ts
// New code handles both old and new
function getUser(data: any): User {
  return {
    id: data.id,
    email: data.email,
    displayName: data.displayName ?? data.fullName,  // Old: fullName; New: displayName
  };
}
```

The new code is backwards compatible.

## The "version anti-pattern" anti-patterns

### 1. No version
- **Issue:** Breaking change breaks clients
- **Fix:** Use SemVer

### 2. Major for minor changes
- **Issue:** Users don't upgrade
- **Fix:** Major only for breaking

### 3. No deprecation
- **Issue:** Users surprised by removal
- **Fix:** 6-month deprecation

### 4. No migration guide
- **Issue:** Users don't know how to upgrade
- **Fix:** Provide a guide

### 5. No contract tests
- **Issue:** Breaking change slips in
- **Fix:** Contract tests

## Verification
- **Test:** API versions work
- **Test:** Deprecation headers set
- **Test:** Backwards compat
- **Live:** Old version is monitored
- **Audit:** Quarterly version review

## Gotchas
- **The "no version" anti-pattern.** Use SemVer.
- **The "no deprecation" anti-pattern.** 6 months in
  advance.
- **The "no migration guide" anti-pattern.** Provide
  one.

## Related
- `api-versioning.md`
- `api-versioning-detail.md`
- `feature-cookbook-changelog.md`
- `feature-cookbook-feature-flags.md`
- `database-migration-strategy.md`
- SemVer: https://semver.org/
- Keep a Changelog: https://keepachangelog.com/
