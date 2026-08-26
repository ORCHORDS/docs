# ios-push-notifications-apns

**Issue:** Configuring Apple Push Notification service (APNs) for iOS apps
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
APNs requires a p8 authentication key or p12 certificate, and the device token obtained at runtime. Getting the full flow right — from entitlement to delivery — has many silent failure points.

## Pattern / Solution
**Register for remote notifications (Swift):**
```swift
import UserNotifications

func application(_ application: UIApplication, didFinishLaunchingWithOptions ...) -> Bool {
    UNUserNotificationCenter.current().delegate = self
    let authOptions: UNAuthorizationOptions = [.alert, .badge, .sound]
    UNUserNotificationCenter.current().requestAuthorization(options: authOptions) { granted, _ in
        guard granted else { return }
        DispatchQueue.main.async { application.registerForRemoteNotifications() }
    }
    return true
}

func application(_ application: UIApplication, didRegisterForRemoteNotificationsWithDeviceToken deviceToken: Data) {
    let token = deviceToken.map { String(format: "%02.2hhx", $0) }.joined()
    // Send `token` to your backend
}
```

**Send via APNs HTTP/2 (server side):**
```http
POST /3/device/<device_token>
Host: api.push.apple.com
Authorization: bearer <JWT signed with p8 key>
apns-topic: com.example.myapp
apns-push-type: alert
Content-Type: application/json

{"aps": {"alert": {"title": "Hello", "body": "World"}, "badge": 1, "sound": "default"}}
```

**JWT for APNs (Node.js):**
```ts
import jwt from 'jsonwebtoken';
const token = jwt.sign({}, p8KeyString, {
  algorithm: 'ES256',
  keyid: KEY_ID,
  issuer: TEAM_ID,
  expiresIn: '1h',
});
```

**Required entitlements:**
- `aps-environment`: `development` or `production` in `.entitlements` file

## Gotchas
- p8 keys never expire and can be used for multiple apps; p12 certificates expire after 1 year and are per-app
- Device tokens can change; always update your backend on every app launch
- APNs delivery is best-effort — no delivery receipt in the basic API; use APNs feedback service or FCM for delivery tracking
- Notification content extensions run in a separate process; they cannot access the app's Keychain items directly
- `apns-push-type` header is required on watchOS and should be set for all platforms
- Background pushes (`content-available: 1`) have a 30-second budget and are throttled by iOS when battery is low

## Related
- `react-native-push-notifications.md`
- `ios-background-fetch.md`
- `android-firebase-messaging.md`
