# cloudflare-email-routing

**Issue:** Using Cloudflare Email Routing to forward inbound email without a mail server
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Developers want to receive email at a custom domain without running a mail server, forwarding to Gmail or other providers.

## Pattern / Solution
1. Enable Email Routing in Cloudflare dashboard under the domain > Email > Email Routing.
2. Cloudflare auto-adds required MX records (route1/2/3.mx.cloudflare.net).
3. Create routing rules: specific addresses to destination email, or catch-all to destination.
4. Verify destination email address in Cloudflare (confirmation email sent).
5. For programmatic processing, use Email Workers:
```js
export default {
  async email(message, env, ctx) {
    await message.forward('destination@example.com');
  }
};
```

## Gotchas
- Outbound sending not supported; routing is inbound-only.
- Email Workers can transform, filter, or reject messages before forwarding.
- Maximum message size for routing is 25 MB.
- SPF must include Cloudflare's servers if using custom MAIL FROM.
- Destination addresses limited to 200 per zone.

## Related
- mx-record-configuration, email-forwarding-setup, inbound-email-processing, email-catch-all-patterns
