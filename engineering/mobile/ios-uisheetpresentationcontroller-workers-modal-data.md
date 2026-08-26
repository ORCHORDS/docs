# iOS UISheetPresentationController with Cloudflare Workers Modal Data

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

example project iOS presents contextual detail sheets (post reactions, anonymous profile previews, report dialogs) using `UISheetPresentationController` — the system bottom-sheet API available since iOS 15. These sheets need to load data from Cloudflare Workers as they expand to `.large` detent. Common issues:

- Sheet content is blank on first expansion because the Workers fetch hasn't completed yet
- The sheet bounces to `.medium` when it should hold at the current detent during a background fetch
- Presenting a sheet from a SwiftUI view inside a UIKit navigation stack conflicts with the sheet's `presentingViewController`
- Cancelling the fetch when the sheet is dismissed requires careful `Task` lifecycle management
- The `.large` detent triggers a redundant second fetch when the user drags up from `.medium`

---

## Context

Target: iOS 16+ (uses `UISheetPresentationController.Detent.custom` and `UIScrollView` undimming).

Architecture: SwiftUI views embedded in a UIKit `UINavigationController` using `UIHostingController`. Sheet presentation is handled by a `SheetCoordinator` class owned by the navigation controller. Async data loading via `async/await` with `URLSession`.

Workers API endpoint: `GET /posts/{id}/reactions` — returns reaction summary and recent anonymous reacting users.

---

## Workers Endpoint: Reactions Summary

```typescript
// workers/src/posts/reactions.ts
import { D1Database } from '@cloudflare/workers-types';

interface Env { DB: D1Database; }

export async function handleReactions(
  request: Request,
  env: Env,
  postId: string
): Promise<Response> {
  const [summary, recent] = await Promise.all([
    env.DB.prepare(
      `SELECT reaction_type, COUNT(*) as count
       FROM reactions WHERE post_id = ?1 AND deleted = 0
       GROUP BY reaction_type`
    ).bind(postId).all<{ reaction_type: string; count: number }>(),

    env.DB.prepare(
      `SELECT anon_id, reaction_type, reacted_at
       FROM reactions WHERE post_id = ?1 AND deleted = 0
       ORDER BY reacted_at DESC LIMIT 20`
    ).bind(postId).all<{ anon_id: string; reaction_type: string; reacted_at: string }>(),
  ]);

  return new Response(
    JSON.stringify({
      totals: summary.results,
      recent: recent.results,
    }),
    {
      headers: {
        'Content-Type': 'application/json',
        'Cache-Control': 'public, max-age=10', // short cache — reactions are live
      },
    }
  );
}
```

---

## Swift Data Model and Network Layer

```swift
// Networking/ReactionsClient.swift
import Foundation

struct ReactionSummary: Codable {
    struct Total: Codable {
        let reactionType: String
        let count: Int

        enum CodingKeys: String, CodingKey {
            case reactionType = "reaction_type"
            case count
        }
    }

    struct RecentReaction: Codable {
        let anonId: String
        let reactionType: String
        let reactedAt: String

        enum CodingKeys: String, CodingKey {
            case anonId = "anon_id"
            case reactionType = "reaction_type"
            case reactedAt = "reacted_at"
        }
    }

    let totals: [Total]
    let recent: [RecentReaction]
}

actor ReactionsClient {
    private let session: URLSession
    private let baseURL: URL

    init() {
        let config = URLSessionConfiguration.default
        config.timeoutIntervalForRequest = 8
        config.waitsForConnectivity = true
        self.session = URLSession(configuration: config)
        self.baseURL = URL(string: "https://api.example project.workers.dev")!
    }

    func fetchReactions(postId: String) async throws -> ReactionSummary {
        let url = baseURL.appendingPathComponent("/posts/\(postId)/reactions")
        var request = URLRequest(url: url)
        request.setValue("Bearer \(TokenStore.shared.accessToken ?? "")", forHTTPHeaderField: "Authorization")

        let (data, response) = try await session.data(for: request)

        guard let http = response as? HTTPURLResponse else {
            throw URLError(.badServerResponse)
        }
        guard (200..<300).contains(http.statusCode) else {
            throw WorkersAPIError(statusCode: http.statusCode)
        }

        return try JSONDecoder().decode(ReactionSummary.self, from: data)
    }
}

struct WorkersAPIError: Error {
    let statusCode: Int
}
```

---

## ViewModel with Detent-Aware Loading

The trick: load only a lightweight summary at `.medium` detent. Load the full list when the sheet expands to `.large`. Track which detent triggered each load to avoid double-fetching.

```swift
// Sheets/ReactionsViewModel.swift
import SwiftUI
import Combine

@MainActor
final class ReactionsViewModel: ObservableObject {
    enum LoadState {
        case idle
        case loading
        case loaded(ReactionSummary)
        case failed(Error)
    }

    @Published var loadState: LoadState = .idle
    private(set) var loadedForLarge = false

    private let client = ReactionsClient()
    private var fetchTask: Task<Void, Never>?

    func loadIfNeeded(postId: String, isLargeDetent: Bool) {
        // Already loaded for large — never downgrade
        if loadedForLarge { return }
        // Already loaded for medium and not yet large — don't reload
        if case .loaded = loadState, !isLargeDetent { return }

        fetchTask?.cancel()
        fetchTask = Task {
            loadState = .loading
            do {
                let summary = try await client.fetchReactions(postId: postId)
                guard !Task.isCancelled else { return }
                loadState = .loaded(summary)
                if isLargeDetent { loadedForLarge = true }
            } catch is CancellationError {
                // Sheet dismissed — no UI update needed
            } catch {
                guard !Task.isCancelled else { return }
                loadState = .failed(error)
            }
        }
    }

    func cancelFetch() {
        fetchTask?.cancel()
        fetchTask = nil
    }
}
```

---

## UIKit Sheet Coordinator

```swift
// Sheets/SheetCoordinator.swift
import UIKit
import SwiftUI

final class SheetCoordinator: NSObject, UISheetPresentationControllerDelegate {

    private weak var navigationController: UINavigationController?

    init(navigationController: UINavigationController) {
        self.navigationController = navigationController
    }

    func presentReactionsSheet(postId: String) {
        let viewModel = ReactionsViewModel()

        let hostingController = UIHostingController(
            rootView: ReactionsSheetView(postId: postId, viewModel: viewModel)
        )
        hostingController.modalPresentationStyle = .pageSheet

        if let sheet = hostingController.sheetPresentationController {
            // Medium detent: ~half screen (peek)
            // Large detent: full height
            let mediumDetent = UISheetPresentationController.Detent.medium()
            let largeDetent = UISheetPresentationController.Detent.large()

            sheet.detents = [mediumDetent, largeDetent]
            sheet.prefersGrabberVisible = true
            sheet.selectedDetentIdentifier = .medium
            sheet.prefersScrollingExpandsWhenScrolledToEdge = true

            // Undim the presenting content at medium — feeds remain visible
            sheet.largestUndimmedDetentIdentifier = .medium

            sheet.delegate = self

            // Associate postId for delegate callbacks
            objc_setAssociatedObject(
                hostingController,
                &AssociatedKeys.postId,
                postId,
                .OBJC_ASSOCIATION_RETAIN_NONATOMIC
            )
            objc_setAssociatedObject(
                hostingController,
                &AssociatedKeys.viewModel,
                viewModel,
                .OBJC_ASSOCIATION_RETAIN_NONATOMIC
            )
        }

        // Trigger medium-detent load immediately
        viewModel.loadIfNeeded(postId: postId, isLargeDetent: false)

        navigationController?.present(hostingController, animated: true)
    }

    // MARK: UISheetPresentationControllerDelegate

    func sheetPresentationControllerDidChangeSelectedDetentIdentifier(
        _ sheetPresentationController: UISheetPresentationController
    ) {
        guard
            let vc = sheetPresentationController.presentedViewController,
            let postId = objc_getAssociatedObject(vc, &AssociatedKeys.postId) as? String,
            let viewModel = objc_getAssociatedObject(vc, &AssociatedKeys.viewModel) as? ReactionsViewModel
        else { return }

        let isLarge = sheetPresentationController.selectedDetentIdentifier == .large
        viewModel.loadIfNeeded(postId: postId, isLargeDetent: isLarge)
    }

    func presentationControllerDidDismiss(_ presentationController: UIPresentationController) {
        guard
            let vc = presentationController.presentedViewController,
            let viewModel = objc_getAssociatedObject(vc, &AssociatedKeys.viewModel) as? ReactionsViewModel
        else { return }

        viewModel.cancelFetch()
    }
}

private enum AssociatedKeys {
    static var postId = "postId"
    static var viewModel = "viewModel"
}
```

---

## SwiftUI Sheet Content View

```swift
// Sheets/ReactionsSheetView.swift
import SwiftUI

struct ReactionsSheetView: View {
    let postId: String
    @ObservedObject var viewModel: ReactionsViewModel

    var body: some View {
        NavigationStack {
            Group {
                switch viewModel.loadState {
                case .idle:
                    Color.clear // briefly shown before first load
                case .loading:
                    ProgressView("Loading reactions…")
                        .frame(maxWidth: .infinity, maxHeight: .infinity)
                case .loaded(let summary):
                    ReactionsContentView(summary: summary)
                case .failed(let error):
                    VStack(spacing: 12) {
                        Image(systemName: "exclamationmark.triangle")
                            .font(.largeTitle)
                        Text("Couldn't load reactions")
                            .font(.headline)
                        Text(error.localizedDescription)
                            .font(.caption)
                            .foregroundStyle(.secondary)
                    }
                    .padding()
                }
            }
            .navigationTitle("Reactions")
            .navigationBarTitleDisplayMode(.inline)
        }
    }
}

struct ReactionsContentView: View {
    let summary: ReactionSummary

    var body: some View {
        List {
            Section("Totals") {
                ForEach(summary.totals, id: \.reactionType) { total in
                    HStack {
                        Text(total.reactionType)
                        Spacer()
                        Text("\(total.count)")
                            .foregroundStyle(.secondary)
                    }
                }
            }
            Section("Recent") {
                ForEach(summary.recent, id: \.anonId) { reaction in
                    HStack {
                        Text("Anonymous")
                            .foregroundStyle(.secondary)
                        Spacer()
                        Text(reaction.reactionType)
                    }
                }
            }
        }
    }
}
```

---

## Custom Detent for a "Peek" Height

```swift
// For iOS 16+: a custom detent showing just the reaction totals row
if #available(iOS 16.0, *) {
    let peekDetent = UISheetPresentationController.Detent.custom(
        identifier: UISheetPresentationController.Detent.Identifier("peek")
    ) { context in
        return 120 // fixed height in points
    }
    sheet.detents = [peekDetent, .medium(), .large()]
    sheet.selectedDetentIdentifier = UISheetPresentationController.Detent.Identifier("peek")
}
```

---

## Anti-patterns

- **Fetching data in the sheet's SwiftUI `onAppear`**: `onAppear` fires when the view appears in the hierarchy (at `.medium`), not when the sheet finishes its expand animation. Starting the fetch here is fine for medium, but hooking into detent changes requires the `UISheetPresentationControllerDelegate` — pure SwiftUI has no equivalent.
- **Holding a strong reference to `presentingViewController` in the coordinator**: Leads to retain cycles. Use `weak var navigationController`.
- **Blocking the main thread during JSON decoding**: For large reaction lists, decode on a background actor or use `JSONDecoder` with `Task { await decode() }`. `ReactionsClient` already runs decoding off-main via `URLSession.data(for:)`.
- **Not cancelling the `Task` on dismiss**: If the user swipes down quickly, the fetch continues and calls `@Published` property setters on a deallocated object. Always cancel in `presentationControllerDidDismiss`.
- **Reloading at `.large` even when `.medium` data is sufficient**: If the Worker returns the same 20 recent reactions regardless of detent, don't fetch again. Gate on `loadedForLarge` as shown.

---

## Gotchas

- **`largestUndimmedDetentIdentifier`**: Setting this to `.medium` means the presenting view is NOT dimmed at `.medium`, which gives the feed-behind effect. At `.large` the background dims normally. This must be set before `present()`.
- **SwiftUI `List` in a sheet scrolls against `prefersScrollingExpandsWhenScrolledToEdge`**: When `prefersScrollingExpandsWhenScrolledToEdge = true`, scrolling the list's top while at `.medium` expands the sheet to `.large` before the list scrolls. Users expect this; disable it only if the sheet content has a top scroll action that conflicts.
- **`selectedDetentIdentifier` observable in SwiftUI**: There is no SwiftUI equivalent of the delegate callback for detent changes. A UIKit shim via `UIViewControllerRepresentable` is the only option in pure SwiftUI apps.
- **iOS 15 vs. iOS 16 detent API**: `UISheetPresentationController.Detent.custom` requires iOS 16. Gate with `if #available(iOS 16.0, *)` and fall back to `.medium()` + `.large()` on iOS 15.
- **Adaptive height**: If the sheet's content is short (e.g., a post with no reactions), setting `.medium` detent results in a sheet that's too tall. Use a custom detent sized to `UIView.intrinsicContentSize` for best results.

---

## Verification

```swift
// XCTest: verify fetch cancellation on dismiss
func testFetchCancelledOnDismiss() async {
    let viewModel = ReactionsViewModel()
    let expectation = XCTestExpectation(description: "Fetch cancelled")

    viewModel.loadIfNeeded(postId: "test-post-id", isLargeDetent: false)
    viewModel.cancelFetch()

    try? await Task.sleep(nanoseconds: 500_000_000) // 0.5s

    if case .idle = viewModel.loadState {
        expectation.fulfill()
    } else if case .loading = viewModel.loadState {
        XCTFail("Fetch should have been cancelled")
    }

    await fulfillment(of: [expectation], timeout: 1.0)
}
```

```
# Manual checklist
[ ] Sheet presents at .medium with totals visible within 500ms
[ ] Expanding to .large shows Recent section (if not already loaded)
[ ] Dismissing while loading does not cause a crash or "published on background thread" warning
[ ] Tapping outside the sheet at .medium dismisses it (largestUndimmedDetentIdentifier = .medium)
[ ] Custom peek detent (120pt) shows reaction emoji row without cropping
```

---

## Related

- `ios-app-clips.md`
- `ios-swift-concurrency-async-await.md`
- `ios-swiftui-basics.md`
- `ios-urlsession-patterns.md`
- `ios-app-clip-workers-auth-flow.md`
- `mobile-network-resilience-cloudflare-workers.md`

---

## Sources

- Apple UISheetPresentationController docs: https://developer.apple.com/documentation/uikit/uisheetpresentationcontroller
- WWDC 2021 "Customize and Resize Sheets in UIKit": https://developer.apple.com/videos/play/wwdc2021/10063/
- WWDC 2022 "What's new in UIKit" (custom detents): https://developer.apple.com/videos/play/wwdc2022/10068/
- Swift Concurrency Task cancellation: https://developer.apple.com/documentation/swift/task
- SwiftUI + UIKit hosting: https://developer.apple.com/documentation/swiftui/uihostingcontroller
