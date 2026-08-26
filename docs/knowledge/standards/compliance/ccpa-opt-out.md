# ccpa-opt-out

**Issue:** California Consumer Privacy Act opt-out implementation
**Date:** 2026-08-09
**Status:** documented

## Symptom
A California resident clicks "Do Not Sell or Share My Personal
Information" on your site. You have 15 business days to honor
the request. You don't know which user it is (they're browsing
as a guest). The implementation is a maze of edge cases.

## Root cause
CCPA grants California residents three core rights:
1. **Right to know** what personal information is collected
2. **Right to delete** personal information
3. **Right to opt out** of sale or sharing

Each has specific implementation requirements that differ from
GDPR.

**Source:** California AG — CCPA:
https://oag.ca.gov/privacy/ccpa

> "A consumer shall have the right, at any time, to direct a
> business that sells or shares personal information about the
> consumer to not sell or share the consumer's personal
> information."

## Fix
Three things to implement:

### 1. Opt-out signal (Global Privacy Control)

CCPA honors the **Global Privacy Control** (GPC) HTTP header
and JavaScript API. If the user's browser sends `Sec-GPC: 1`,
you MUST treat it as an opt-out signal.

```ts
async function handleRequest(request: Request, env: Env): Promise<Response> {
  const gpcSignal = request.headers.get('Sec-GPC') === '1';
  // OR detect via navigator.globalPrivacyControl in client JS

  if (gpcSignal) {
    // Honor the opt-out. Set a cookie that survives the session.
    // (Not a sale-blocker cookie — see "Do Not Sell" cookie below.)
    await markUserOptedOut(env, ipAddress);
  }
  // ...
}
```

**Source:** Global Privacy Control spec:
https://globalprivacycontrol.github.io/gpc-spec/

### 2. "Do Not Sell or Share" link in footer

CCPA requires a clear link in the website footer, with a
mechanism to opt out. Use a page (not just a form submission):

```html
<footer>
  <a >Do Not Sell or Share My Personal Information</a>
</footer>
```

The page must:
- Be reachable in 1 click from the homepage
- Explain what "sale" and "share" mean in your context
- Provide a way to opt out (form, account setting, or both)
- Honor GPC automatically

### 3. Opt-out for known users (account setting)

For logged-in users, add a toggle in account settings:

```ts
// On opt-out
await env.DB.prepare(
  `UPDATE users SET ccpa_opted_out = 1, ccpa_opt_out_at = ?
   WHERE id = ?`
).bind(now, userId).run();

// In all downstream flows (analytics, ad networks, data brokers):
if (user.ccpa_opted_out) {
  // Skip the data-share call
  return;
}
```

## The 15-day rule

You have **15 business days** to act on a verified opt-out. For
GPC signals, the count starts when you detect the signal in your
logs. For account toggles, the count starts when the user clicks
the button.

Track the 15-day deadline in your system and alert when it's
approaching.

## Verification
- **Test:** `test/ccpa.test.ts > GPC header is honored` — passes
- **Test:** `test/ccpa.test.ts > opt-out flag in user record
  disables data sharing` — passes
- **Live:** GPC-enabled browser (Firefox + Privacy Badger) sees
  no third-party trackers, no sale-side data flow

## Gotchas
- **"Sale" and "share" have specific legal definitions** in CCPA.
  A "like" button or a Google Analytics script may count. Consult
  a lawyer for your specific integrations.
- **The 15-day window is strict.** A delay is a violation, even
  if unintentional. Build the 15-day tracker on day 1.
- **CCPA applies to businesses meeting thresholds** ($25M revenue,
  50k consumers, 50% revenue from selling data). Most consumer
  apps meet at least one. Apply it preemptively.
- **CPRA (California Privacy Rights Act)** strengthened CCPA in
  2023. Sensitive personal information has separate rules.
  Apply CPRA-level protection to all data.
- **Children's data (under 16)** has special rules — no sale or
  sharing without opt-in.
- **The GPC signal is opt-out, not opt-in.** A user with GPC
  enabled has implicitly opted out. You don't need a separate
  click.

## Related
- `gdpr-article-17-erasure.md` (companion for EU users)
- `compliance/region-matrix.md` (where CCPA applies)
- CCPA: https://oag.ca.gov/privacy/ccpa
- GPC spec: https://globalprivacycontrol.github.io/gpc-spec/
