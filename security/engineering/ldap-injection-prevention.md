# ldap-injection-prevention

**Issue:** Unsanitized user input in LDAP queries enables authentication bypass and directory enumeration
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Applications that construct LDAP search filters from user input are vulnerable to injection. An attacker can supply `*)(uid=*))(|(uid=*` to bypass authentication or enumerate all directory entries. The impact ranges from privilege escalation to complete directory dump.

## Pattern / Solution
```javascript
// INSECURE — direct string interpolation
const filter = `(uid=${username})`; // if username = "*)(uid=*" → all users match

// SECURE — escape special LDAP characters
function escapeLdapValue(value) {
  return value.replace(/[\\*()\x00]/g, (char) => {
    return '\\' + char.charCodeAt(0).toString(16).padStart(2, '0');
  });
}
const filter = `(uid=${escapeLdapValue(username)})`;

// SECURE — use a library
// npm: ldapjs has filter.escape()
const ldap = require('ldapjs');
const safeUsername = ldap.filter.escape(username);
```
```python
# Python — use ldap3 with proper escaping
from ldap3.utils.conv import escape_filter_chars
safe_username = escape_filter_chars(username)
search_filter = f"(uid={safe_username})"
conn.search(base_dn, search_filter)
```
```
LDAP filter special characters requiring escaping:
\ * ( ) NUL and for DN: , + " < > ; = /
```

## Gotchas
- LDAP injection is distinct from SQL injection but equally dangerous in directory-heavy environments.
- Bind DN credentials used for search should be read-only service accounts with minimal permissions.
- Log failed LDAP authentication attempts — brute force and enumeration appear here first.
- Some LDAP servers allow unauthenticated binds by default — disable anonymous bind.

## Related
- `sql-injection-prevention-detail.md`
- `nosql-injection-mongodb.md`
