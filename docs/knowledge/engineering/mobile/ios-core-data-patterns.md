# ios-core-data-patterns

**Issue:** Persisting structured data locally on iOS using Core Data with Swift concurrency
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Fetching Core Data objects on the wrong queue causes crashes; the modern `NSPersistentContainer` API with actor isolation prevents these.

## Pattern / Solution
```swift
import CoreData

// Shared persistent container
class PersistenceController {
  static let shared = PersistenceController()
  let container: NSPersistentContainer

  init() {
    container = NSPersistentContainer(name: "MyApp")
    container.loadPersistentStores { _, error in
      if let error { fatalError("Core Data load failed: \(error)") }
    }
    container.viewContext.automaticallyMergesChangesFromParent = true
  }
}

// Fetch on main context (SwiftUI)
struct ItemListView: View {
  @FetchRequest(sortDescriptors: [SortDescriptor(\.createdAt, order: .reverse)])
  private var items: FetchedResults<Item>

  var body: some View {
    List(items) { item in Text(item.title ?? "") }
  }
}

// Background write
func saveItem(title: String) async {
  let context = PersistenceController.shared.container.newBackgroundContext()
  await context.perform {
    let item = Item(context: context)
    item.title = title
    item.createdAt = Date()
    try? context.save()
  }
}
```

## Gotchas
- Never pass `NSManagedObject` instances between contexts — use object IDs and re-fetch
- `viewContext` is main-thread only; always call `context.perform {}` on background contexts
- `automaticallyMergesChangesFromParent` is essential when writing on background contexts
- Migration must be explicitly configured via `NSMigratePersistentStoresAutomaticallyOption` or the store fails to open after schema changes

## Related
- `ios-swiftui-basics.md`
- `mobile-data-storage.md`
- `android-room-database.md`
