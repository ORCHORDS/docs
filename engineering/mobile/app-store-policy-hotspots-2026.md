# App Store + Play Store Policy Hotspots 2026

## iOS 17/18 Sensitive Content APIs

Apple's iOS 17 and 18 introduce stricter controls over sensitive content access. Apps must now explicitly request permission for:
- Health data collection
- Motion and fitness tracking
- Contact access
- Camera/microphone usage

```swift
import HealthKit

let healthStore = HKHealthStore()
let readTypes = Set([
    HKObjectType.quantityType(forIdentifier: .heartRate)!,
    HKObjectType.characteristicType(forIdentifier: .biologicalSex)!
])

healthStore.requestAuthorization(toShare: nil, read: readTypes) { success, error in
    if success {
        print("Health permissions granted")
    }
}
```

## Privacy Manifest Requirements

Starting January 2026, all apps must include comprehensive Privacy Manifest files. This includes:
- Data collection purposes
- Third-party data sharing
- Data retention policies
- User consent mechanisms

```xml
<?xml version="1.0" encoding="UTF-8"?>
<PrivacyManifest xmlns="http://www.apple.com/privacy">
    <Version>1.0</Version>
    <DataCategories>
        <Category>Health and Fitness</Category>
        <Category>Other Data</Category>
    </DataCategories>
    <DataUses>
        <Use purpose="Analytics">To improve app performance</Use>
        <Use purpose="Marketing">To send promotional emails</Use>
    </DataUses>
</PrivacyManifest>
```

## Android 14/15 Foreground Service Changes

Android 14 and 15 require foreground service declarations for background tasks. Apps must now:
- Show persistent notification when running in background
- Declare exact alarm permissions
- Implement proper lifecycle management

```kotlin
class BackgroundService : Service() {
    private val CHANNEL_ID = "ForegroundServiceChannel"

    override fun onCreate() {
        createNotificationChannel()
        startForeground(1, createNotification())
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        // Your background work here
        return START_STICKY
    }

    private fun createNotificationChannel() {
        val channel = NotificationChannel(
            CHANNEL_ID,
            "Background Service",
            NotificationManager.IMPORTANCE_LOW
        )
        val manager = getSystemService(NotificationManager::class
