# browser-permissions-api

**Issue:** Requesting browser permissions at the wrong time leads to high denial rates
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Requesting camera permission on page load before the user understands why results in 80% denials.

## Pattern / Solution
```ts
// Check permission state before requesting
const result = await navigator.permissions.query({ name: 'geolocation' });
// result.state: 'granted' | 'prompt' | 'denied'

if (result.state === 'denied') {
  showSettingsInstructions();
  return;
}

// Request permission contextually (on user gesture)
button.addEventListener('click', async () => {
  try {
    const pos = await new Promise((resolve, reject) =>
      navigator.geolocation.getCurrentPosition(resolve, reject)
    );
    usePosition(pos);
  } catch {
    showDeniedMessage();
  }
});

// Listen for permission changes
result.addEventListener('change', () => {
  console.log('Permission changed to:', result.state);
});
```

## Gotchas
- Permission requests must be triggered by user gesture or they auto-deny
- Permissions query API does not cover all permissions (e.g., clipboard write)
- HTTPS required for most permission-gated APIs

## Related
- `browser-notifications-api.md`
- `browser-clipboard-api.md`
