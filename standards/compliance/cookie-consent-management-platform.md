# Cookie Consent and CMP Implementation

**Date:** 2026-08-17
**Author:** the platform team
**Status:** published

## Symptom

Analytics events fire on page load before the user has interacted
with a consent banner. A visitor from Germany complains; your DPA
audit confirms cookies were written without a lawful basis. Fines
under ePrivacy Directive are separate from GDPR fines.

## Context

The ePrivacy Directive (2002/58/EC, amended 2009) requires prior
informed consent before placing any non-essential cookie or
accessing stored information. GDPR provides the consent standard:
freely given, specific, informed, unambiguous, and withdrawable.
The two laws work together — ePrivacy governs the cookie act,
GDPR governs the personal data that flows from it.

Cookie categories and their lawful basis:

| Category    | Examples                       | Lawful basis       |
|-------------|--------------------------------|--------------------|
| Essential   | Session token, CSRF, auth      | Legitimate interest|
| Functional  | Language preference, theme     | Consent or LI      |
| Analytics   | Plausible, GA4, Amplitude      | Consent required   |
| Marketing   | Meta Pixel, Google Ads         | Consent required   |
| Personaliz. | A/B testing with PII           | Consent required   |

## Consent Requirements (TCF 2.2)

The IAB Europe Transparency & Consent Framework 2.2 defines a
machine-readable format for consent signals that ad vendors and
CMPs can exchange. Key requirements for TCF 2.2 compliance:

1. All purposes must be presented with vendor lists.
2. No pre-ticked boxes; consent is opt-in only.
3. Reject-all must be as easy to invoke as accept-all.
4. The TC String (consent record) must be stored and sent with
   every downstream vendor call.
5. Consent must be refreshed at least every 13 months.

A TC String is a Base64-encoded binary blob. Decode it server-
side to verify consent before firing server-side events:

```ts
import { decode } from '@iabtcf/core';

function hasConsentForPurpose(
  tcString: string,
  purposeId: number,
): boolean {
  const tc = decode(tcString);
  return tc.purposeConsents.has(purposeId);
}
// Purpose 1 = Store/access info; Purpose 7 = Measurement
```

## Consent Before Analytics Firing

The golden rule: **initialize analytics only after consent is
granted**. Never load tracking scripts speculatively.

```ts
type ConsentState = {
  essential: true;
  functional: boolean;
  analytics: boolean;
  marketing: boolean;
};

let consent: ConsentState | null = null;

export function grantConsent(state: ConsentState) {
  consent = state;
  localStorage.setItem('cookie_consent', JSON.stringify(state));
  document.dispatchEvent(
    new CustomEvent('consent:granted', { detail: state }),
  );
}

// In your analytics initializer:
document.addEventListener('consent:granted', (e) => {
  const { analytics } = (e as CustomEvent<ConsentState>).detail;
  if (analytics) initAnalytics();
});
```

## Cloudflare Zaraz and CMP Integration

Zaraz evaluates trigger conditions server-side before injecting
any third-party tool. This prevents client-side script injection
before consent is recorded.

Zaraz consent integration steps:

1. Enable **Consent Management** in the Zaraz dashboard.
2. Map each tool to a consent purpose (Analytics / Marketing).
3. Zaraz reads the `zaraz-consent` cookie on each request and
   suppresses tools whose purpose is not consented.
4. Expose the Zaraz consent API to your CMP button handlers:

```ts
// Accept analytics only
zaraz.consent.setAll(false);
zaraz.consent.set('analytics-purpose-id', true);
zaraz.consent.sendQueuedEvents();

// Full accept
zaraz.consent.acceptAll();

// Full reject (still fires essential-only tools)
zaraz.consent.rejectAll();
```

The `zaraz-consent` cookie is HttpOnly-safe and is managed by
the Zaraz Worker, not by client JS, reducing XSS risk.

## Lightweight CMP Without a Third-Party SaaS

Third-party CMP SDKs (OneTrust, Cookiebot, Didomi) add 50–300 KB
to the page and introduce a consent wall before any JS runs.
A first-party implementation requires:

1. **Banner component** — rendered server-side (SSR/static) so
   it appears before any JS hydration.
2. **Consent store** — `localStorage` for persistence; a secure
   `__consent` cookie for server-side reads (HttpOnly, SameSite).
3. **Script loader** — dynamic `<script>` insertion only after
   the relevant consent category is granted.
4. **Preference center** — allow granular withdrawal at any time.
5. **Audit record** — store consent timestamp, version, and
   categories; log to a server endpoint for compliance evidence.

```ts
// Server-readable consent cookie (set from client after grant)
document.cookie = [
  `__consent=${btoa(JSON.stringify(state))}`,
  'path=/',
  'max-age=31536000',
  'SameSite=Lax',
].join('; ');
```

## Anti-patterns

- Loading Google Tag Manager unconditionally on page load.
- Using a single "I agree to all cookies" checkbox.
- Storing consent only in `localStorage` — invisible to Workers.
- Hiding the "reject all" option behind multiple sub-menus.
- Firing a server-side analytics event before reading the TC
  String from the request cookie.
- Setting the consent cookie as `HttpOnly` — the client cannot
  update it on preference changes.

## Gotchas

- Essential cookies do not require consent, but you must still
  disclose them in the cookie policy.
- The ePrivacy Directive applies to all users visiting from
  the EU, regardless of where your servers are hosted.
- Consent signals must survive a page reload; `sessionStorage`
  is insufficient.
- Soft opt-in ("continued browsing = consent") is no longer
  accepted by most EU DPAs.
- TCF 2.2 `euconsent-v2` cookie must not be set until after
  the user takes an affirmative action.

## Verification

- **E2E test:** load the page in a fresh browser profile; assert
  no `_ga`, `_fbp`, or analytics cookies are set before consent.
- **Consent audit log:** query the `consent_events` table;
  confirm every session has an explicit grant or reject record.
- **Network trace:** in DevTools, filter for analytics domains;
  confirm no requests fire before `consent:granted` event.

## Related

- `compliance/gdpr-cookie-consent-implementation.md`
- `compliance/gdpr-consent-management.md`
- `compliance/gdpr-legitimate-interest-assessment.md`
- `performance/tag-manager-performance.md`

## Source URLs (verified 2026-08-17)

- https://gdpr-info.eu/art-7-gdpr/
- https://iabeurope.eu/tcf-2-2/
- https://developers.cloudflare.com/zaraz/consent-management/
- https://ec.europa.eu/justice/article-29/documentation/opinion-recommendation/files/2012/wp194_en.pdf
- https://edpb.europa.eu/our-work-tools/our-documents/guidelines/guidelines-052020-consent-under-regulation-2016679_en
