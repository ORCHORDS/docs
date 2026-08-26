# ios-swift-concurrency-async-await

**Issue:** Using Swift's async/await and structured concurrency for iOS development
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Swift's structured concurrency (introduced in Swift 5.5, iOS 15+) replaces callback-based and DispatchQueue patterns. Misusing actors or task cancellation causes data races, hangs, or crashes.

## Pattern / Solution
**Basic async/await:**
```swift
// Network call
func fetchUser(id: String) async throws -> User {
    let url = URL(string: "https://api.example.com/users/\(id)")!
    let (data, response) = try await URLSession.shared.data(from: url)
    guard (response as? HTTPURLResponse)?.statusCode == 200 else {
        throw APIError.badStatus
    }
    return try JSONDecoder().decode(User.self, from: data)
}

// Call from SwiftUI
.task {
    do {
        user = try await fetchUser(id: userId)
    } catch {
        errorMessage = error.localizedDescription
    }
}
```

**Parallel tasks:**
```swift
async let profile = fetchProfile(id: userId)
async let posts = fetchPosts(userId: userId)
let (p, ps) = try await (profile, posts) // runs concurrently
```

**Actor for shared mutable state:**
```swift
actor Cache {
    private var store: [String: Data] = [:]

    func get(_ key: String) -> Data? { store[key] }
    func set(_ key: String, value: Data) { store[key] = value }
}

let cache = Cache()
await cache.set("user_avatar", value: imageData)
```

**Task cancellation:**
```swift
let task = Task {
    for item in items {
        try Task.checkCancellation()
        await process(item)
    }
}
// Later:
task.cancel()
```

**MainActor for UI updates:**
```swift
@MainActor
func updateUI(with user: User) {
    self.nameLabel.text = user.name
}
```

## Gotchas
- `@MainActor` functions always resume on the main thread; calling them from a background actor hops threads implicitly
- `Task { }` inherits the actor context of the calling scope; `Task.detached { }` does not
- `async let` bindings are cancelled if the enclosing scope throws before they're awaited
- Continuations (`withCheckedContinuation`) must call `resume` exactly once; missing it causes a hang
- Mixing async/await with DispatchQueue can cause priority inversions; prefer `Task` and actors

## Related
- `ios-background-fetch.md`
- `mobile-api-design-patterns.md`
