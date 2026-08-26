# ios-health-kit

**Issue:** Reading and writing health data from the Apple Health app using HealthKit
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
HealthKit requires explicit per-data-type authorization at runtime; silently querying without authorization returns empty results rather than errors.

## Pattern / Solution
Enable HealthKit capability in Xcode and add to `Info.plist`:
```xml
<key>NSHealthShareUsageDescription</key>
<string>Read your step count to personalize recommendations.</string>
<key>NSHealthUpdateUsageDescription</key>
<string>Write workout data to Apple Health.</string>
```

```swift
import HealthKit

class HealthService {
  let store = HKHealthStore()

  func requestAuthorization() async throws {
    guard HKHealthStore.isHealthDataAvailable() else { return }

    let read: Set<HKObjectType> = [
      HKQuantityType(.stepCount),
      HKQuantityType(.heartRate),
    ]
    let write: Set<HKSampleType> = [HKQuantityType(.activeEnergyBurned)]

    try await store.requestAuthorization(toShare: write, read: read)
  }

  func fetchStepsToday() async throws -> Double {
    let type = HKQuantityType(.stepCount)
    let predicate = HKQuery.predicateForSamples(
      withStart: Calendar.current.startOfDay(for: Date()),
      end: Date()
    )
    let stats = try await store.statisticsCollection(
      for: .init(type: type),
      anchorDate: Calendar.current.startOfDay(for: Date()),
      intervalComponents: DateComponents(day: 1)
    )
    return stats.statistics().first?.sumQuantity()?.doubleValue(for: .count()) ?? 0
  }
}
```

## Gotchas
- HealthKit is unavailable on iPad unless the app explicitly supports it; always check `isHealthDataAvailable()`
- Authorization status `sharingDenied` and `notDetermined` are indistinguishable — Apple deliberately hides denial status for privacy
- Background delivery requires setting up `HKObserverQuery` + `enableBackgroundDelivery` and a background fetch capability
- Submitting apps that access HealthKit but don't have a clear health-related purpose leads to App Store rejection

## Related
- `ios-local-notifications.md`
- `mobile-gdpr-mobile.md`
