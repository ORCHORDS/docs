# mobile-gdpr-mobile

**Issue:** Implementing GDPR and mobile privacy requirements (consent, data deletion, data minimization) in mobile apps
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
GDPR fines up to 4% of global revenue apply to apps serving EU users; App Store and Google Play both require privacy labels and enforce data usage declarations.

## Pattern / Solution
**Consent management:**
```ts
import { GoogleMobileAds, AdsConsentStatus } from 'react-native-google-mobile-ads';

async function initializeAds() {
  const consentInfo = await AdsConsentStatus.requestInfoUpdate();

  if (consentInfo.isConsentFormAvailable &&
      consentInfo.status === AdsConsentStatus.REQUIRED) {
    await AdsConsentStatus.showForm();
  }

  await GoogleMobileAds().initialize();
}
```

**Data deletion flow:**
```ts
async function deleteUserAccount(userId: string) {
  // 1. Revoke tokens
  await AuthService.revokeAll(userId);
  // 2. Delete from backend (cascade)
  await api.delete(`/users/${userId}`);
  // 3. Clear local storage
  storage.clearAll();
  await AsyncStorage.clear();
  await Keychain.resetGenericPassword();
  // 4. Reset analytics
  await analytics().resetAnalyticsData();
}
```

**App Store privacy labels (iOS):**
Declare in App Store Connect > App Privacy:
- Data types collected (email, location, usage data)
- Linked to user: yes/no
- Used for tracking: yes/no

**Google Play Data Safety:**
Complete the Data Safety form in Play Console; declared data types must match what the SDK actually collects.

## Gotchas
- Consent must be re-obtained if the consent string changes (e.g., vendor list update); cache the version string
- Analytics SDKs (Firebase, Amplitude) collect data by default even without explicit consent — disable collection until consent is granted
- App Store reviewers check that declared privacy practices match actual SDK behavior — audit your SDKs
- Right to erasure (Art. 17 GDPR) requires actual deletion, not just deactivation; ensure backend cascades

## Related
- `react-native-localization.md`
- `mobile-gdpr-mobile.md`
- `react-native-camera-permissions.md`
- `mobile-analytics-patterns.md`
