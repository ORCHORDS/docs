# react-native-push-notifications

**Issue:** Implementing push notifications in React Native across iOS and Android
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Push notifications require separate setup on APNS (iOS) and FCM (Android), plus foreground/background handling. Getting all states (foreground, background, killed) working correctly is error-prone.

## Pattern / Solution
**Expo Notifications (recommended):**
```tsx
import * as Notifications from 'expo-notifications';
import * as Device from 'expo-device';

Notifications.setNotificationHandler({
  handleNotification: async () => ({
    shouldShowAlert: true,
    shouldPlaySound: true,
    shouldSetBadge: true,
  }),
});

async function registerForPush(): Promise<string | null> {
  if (!Device.isDevice) return null; // simulators can't receive push
  const { status: existingStatus } = await Notifications.getPermissionsAsync();
  let finalStatus = existingStatus;
  if (existingStatus !== 'granted') {
    const { status } = await Notifications.requestPermissionsAsync();
    finalStatus = status;
  }
  if (finalStatus !== 'granted') return null;

  const token = await Notifications.getExpoPushTokenAsync({
    projectId: Constants.expoConfig?.extra?.eas?.projectId,
  });
  return token.data;
}

// Listen in component
useEffect(() => {
  const sub = Notifications.addNotificationReceivedListener(n => {
    console.log('Foreground:', n);
  });
  const responseSub = Notifications.addNotificationResponseReceivedListener(r => {
    // App opened via tap — navigate
    router.push(r.notification.request.content.data.url as string);
  });
  return () => { sub.remove(); responseSub.remove(); };
}, []);
```

**Send via Expo Push API:**
```ts
await fetch('https://exp.host/--/api/v2/push/send', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({
    to: expoPushToken,
    title: 'Hello',
    body: 'World',
    data: { url: '/notifications' },
  }),
});
```

## Gotchas
- iOS requires provisioning profiles with push entitlement; `expo build` handles this but bare workflow needs manual setup in Apple Developer portal
- Android 13+ requires `POST_NOTIFICATIONS` runtime permission
- Background notification handlers run in a separate JS context — avoid accessing React state directly
- Notification channels (Android) must be created before sending; Expo creates a default channel automatically
- `getLastNotificationResponseAsync()` handles the "cold start from tap" case that listeners miss
- Expo Push service is a relay; for production volume use FCM/APNS directly via `getDevicePushTokenAsync()`

## Related
- `ios-push-notifications-apns.md`
- `android-firebase-messaging.md`
- `mobile-analytics-patterns.md`
