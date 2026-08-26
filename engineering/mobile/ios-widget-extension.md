# ios-widget-extension

**Issue:** Building iOS Home Screen and Lock Screen widgets using WidgetKit and SwiftUI
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Widgets are separate extension targets with their own timeline providers and cannot directly read app state at display time.

## Pattern / Solution
Add Widget Extension target: File > New > Target > Widget Extension.

```swift
import WidgetKit
import SwiftUI

// Data model
struct WeatherEntry: TimelineEntry {
  let date: Date
  let temperature: Int
}

// Timeline provider
struct WeatherProvider: TimelineProvider {
  func placeholder(in context: Context) -> WeatherEntry {
    WeatherEntry(date: Date(), temperature: 22)
  }

  func getSnapshot(in context: Context, completion: @escaping (WeatherEntry) -> Void) {
    completion(WeatherEntry(date: Date(), temperature: 22))
  }

  func getTimeline(in context: Context, completion: @escaping (Timeline<WeatherEntry>) -> Void) {
    let entry = WeatherEntry(date: Date(), temperature: fetchTemp())
    // Refresh every hour
    let nextUpdate = Calendar.current.date(byAdding: .hour, value: 1, to: Date())!
    completion(Timeline(entries: [entry], policy: .after(nextUpdate)))
  }
}

// Widget view
struct WeatherWidgetView: View {
  let entry: WeatherEntry
  var body: some View {
    Text("\(entry.temperature)°")
      .font(.system(size: 40, weight: .bold))
      .containerBackground(.fill.tertiary, for: .widget)
  }
}

@main
struct WeatherWidget: Widget {
  var body: some WidgetConfiguration {
    StaticConfiguration(kind: "WeatherWidget", provider: WeatherProvider()) { entry in
      WeatherWidgetView(entry: entry)
    }
    .supportedFamilies([.systemSmall, .systemMedium, .accessoryCircular])
  }
}
```

Share data between app and widget via App Groups:
```swift
let defaults = UserDefaults(suiteName: "group.com.example.myapp")!
defaults.set(temperature, forKey: "currentTemp")
// In widget:
let temp = UserDefaults(suiteName: "group.com.example.myapp")!.integer(forKey: "currentTemp")
```

## Gotchas
- Widgets cannot run arbitrary code on demand — they are snapshots at a point in time
- Network requests in `getTimeline` have a short time budget; cache aggressively
- `containerBackground` modifier is required in iOS 17+ or the widget shows a default background
- Lock screen widgets (`.accessoryCircular`, `.accessoryRectangular`) are rendered in grayscale in standby mode

## Related
- `ios-swiftui-basics.md`
- `ios-app-clips.md`
- `ios-siri-shortcuts.md`
