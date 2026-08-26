# ios-urlsession-patterns

**Issue:** Making authenticated HTTP requests with retry, timeout, and certificate pinning using URLSession
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
`URLSession` default configuration leaks auth tokens via redirects and does not retry on transient failures.

## Pattern / Solution
```swift
import Foundation

// Configured session
let config = URLSessionConfiguration.default
config.timeoutIntervalForRequest = 30
config.waitsForConnectivity = true
config.requestCachePolicy = .reloadIgnoringLocalCacheData

let session = URLSession(configuration: config)

// Authenticated request with async/await
struct APIClient {
  let baseURL = URL(string: "https://api.example.com")!

  func fetch<T: Decodable>(_ path: String, token: String) async throws -> T {
    var request = URLRequest(url: baseURL.appendingPathComponent(path))
    request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
    request.setValue("application/json", forHTTPHeaderField: "Accept")

    let (data, response) = try await session.data(for: request)

    guard let http = response as? HTTPURLResponse, 200..<300 ~= http.statusCode else {
      throw URLError(.badServerResponse)
    }

    return try JSONDecoder().decode(T.self, from: data)
  }
}

// Retry with exponential backoff
func withRetry<T>(attempts: Int = 3, operation: () async throws -> T) async throws -> T {
  var delay: UInt64 = 500_000_000 // 0.5s
  for attempt in 1...attempts {
    do { return try await operation() }
    catch {
      if attempt == attempts { throw error }
      try await Task.sleep(nanoseconds: delay)
      delay *= 2
    }
  }
  fatalError()
}
```

## Gotchas
- `waitsForConnectivity = true` blocks indefinitely if there is no network — set `timeoutIntervalForResource` as a hard cap
- Redirects strip the `Authorization` header by default; implement `urlSession(_:task:willPerformHTTPRedirection:)` to re-add it
- Background URL sessions require a unique identifier and `application(_:handleEventsForBackgroundURLSession:)` in AppDelegate
- Decodable `Date` requires a custom `dateDecodingStrategy` if the API returns ISO-8601 strings

## Related
- `ios-combine-framework.md`
- `certificate-pinning.md`
- `mobile-network-resilience.md`
