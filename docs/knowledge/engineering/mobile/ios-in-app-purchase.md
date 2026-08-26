# ios-in-app-purchase

**Issue:** Implementing subscriptions and one-time purchases using StoreKit 2 on iOS
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
The original StoreKit API is callback-based and error-prone; StoreKit 2 (iOS 15+) uses async/await and has clearer transaction state management.

## Pattern / Solution
```swift
import StoreKit

class StoreManager: ObservableObject {
  @Published var products: [Product] = []
  @Published var purchasedIds: Set<String> = []

  func loadProducts() async {
    let ids = ["com.example.app.monthly", "com.example.app.yearly"]
    products = (try? await Product.products(for: ids)) ?? []
  }

  func purchase(_ product: Product) async throws {
    let result = try await product.purchase()
    switch result {
    case .success(let verification):
      let transaction = try checkVerified(verification)
      await updatePurchasedProducts()
      await transaction.finish()
    case .userCancelled, .pending:
      break
    @unknown default: break
    }
  }

  func checkVerified<T>(_ result: VerificationResult<T>) throws -> T {
    switch result {
    case .unverified: throw StoreError.failedVerification
    case .verified(let value): return value
    }
  }

  func updatePurchasedProducts() async {
    for await result in Transaction.currentEntitlements {
      if case .verified(let tx) = result, tx.revocationDate == nil {
        purchasedIds.insert(tx.productID)
      }
    }
  }
}
```

## Gotchas
- Always call `transaction.finish()` after processing — unfinished transactions stay in the queue and re-deliver on next launch
- `Transaction.currentEntitlements` only returns active subscriptions and non-consumables
- Sandbox testing requires a sandbox Apple ID; use `Xcode > Settings > Accounts` to add one
- Server-side receipt validation (App Store Server API) is mandatory for fraud detection

## Related
- `android-in-app-billing.md`
- `ios-app-store-submission.md`
