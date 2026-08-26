# mass-assignment-prevention

**Issue:** Binding HTTP request body directly to model objects allows attackers to set privileged fields like role or isAdmin
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
ORMs and frameworks that auto-map request parameters to model fields (Rails `update(params)`, Spring `@ModelAttribute`, Mongoose `Object.assign(user, req.body)`) allow attackers to include unexpected fields. Sending `{"name": "Bob", "role": "admin"}` in a profile update could elevate privileges.

## Pattern / Solution
```javascript
// INSECURE — spreads entire request body onto model
app.put('/api/users/:id', auth, async (req, res) => {
  await User.findByIdAndUpdate(req.params.id, req.body); // role, isAdmin, etc. can be set
});

// SECURE — explicit field allowlist
app.put('/api/users/:id', auth, async (req, res) => {
  const allowed = ['name', 'email', 'bio'];
  const update = Object.fromEntries(
    Object.entries(req.body).filter(([k]) => allowed.includes(k))
  );
  await User.findOneAndUpdate({ _id: req.params.id, userId: req.user.id }, update);
});

// SECURE — use a validation schema that strips extra fields
import { z } from 'zod';
const UpdateUserSchema = z.object({
  name: z.string().max(100).optional(),
  email: z.string().email().optional(),
  bio: z.string().max(500).optional(),
}).strict(); // .strict() rejects unknown keys

const update = UpdateUserSchema.parse(req.body);
```
```ruby
# Rails — use Strong Parameters (required since Rails 4)
def user_params
  params.require(:user).permit(:name, :email, :bio)
  # :role, :is_admin are NOT permitted and will be stripped
end
```

## Gotchas
- `.strict()` in Zod rejects extra fields; without it, extra fields are silently stripped — both are safe but strict is more explicit.
- Nested objects also need allowlisting — `user.address` with `user.address.__proto__` is prototype pollution via mass assignment.
- Response serialization should also use an allowlist to prevent accidentally returning sensitive fields.
- Admin endpoints that legitimately set `role` need their own separate schemas with the admin fields permitted.

## Related
- `idor-insecure-direct-object-reference.md`
- `prototype-pollution-prevention.md`
