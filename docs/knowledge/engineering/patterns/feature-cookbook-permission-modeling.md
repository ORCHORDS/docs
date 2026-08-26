# feature-cookbook-permission-modeling

**Issue:** Permissions — roles, ABAC, RBAC, scopes
**Date:** 2026-08-09
**Status:** documented

## Symptom
Your app has "admin" and "user" roles. The customer
wants "moderator" who can ban users but not delete
posts. You add a "moderator" role. The team wants
"content creator" who can write but not publish. You
add another role. You have 10 roles. The code is full
of `if (role === 'admin' || role === 'moderator' || role === 'editor')`.

## Root cause
**Roles are coarse.** For complex permissions, use
RBAC or ABAC.

**Source:** NIST — RBAC:
https://csrc.nist.gov/projects/role-based-access-control

## The "RBAC" pattern

For role-based access control:
- **User:** A person
- **Role:** A set of permissions
- **Permission:** An action on a resource
- **Resource:** The thing being protected

```ts
const ROLES = {
  viewer: ['post:read', 'comment:read'],
  author: ['post:read', 'post:create', 'post:update_own', 'comment:create'],
  editor: ['post:read', 'post:create', 'post:update', 'post:delete', 'comment:create', 'comment:delete'],
  admin: ['*'],  // All
};

function can(user: User, action: string, resource: Resource): boolean {
  const permissions = ROLES[user.role] ?? [];
  if (permissions.includes('*')) return true;
  return permissions.includes(action);
}
```

The role has a set of permissions.

## The "ABAC" pattern

For attribute-based access control:
```ts
function can(user: User, action: string, resource: Resource): boolean {
  // Conditions based on attributes
  if (action === 'post:update' && resource.authorId === user.id) return true;
  if (action === 'post:update' && user.role === 'editor') return true;
  if (action === 'post:read' && !resource.draft) return true;
  if (action === 'post:read' && resource.draft && resource.authorId === user.id) return true;
  return false;
}
```

The decision is based on attributes.

## The "scopes" pattern (OAuth-style)

For OAuth scopes:
```ts
const SCOPES = {
  'post:read': 'Read posts',
  'post:write': 'Write posts',
  'post:delete': 'Delete posts',
  'comment:read': 'Read comments',
  'comment:write': 'Write comments',
  'user:read': 'Read user profile',
  'user:write': 'Update user profile',
};

interface Token {
  scopes: string[];  // e.g. ['post:read', 'post:write']
}

function hasScope(token: Token, scope: string): boolean {
  return token.scopes.includes(scope);
}
```

The token has scopes; the resource checks them.

## The "policy" pattern (OPA-style)

For policy-based:
```rego
# OPA / Cedar policy
package posts

allow {
  input.action == "read"
  input.resource.public == true
}

allow {
  input.action == "read"
  input.user.id == input.resource.author_id
}

allow {
  input.action == "update"
  input.user.id == input.resource.author_id
}

allow {
  input.action == "update"
  input.user.role == "editor"
}
```

The policy is in a separate file.

## The "permission" pattern

For a permission table:
```sql
CREATE TABLE permissions (
  id TEXT PRIMARY KEY,
  name TEXT UNIQUE NOT NULL,  -- e.g. 'post:delete'
  description TEXT
);

CREATE TABLE role_permissions (
  role_id TEXT NOT NULL,
  permission_id TEXT NOT NULL,
  PRIMARY KEY (role_id, permission_id)
);

CREATE TABLE user_roles (
  user_id TEXT NOT NULL,
  role_id TEXT NOT NULL,
  PRIMARY KEY (user_id, role_id)
);
```

The tables are normalized.

## The "ownership" pattern

For ownership, the resource has an `owner_id`:
```ts
async function canUpdatePost(user: User, post: Post): Promise<boolean> {
  // Owner can update
  if (post.authorId === user.id) return true;

  // Editor can update
  if (user.role === 'editor') return true;

  return false;
}
```

The owner has special rights.

## The "tenant isolation" pattern

For multi-tenant:
```ts
async function canReadPost(user: User, post: Post): Promise<boolean> {
  // Different tenant = no access
  if (user.tenantId !== post.tenantId) return false;

  // Owner can read
  if (post.authorId === user.id) return true;

  // Editor can read
  if (user.role === 'editor') return true;

  // Public posts can be read by anyone
  if (post.public) return true;

  return false;
}
```

The tenant boundary is enforced.

## The "time-based" pattern

For time-based permissions:
```ts
async function canEditPost(user: User, post: Post): Promise<boolean> {
  if (post.authorId !== user.id) return false;

  // Only allow editing within 24h
  const hoursSinceCreation = (Date.now() - post.createdAt) / (60 * 60 * 1000);
  if (hoursSinceCreation > 24) return false;

  return true;
}
```

The time window is enforced.

## The "deny" pattern

For deny-by-default:
```ts
async function can(user: User, action: string, resource: Resource): Promise<boolean> {
  // Deny by default
  let allowed = false;

  // Check the role
  if (user.role === 'admin') allowed = true;
  if (user.role === 'editor' && action.startsWith('post:')) allowed = true;
  if (post.authorId === user.id && action === 'post:update') allowed = true;

  return allowed;
}
```

The default is "deny"; the rules allow.

## The "audit" pattern

For an audit log:
```sql
CREATE TABLE access_log (
  id TEXT PRIMARY KEY,
  user_id TEXT NOT NULL,
  action TEXT NOT NULL,
  resource_id TEXT,
  allowed BOOLEAN NOT NULL,
  reason TEXT,
  timestamp TEXT DEFAULT CURRENT_TIMESTAMP
);
```

The access is logged.

## The "permission anti-pattern" anti-patterns

### 1. Coarse roles
- **Issue:** 10 roles × 10 features = combinatorial
  complexity
- **Fix:** Use permissions (RBAC) or attributes (ABAC)

### 2. Role in code
- **Issue:** `if (user.role === 'admin')` is hard to
  audit
- **Fix:** Centralize in a `can()` function

### 3. Allow by default
- **Issue:** New features are accessible to all
- **Fix:** Deny by default

### 4. No ownership check
- **Issue:** User A can edit User B's posts
- **Fix:** Check `resource.authorId === user.id`

### 5. No tenant isolation
- **Issue:** User A in Tenant 1 can read Tenant 2's data
- **Fix:** Always check `user.tenantId === resource.tenantId`

### 6. No audit log
- **Issue:** "Who accessed this?" — no answer
- **Fix:** Log every access

## The "permission testing" pattern

For testing:
```ts
test('user can read own post', () => {
  const user = { id: 'u_1', role: 'viewer' };
  const post = { id: 'p_1', authorId: 'u_1' };
  expect(await can(user, 'post:read', post)).toBe(true);
});

test('user cannot read other user post', () => {
  const user = { id: 'u_1', role: 'viewer' };
  const post = { id: 'p_1', authorId: 'u_2' };
  expect(await can(user, 'post:read', post)).toBe(false);
});
```

The permissions are tested.

## Verification
- **Test:** Each permission is enforced
- **Test:** Deny by default works
- **Test:** Tenant isolation works
- **Live:** Access is logged
- **Audit:** Annual review of permissions

## Gotchas
- **The "coarse roles" anti-pattern.** Use RBAC or ABAC.
- **The "no ownership check" anti-pattern.** Always
  check the owner.
- **The "no tenant isolation" anti-pattern.** Always
  check the tenant.
- **The "no audit log" anti-pattern.** Log every access.

## Related
- `multi-tenant-data-isolation.md`
- `feature-cookbook-auth.md`
- `oauth-best-practices.md`
- `jwt-best-practices.md`
- `audit-log-as-product.md`
- `audit-log-mandatory.md`
- NIST RBAC: https://csrc.nist.gov/projects/role-based-access-control
- OPA: https://www.openpolicyagent.org/
- Cedar: https://www.cedarpolicy.com/
