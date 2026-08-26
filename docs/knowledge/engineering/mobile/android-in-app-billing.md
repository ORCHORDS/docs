# android-in-app-billing

**Issue:** Implementing subscriptions and one-time purchases using Google Play Billing Library 7+
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
The legacy AIDL billing interface was deprecated; the Play Billing Library wraps it with a Kotlin-first coroutine API.

## Pattern / Solution
```kotlin
// build.gradle
implementation "com.android.billingclient:billing-ktx:7.0.0"

class BillingManager(private val activity: Activity) : PurchasesUpdatedListener {
  private val billingClient = BillingClient.newBuilder(activity)
    .setListener(this)
    .enablePendingPurchases()
    .build()

  suspend fun connect() {
    val result = billingClient.startConnection(object : BillingClientStateListener {
      override fun onBillingSetupFinished(result: BillingResult) { /* connected */ }
      override fun onBillingServiceDisconnected() { /* retry */ }
    })
  }

  suspend fun queryProducts(): List<ProductDetails> {
    val params = QueryProductDetailsParams.newBuilder()
      .setProductList(listOf(
        QueryProductDetailsParams.Product.newBuilder()
          .setProductId("premium_monthly")
          .setProductType(BillingClient.ProductType.SUBS)
          .build()
      )).build()

    val result = billingClient.queryProductDetails(params)
    return result.productDetailsList ?: emptyList()
  }

  override fun onPurchasesUpdated(result: BillingResult, purchases: List<Purchase>?) {
    if (result.responseCode == BillingResponseCode.OK && purchases != null) {
      purchases.forEach { purchase ->
        if (purchase.purchaseState == Purchase.PurchaseState.PURCHASED) {
          verifyAndAcknowledge(purchase)
        }
      }
    }
  }
}
```

## Gotchas
- Always acknowledge purchases within 3 days or Google Play auto-refunds them
- Verify purchase tokens server-side using the Google Play Developer API before granting entitlements
- `BillingClient` must be reconnected after `onBillingServiceDisconnected` — use exponential backoff
- Subscriptions in `queryPurchasesAsync` only return active ones; check `PurchaseState` carefully

## Related
- `ios-in-app-purchase.md`
- `android-app-bundle.md`
