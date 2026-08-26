# mobile-analytics-patterns

**Issue:** Implementing analytics tracking in mobile apps correctly and without privacy violations
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Analytics track user behavior to improve the product. Poorly implemented analytics violate privacy regulations (GDPR, CCPA), bloat app size, and generate noisy data from internal users and bots.

## Pattern / Solution
**Segment (unified analytics layer):**
```ts
import { createClient } from '@segment/analytics-react-native';

const analytics = createClient({
  writeKey: SEGMENT_WRITE_KEY,
  trackAppLifecycleEvents: true,
  debug: __DEV__,
});

// Identify user after login
analytics.identify(userId, {
  email: user.email,
  plan: user.plan,
  createdAt: user.createdAt,
});

// Track events
analytics.track('Product Viewed', {
  product_id: product.id,
  name: product.name,
  price: product.price,
  category: product.category,
});

// Screen views
analytics.screen('Checkout', { step: 'payment' });
```

**Event taxonomy (keep consistent):**
```
Object Action:   "Product Viewed", "Order Completed", "Session Started"
Properties:      snake_case, no PII in event name
User traits:     Identify only non-PII or hashed PII
```

**Filter internal traffic:**
```ts
analytics.add({
  plugin: {
    type: 'before',
    execute: event => {
      if (__DEV__ || isEmployee(currentUser)) return null; // drop event
      return event;
    },
  },
});
```

**Consent management:**
```ts
import { useConsent } from './hooks/useConsent';

function App() {
  const { analyticsConsented } = useConsent();
  useEffect(() => {
    if (!analyticsConsented) {
      analytics.disable(); // stop all tracking
    } else {
      analytics.enable();
    }
  }, [analyticsConsented]);
}
```

## Gotchas
- Never log PII (email, phone, full name) as event properties; use hashed user IDs
- App Store and Play Store require privacy nutrition labels listing all data collected — keep analytics SDK list current
- `trackAppLifecycleEvents` fires on simulator/emulator; filter by device type
- Batching events reduces API calls but risks losing events on crash before flush
- iOS ATT prompt is required before using IDFA; most analytics SDKs fall back to anonymous IDs without it

## Related
- `mobile-feature-flags-remote-config.md`
- `mobile-crash-reporting.md`
- `react-native-push-notifications.md`
- `mobile-accessibility-a11y.md`
