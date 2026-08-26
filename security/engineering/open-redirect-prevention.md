# open-redirect-prevention

**Issue:** Unvalidated redirect parameters allow attackers to redirect users to malicious sites after authentication
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Login flows often accept a `next` or `redirect_to` parameter so users land on the page they originally requested. Without validation, attackers craft links like `https://app.example.com/login?next=https://evil.com` — the user sees a trusted domain, logs in, then is sent to the attacker's site.

## Pattern / Solution
```javascript
// INSECURE
app.get('/login', (req, res) => {
  // ... authenticate ...
  res.redirect(req.query.next); // arbitrary redirect
});

// SECURE — allowlist of paths or validate same origin
function isSafeRedirect(url) {
  try {
    const parsed = new URL(url, 'https://app.example.com');
    return parsed.origin === 'https://app.example.com';
  } catch {
    return false;
  }
}

app.get('/login', (req, res) => {
  const next = req.query.next;
  const target = isSafeRedirect(next) ? next : '/dashboard';
  res.redirect(target);
});
```

## Gotchas
- `//evil.com` is a protocol-relative URL and redirects to `https://evil.com` — catch it by checking for leading `//`.
- URL encoding tricks: `%2F%2Fevil.com` decodes to `//evil.com` — decode before validation.
- `javascript:` URI in redirect parameters can execute code in some older browsers.
- Allowlisting path prefixes (e.g., `/app/`) is safer than blocklisting.

## Related
- `subdomain-takeover-prevention.md`
- `path-traversal-prevention.md`
