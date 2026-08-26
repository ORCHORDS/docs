# ios-swiftui-basics

**Issue:** Building declarative iOS UIs with SwiftUI and managing state correctly
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
UIKit boilerplate for simple screens is verbose; SwiftUI reduces layout code by 70% but has different lifecycle and state rules.

## Pattern / Solution
```swift
import SwiftUI

struct ContentView: View {
  @State private var count = 0          // local mutable state
  @StateObject private var vm = ViewModel() // owned observable object
  @EnvironmentObject var auth: AuthStore    // injected from parent

  var body: some View {
    VStack(spacing: 16) {
      Text("Count: \(count)")
        .font(.title)
      Button("Increment") { count += 1 }
        .buttonStyle(.borderedProminent)
      AsyncImage(url: URL(string: "https://example.com/photo.jpg")) { image in
        image.resizable().scaledToFit()
      } placeholder: {
        ProgressView()
      }
    }
    .padding()
    .task {
      await vm.loadData()
    }
  }
}

// Observable ViewModel (iOS 17+)
@Observable class ViewModel {
  var items: [Item] = []
  func loadData() async {
    items = try! await APIClient.fetchItems()
  }
}
```

## Gotchas
- `@State` objects must be value types (structs/enums); use `@StateObject` for reference types
- `@ObservableObject` + `@Published` is replaced by `@Observable` in iOS 17 — maintain both for backward compat
- SwiftUI previews require `#Preview` macro (Xcode 15+); older `PreviewProvider` still works
- `NavigationStack` (iOS 16+) replaces `NavigationView` — do not mix them in the same hierarchy

## Related
- `ios-combine-framework.md`
- `ios-local-notifications.md`
- `ios-widget-extension.md`
