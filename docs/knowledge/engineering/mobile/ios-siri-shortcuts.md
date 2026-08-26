# ios-siri-shortcuts

**Issue:** Exposing app actions to Siri and Shortcuts.app via App Intents (iOS 16+)
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Legacy `NSUserActivity` / `INIntent` approach requires Intents Extension targets; App Intents in iOS 16+ is entirely in-process and simpler.

## Pattern / Solution
```swift
import AppIntents

// Define an intent
struct OrderCoffeeIntent: AppIntent {
  static let title: LocalizedStringResource = "Order Coffee"
  static let description = IntentDescription("Places your saved coffee order.")

  @Parameter(title: "Drink")
  var drink: String

  func perform() async throws -> some IntentResult & ProvidesDialog {
    try await CoffeeService.shared.order(drink: drink)
    return .result(dialog: "Ordering your \(drink)!")
  }
}

// Donate a shortcut for discoverability
struct MyApp: App {
  var body: some Scene {
    WindowGroup {
      ContentView()
        .task {
          // Donate app shortcut suggestions
          AppShortcutsProvider.updateAppShortcutParameters()
        }
    }
  }
}

// Provide shortcuts to the system
struct MyAppShortcuts: AppShortcutsProvider {
  static var appShortcuts: [AppShortcut] {
    AppShortcut(
      intent: OrderCoffeeIntent(),
      phrases: ["Order coffee with \(.applicationName)", "Get my \(\.$drink) from \(.applicationName)"],
      shortTitle: "Order Coffee",
      systemImageName: "cup.and.saucer"
    )
  }
}
```

## Gotchas
- `AppShortcutsProvider` phrases must contain the application name token `\(.applicationName)` or Siri rejects them
- App Intents run in-process; the app does not need to be open but it must be installed
- Parameters with `@Parameter` require a `DynamicOptionsProvider` if the list of valid values is dynamic
- Testing with Siri requires a real device; the simulator has limited Siri support

## Related
- `ios-widget-extension.md`
- `ios-swiftui-basics.md`
