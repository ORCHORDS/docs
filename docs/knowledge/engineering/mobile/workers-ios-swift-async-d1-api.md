# iOS Swift async/await Workers API Client

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

You are building an iOS app that communicates with a Cloudflare Workers API backed by D1. You want to use Swift's native `async/await` and `URLSession` structured concurrency, strongly-typed `Codable` response models that mirror the D1 schema, and an exponential-backoff retry mechanism for transient network failures.

## Context

- iOS 17+ / Swift 5.10 / Xcode 16
- `URLSession` with `async/await` (no third-party HTTP library)
- `Codable` structs matching the D1 column names via `CodingKeys`
- Cloudflare Workers REST API returning `{ data, error }` envelope
- Retry with jittered exponential backoff for 5xx / timeout errors

---

## API Envelope & Codable Types

```swift
// Sources/Models/ApiEnvelope.swift
import Foundation

struct ApiResponse<T: Decodable>: Decodable {
    let data: T?
    let error: String?
}

struct Article: Codable, Identifiable {
    let id: Int
    let title: String
    let body: String
    let published: Bool
    let createdAt: String

    // Map snake_case JSON keys from D1
    enum CodingKeys: String, CodingKey {
        case id, title, body, published
        case createdAt = "created_at"
    }
}

struct CreateArticleRequest: Encodable {
    let title: String
    let body: String
}
```

---

## URLSession API Client

```swift
// Sources/Network/WorkersClient.swift
import Foundation

enum APIError: LocalizedError {
    case badStatus(Int)
    case serverError(String)
    case decodingError(Error)
    case unknown(Error)

    var errorDescription: String? {
        switch self {
        case .badStatus(let code):   return "HTTP \(code)"
        case .serverError(let msg):  return "Server error: \(msg)"
        case .decodingError(let e):  return "Decoding failed: \(e.localizedDescription)"
        case .unknown(let e):        return e.localizedDescription
        }
    }
}

actor WorkersClient {
    static let shared = WorkersClient()

    private let session: URLSession
    private let baseURL: URL
    private let decoder: JSONDecoder
    private let encoder: JSONEncoder

    init(
        baseURL: URL = URL(string: ProcessInfo.processInfo.environment["API_BASE_URL"] ?? "https://api.example.workers.dev")!,
        session: URLSession = .shared
    ) {
        self.baseURL = baseURL
        self.session = session
        decoder = JSONDecoder()
        encoder = JSONEncoder()
    }

    // MARK: - Generic request with retry

    func request<T: Decodable>(
        path: String,
        method: String = "GET",
        body: (some Encodable)? = nil as String?,
        maxRetries: Int = 3
    ) async throws -> T {
        var attempt = 0
        var lastError: Error = APIError.unknown(URLError(.unknown))

        while attempt <= maxRetries {
            do {
                return try await _request(path: path, method: method, body: body)
            } catch APIError.badStatus(let code) where code >= 500 {
                lastError = APIError.badStatus(code)
            } catch let urlError as URLError
                where urlError.code == .timedOut || urlError.code == .networkConnectionLost {
                lastError = urlError
            } catch {
                throw error  // Non-retriable
            }
            attempt += 1
            if attempt <= maxRetries {
                let delay = backoffDelay(attempt: attempt)
                try await Task.sleep(for: .seconds(delay))
            }
        }
        throw lastError
    }

    private func backoffDelay(attempt: Int) -> Double {
        let base = pow(2.0, Double(attempt)) // 2, 4, 8 seconds
        let jitter = Double.random(in: 0..<1)
        return min(base + jitter, 30)
    }

    private func _request<T: Decodable>(
        path: String,
        method: String,
        body: (some Encodable)?
    ) async throws -> T {
        var req = URLRequest(url: baseURL.appendingPathComponent(path))
        req.httpMethod = method
        req.setValue("application/json", forHTTPHeaderField: "Content-Type")
        req.timeoutInterval = 15

        if let body {
            req.httpBody = try encoder.encode(body)
        }

        let (data, response) = try await session.data(for: req)
        guard let http = response as? HTTPURLResponse else {
            throw APIError.unknown(URLError(.badServerResponse))
        }
        guard (200..<300).contains(http.statusCode) else {
            throw APIError.badStatus(http.statusCode)
        }

        do {
            let envelope = try decoder.decode(ApiResponse<T>.self, from: data)
            if let error = envelope.error {
                throw APIError.serverError(error)
            }
            guard let result = envelope.data else {
                throw APIError.serverError("null data")
            }
            return result
        } catch let err as APIError {
            throw err
        } catch {
            throw APIError.decodingError(error)
        }
    }
}
```

---

## Article Service Layer

```swift
// Sources/Services/ArticleService.swift
import Foundation

final class ArticleService {
    private let client: WorkersClient

    init(client: WorkersClient = .shared) {
        self.client = client
    }

    func fetchAll() async throws -> [Article] {
        try await client.request(path: "articles")
    }

    func create(title: String, body: String) async throws -> Article {
        let req = CreateArticleRequest(title: title, body: body)
        return try await client.request(path: "articles", method: "POST", body: req)
    }

    func delete(id: Int) async throws {
        let _: Article? = try? await client.request(path: "articles/\(id)", method: "DELETE")
    }
}
```

---

## SwiftUI ViewModel with @Observable

```swift
// Sources/ViewModels/ArticlesViewModel.swift
import Foundation
import Observation

@Observable
final class ArticlesViewModel {
    var articles: [Article] = []
    var isLoading = false
    var errorMessage: String?

    private let service: ArticleService

    init(service: ArticleService = ArticleService()) {
        self.service = service
    }

    @MainActor
    func load() async {
        isLoading = true
        errorMessage = nil
        do {
            articles = try await service.fetchAll()
        } catch {
            errorMessage = error.localizedDescription
        }
        isLoading = false
    }

    @MainActor
    func add(title: String, body: String) async {
        do {
            let article = try await service.create(title: title, body: body)
            articles.insert(article, at: 0)
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    @MainActor
    func delete(id: Int) async {
        articles.removeAll { $0.id == id }
        await service.delete(id: id)
    }
}
```

---

## SwiftUI View

```swift
// Sources/Views/ArticlesView.swift
import SwiftUI

struct ArticlesView: View {
    @State private var vm = ArticlesViewModel()
    @State private var showAdd = false

    var body: some View {
        NavigationStack {
            Group {
                if vm.isLoading {
                    ProgressView("Loading…")
                } else if let err = vm.errorMessage {
                    ContentUnavailableView(err, systemImage: "wifi.slash")
                } else {
                    List {
                        ForEach(vm.articles) { article in
                            VStack(alignment: .leading, spacing: 4) {
                                Text(article.title).font(.headline)
                                Text(article.createdAt).font(.caption).foregroundStyle(.secondary)
                            }
                            .swipeActions {
                                Button(role: .destructive) {
                                    Task { await vm.delete(id: article.id) }
                                } label: { Label("Delete", systemImage: "trash") }
                            }
                        }
                    }
                }
            }
            .navigationTitle("Articles")
            .toolbar {
                Button("Add", systemImage: "plus") { showAdd = true }
            }
            .task { await vm.load() }
            .sheet(isPresented: $showAdd) { AddArticleView(vm: vm) }
        }
    }
}
```

---

## Anti-patterns

- Do NOT use `URLSession.dataTask` with completion handlers in new code — `async/await` is safer and avoids retain cycles.
- Do NOT store `URLSession` state outside an `actor` when concurrent requests mutate shared state.
- Do NOT decode directly into your model without the `{ data, error }` envelope — Workers always wraps responses.
- Do NOT swallow all errors in `delete()` silently; at minimum log them for debugging.

## Gotchas

- `ProcessInfo.processInfo.environment` is unavailable in release builds on a real device; use `xcconfig` or Xcode Build Settings instead.
- `@Observable` requires iOS 17+; use `ObservableObject` + `@Published` for iOS 15/16 targets.
- `actor` isolated methods must be `await`ed from non-actor contexts — mark UI updates `@MainActor`.
- D1 integer columns return as JSON numbers; Swift's `Int` decodes them correctly but `String` fields can sometimes hold numeric-looking values — use explicit `CodingKeys`.

---

## Verification

```bash
# Run unit tests (Xcode CLI)
xcodebuild test \
  -scheme MyApp \
  -destination 'platform=iOS Simulator,name=iPhone 16' \
  -testPlan UnitTests

# Curl the Workers endpoint directly
curl -s https://api.example.workers.dev/articles | jq '.data | length'

# Check response envelope
curl -s https://api.example.workers.dev/articles/1 | jq '{data: .data.title, error: .error}'
```

---

## Related

- `documentation/docs/policies/mobile/workers-expo-router-api-routes-d1.md`
- `documentation/docs/policies/mobile/workers-mobile-background-fetch-queues.md`
- `documentation/docs/policies/mobile/workers-mobile-graphql-yoga-d1.md`

## Sources

- https://developers.cloudflare.com/workers/
- https://developers.cloudflare.com/d1/
- https://developer.apple.com/documentation/foundation/urlsession
- https://developer.apple.com/documentation/swift/concurrency
- https://developer.apple.com/documentation/observation
