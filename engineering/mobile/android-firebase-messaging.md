# android-firebase-messaging

**Issue:** Integrating Firebase Cloud Messaging (FCM) for Android push notifications
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
FCM is the standard push delivery mechanism for Android. It also acts as the transport layer for APNs when using Firebase for cross-platform push. Misconfigurations cause tokens to expire silently or notifications not to display.

## Pattern / Solution
**Setup:**
```bash
# Add google-services.json from Firebase console to android/app/
# Add to android/build.gradle:
classpath 'com.google.gms:google-services:4.4.1'

# Add to android/app/build.gradle:
apply plugin: 'com.google.gms.google-services'
implementation 'com.google.firebase:firebase-messaging:24.0.0'
```

**FCM Service (Kotlin):**
```kotlin
class MyFirebaseMessagingService : FirebaseMessagingService() {
    override fun onMessageReceived(message: RemoteMessage) {
        // Handle foreground messages
        message.notification?.let { notification ->
            showLocalNotification(notification.title, notification.body, message.data)
        }
        // message.data is always available (data messages)
    }

    override fun onNewToken(token: String) {
        // Send to backend
        sendRegistrationToServer(token)
    }
}
```

**Get current token:**
```kotlin
FirebaseMessaging.getInstance().token.addOnCompleteListener { task ->
    if (task.isSuccessful) {
        val token = task.result
        sendToBackend(token)
    }
}
```

**Send via FCM HTTP v1:**
```http
POST https://fcm.googleapis.com/v1/projects/my-project/messages:send
Authorization: Bearer <OAuth2 access token>
Content-Type: application/json

{
  "message": {
    "token": "<device_token>",
    "notification": { "title": "Hello", "body": "World" },
    "android": { "priority": "high" },
    "data": { "screen": "notifications" }
  }
}
```

## Gotchas
- FCM tokens can be rotated by the device; always update the backend via `onNewToken`
- Data-only messages (no `notification` key) require the app to build and show the notification manually — they arrive even when the app is in the foreground
- Android 13+ requires `POST_NOTIFICATIONS` permission to be requested at runtime
- `priority: "high"` is needed for doze mode delivery; normal priority messages may be delayed hours
- The legacy FCM HTTP API is deprecated; use the HTTP v1 API with OAuth2 service account tokens
- Notification channels must be created before displaying; the default channel ID is `fcm_fallback_notification_channel`

## Related
- `react-native-push-notifications.md`
- `ios-push-notifications-apns.md`
- `android-play-store-submission.md`
