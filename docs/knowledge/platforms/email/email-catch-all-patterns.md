# email-catch-all-patterns

**Issue:** Configuring and using catch-all email addresses for unmapped addresses
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Applications need to receive email at dynamic or unpredictable addresses (e.g., `ticket+12345@acme.com`) without pre-configuring each one.

## Pattern / Solution
1. **Cloudflare Email Routing:** Set catch-all rule in Email Routing > Routing Rules > Catch-all > Forward to destination.
2. **Google Workspace:** Admin > Apps > Google Workspace > Gmail > Default routing > catch-all.
3. **Email Workers (Cloudflare):** Parse address in worker, route programmatically:
```js
export default {
  async email(message, env, ctx) {
    const [localPart] = message.to.split('@');
    if (localPart.startsWith('ticket+')) {
      /* handle ticket reply */
    } else {
      await message.forward('default@acme.com');
    }
  }
};
```
4. Use `+tag` addressing to embed routing context in the address.

## Gotchas
- Catch-all addresses attract significant spam; rate-limit or filter aggressively.
- Some verification services reject `+tag` addresses; test before requiring them from users.
- Catch-all does not mean you receive mail at subdomains (`@sub.domain.com` needs separate MX).

## Related
- email-forwarding-setup, inbound-email-processing, email-to-ticket-pattern, cloudflare-email-routing
