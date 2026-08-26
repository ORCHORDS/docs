# ios-local-notifications

**Issue:** Scheduling time-based and location-based local notifications on iOS
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
`UILocalNotification` was removed in iOS 10; `UNUserNotificationCenter` (UserNotifications framework) is the current API.

## Pattern / Solution
```swift
import UserNotifications

// Request permission
func requestPermission() async -> Bool {
  let center = UNUserNotificationCenter.current()
  let granted = try? await center.requestAuthorization(options: [.alert, .badge, .sound])
  return granted ?? false
}

// Schedule a notification
func scheduleReminder(title: String, body: String, at date: Date) {
  let content = UNMutableNotificationContent()
  content.title = title
  content.body = body
  content.sound = .default
  content.badge = 1

  let components = Calendar.current.dateComponents([.year, .month, .day, .hour, .minute], from: date)
  let trigger = UNCalendarNotificationTrigger(dateMatching: components, repeats: false)
  let request = UNNotificationRequest(identifier: UUID().uuidString, content: content, trigger: trigger)

  UNUserNotificationCenter.current().add(request)
}

// Cancel pending notifications
UNUserNotificationCenter.current().removePendingNotificationRequests(withIdentifiers: ["my-id"])
UNUserNotificationCenter.current().removeAllPendingNotificationRequests()
```

Handle foreground notifications via delegate:
```swift
extension AppDelegate: UNUserNotificationCenterDelegate {
  func userNotificationCenter(_ center: UNUserNotificationCenter,
    willPresent notification: UNNotification,
    withCompletionHandler completionHandler: @escaping (UNNotificationPresentationOptions) -> Void) {
    completionHandler([.banner, .sound])
  }
}
```

## Gotchas
- Setting `UNUserNotificationCenter.current().delegate` must happen before `applicationDidFinishLaunching`
- iOS limits apps to 64 pending local notifications; older ones are silently dropped
- Badge count must be cleared manually (`UIApplication.shared.applicationIconBadgeNumber = 0`)
- Rich notifications (images, attachments) require a Notification Service Extension to download them

## Related
- `ios-push-notifications-apns.md`
- `ios-swiftui-basics.md`
