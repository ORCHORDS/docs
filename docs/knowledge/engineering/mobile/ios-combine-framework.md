# ios-combine-framework

**Issue:** Composing asynchronous event streams using Apple's Combine reactive framework
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Callback-heavy networking and delegation code becomes deeply nested; Combine provides a declarative pipeline for async data flows.

## Pattern / Solution
```swift
import Combine

class UserViewModel: ObservableObject {
  @Published var users: [User] = []
  @Published var searchQuery = ""
  private var cancellables = Set<AnyCancellable>()

  init() {
    $searchQuery
      .debounce(for: .milliseconds(300), scheduler: DispatchQueue.main)
      .removeDuplicates()
      .filter { !$0.isEmpty }
      .flatMap { [weak self] query -> AnyPublisher<[User], Never> in
        self?.fetchUsers(query: query) ?? Empty().eraseToAnyPublisher()
      }
      .receive(on: DispatchQueue.main)
      .assign(to: &$users)
  }

  private func fetchUsers(query: String) -> AnyPublisher<[User], Never> {
    URLSession.shared
      .dataTaskPublisher(for: URL(string: "https://api.example.com/users?q=\(query)")!)
      .map(\.data)
      .decode(type: [User].self, decoder: JSONDecoder())
      .replaceError(with: [])
      .eraseToAnyPublisher()
  }
}
```

## Gotchas
- Every `.sink` / `.assign` returns an `AnyCancellable` — store it or the subscription cancels immediately
- `assign(to: &$published)` (Xcode 12.4+) automatically manages memory; avoid `.store(in: &cancellables)` with it
- `flatMap` preserves all upstream values concurrently — use `switchToLatest` to cancel previous in-flight requests on new emissions
- Combine is largely superseded by Swift Concurrency (`async/await`) in iOS 15+; prefer `async/await` for new code

## Related
- `ios-swiftui-basics.md`
- `ios-urlsession-patterns.md`
