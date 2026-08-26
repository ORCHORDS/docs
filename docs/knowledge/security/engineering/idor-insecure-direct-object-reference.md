# idor-insecure-direct-object-reference

**Issue:** APIs that expose internal object IDs without authorization checks allow users to access other users' data
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
An API endpoint like `GET /api/invoices/1234` returns the invoice if it exists, without checking if the requesting user owns invoice 1234. An attacker iterates IDs to access all invoices in the system. This is OWASP API Security #1 (Broken Object Level Authorization).

## Pattern / Solution
```javascript
// INSECURE — no ownership check
app.get('/api/invoices/:id', auth, async (req, res) => {
  const invoice = await Invoice.findById(req.params.id);
  res.json(invoice); // anyone can access any invoice
});

// SECURE — always scope queries to the authenticated user
app.get('/api/invoices/:id', auth, async (req, res) => {
  const invoice = await Invoice.findOne({
    _id: req.params.id,
    userId: req.user.id,  // ownership enforced at DB level
  });
  if (!invoice) return res.status(404).json({ error: 'Not found' });
  res.json(invoice);
});

// SECURE — admin users access all, regular users only their own
app.get('/api/invoices/:id', auth, async (req, res) => {
  const query = req.user.role === 'admin'
    ? { _id: req.params.id }
    : { _id: req.params.id, userId: req.user.id };
  const invoice = await Invoice.findOne(query);
  if (!invoice) return res.status(404).json({ error: 'Not found' });
  res.json(invoice);
});
```

## Gotchas
- Return 404 (not 403) when the user lacks access — a 403 confirms the resource exists and enables enumeration.
- Sequential integer IDs are trivially enumerable — consider UUIDs, but don't rely on them for security.
- Don't forget indirect IDOR: `DELETE /api/comments/:id` where the comment references a resource the user shouldn't touch.
- Authorization checks must be applied in every code path — a shared utility function reduces the chance of forgetting.

## Related
- `mass-assignment-prevention.md`
- `owasp-api-top-10-2023.md`
