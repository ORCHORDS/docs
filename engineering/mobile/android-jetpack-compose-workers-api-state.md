# Android Jetpack Compose Workers API State Management

Date: 2026-08-23
Author: example.com
Status: production

## Symptom / Use-case

An Android app using Jetpack Compose needs to fetch data from Cloudflare Workers endpoints and
surface it in composables with correct loading, error, and success states. Teams struggle with
where to place the Ktor/OkHttp Workers API client relative to the ViewModel, how to pipe
`StateFlow` into Compose state without recomposition storms, and how to handle Workers-specific
error shapes (rate limits, D1 errors, KV misses) in a type-safe way.

## Context

Jetpack Compose's reactive model pairs naturally with `StateFlow` from Kotlin coroutines, but the
boundary between the network layer (Workers API) and the UI layer needs careful design to avoid
leaking coroutine scopes, causing over-fetching on recomposition, or dropping errors silently.

Workers responses carry non-standard error envelopes (`{ error: string, code: number }`) that
OkHttp's standard error handling ignores unless the client explicitly checks `response.isSuccessful`.

Stack:
- Kotlin 2.x + Jetpack Compose 1.7+
- ViewModel + `viewModelScope`
- Ktor 3.x (or OkHttp 5.x)
- Cloudflare Workers (REST endpoints backed by D1 / KV / R2)
- Hilt for DI

## Workers API Client (Ktor)

```kotlin
// data/remote/WorkersApiClient.kt
package com.example.app.data.remote

import io.ktor.client.*
import io.ktor.client.engine.okhttp.*
import io.ktor.client.plugins.*
import io.ktor.client.plugins.contentnegotiation.*
import io.ktor.client.request.*
import io.ktor.client.statement.*
import io.ktor.http.*
import io.ktor.serialization.kotlinx.json.*
import kotlinx.serialization.Serializable
import kotlinx.serialization.json.Json
import javax.inject.Inject
import javax.inject.Singleton

@Serializable
data class WorkersError(val error: String, val code: Int = 0)

class WorkersApiException(val workerError: WorkersError, httpStatus: Int) :
    Exception("Workers error ${workerError.code} (HTTP $httpStatus): ${workerError.error}")

@Singleton
class WorkersApiClient @Inject constructor() {
    private val json = Json {
        ignoreUnknownKeys = true
        isLenient = true
    }

    val http = HttpClient(OkHttp) {
        install(ContentNegotiation) { json(json) }
        install(HttpTimeout) {
            requestTimeoutMillis = 15_000
            connectTimeoutMillis = 5_000
        }
        defaultRequest {
            url("https://api.example.workers.dev")
            contentType(ContentType.Application.Json)
            accept(ContentType.Application.Json)
        }
    }

    suspend inline fun <reified T> get(
        path: String,
        token: String? = null,
        block: HttpRequestBuilder.() -> Unit = {},
    ): T {
        val response = http.get(path) {
            token?.let { header(HttpHeaders.Authorization, "Bearer $it") }
            block()
        }
        return handleResponse(response)
    }

    suspend inline fun <reified T, reified B> post(
        path: String,
        body: B,
        token: String? = null,
    ): T {
        val response = http.post(path) {
            token?.let { header(HttpHeaders.Authorization, "Bearer $it") }
            setBody(body)
        }
        return handleResponse(response)
    }

    suspend inline fun <reified T> handleResponse(response: HttpResponse): T {
        val text = response.bodyAsText()
        if (!response.status.isSuccess()) {
            val workerErr = runCatching { json.decodeFromString<WorkersError>(text) }
                .getOrElse { WorkersError(error = text, code = response.status.value) }
            throw WorkersApiException(workerErr, response.status.value)
        }
        return json.decodeFromString<T>(text)
    }
}
```

## Sealed UI State

```kotlin
// ui/state/UiState.kt
package com.example.app.ui.state

sealed interface UiState<out T> {
    data object Idle : UiState<Nothing>
    data object Loading : UiState<Nothing>
    data class Success<T>(val data: T) : UiState<T>
    data class Error(
        val message: String,
        val workerCode: Int = 0,
        val retryable: Boolean = true,
    ) : UiState<Nothing>
}

fun <T> UiState<T>.dataOrNull(): T? = (this as? UiState.Success)?.data
```

## ViewModel with StateFlow

```kotlin
// ui/viewmodel/ProductsViewModel.kt
package com.example.app.ui.viewmodel

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.example.app.data.remote.WorkersApiClient
import com.example.app.data.remote.WorkersApiException
import com.example.app.ui.state.UiState
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import kotlinx.serialization.Serializable
import javax.inject.Inject

@Serializable
data class Product(val id: String, val name: String, val price: Double)

@Serializable
data class ProductsResponse(val products: List<Product>, val cursor: String? = null)

@HiltViewModel
class ProductsViewModel @Inject constructor(
    private val api: WorkersApiClient,
) : ViewModel() {

    private val _state = MutableStateFlow<UiState<List<Product>>>(UiState.Idle)
    val state: StateFlow<UiState<List<Product>>> = _state.asStateFlow()

    private var cursor: String? = null
    private val allProducts = mutableListOf<Product>()

    fun load(token: String) {
        if (_state.value is UiState.Loading) return
        _state.value = UiState.Loading

        viewModelScope.launch {
            runCatching {
                api.get<ProductsResponse>("/products") {
                    cursor?.let { parameter("cursor", it) }
                    header("Authorization", "Bearer $token")
                }
            }.onSuccess { resp ->
                allProducts.addAll(resp.products)
                cursor = resp.cursor
                _state.value = UiState.Success(allProducts.toList())
            }.onFailure { err ->
                val (msg, code) = when (err) {
                    is WorkersApiException -> err.workerError.error to err.workerError.code
                    else -> (err.message ?: "Unknown error") to 0
                }
                _state.value = UiState.Error(
                    message = msg,
                    workerCode = code,
                    retryable = code != 403 && code != 404,
                )
            }
        }
    }

    fun retry(token: String) {
        _state.value = UiState.Idle
        load(token)
    }
}
```

## Compose UI Integration

```kotlin
// ui/screens/ProductsScreen.kt
package com.example.app.ui.screens

import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import androidx.hilt.navigation.compose.hiltViewModel
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.example.app.ui.state.UiState
import com.example.app.ui.viewmodel.Product
import com.example.app.ui.viewmodel.ProductsViewModel

@Composable
fun ProductsScreen(
    token: String,
    viewModel: ProductsViewModel = hiltViewModel(),
) {
    // collectAsStateWithLifecycle suspends collection when app is backgrounded
    val uiState by viewModel.state.collectAsStateWithLifecycle()

    LaunchedEffect(token) {
        viewModel.load(token)
    }

    when (val state = uiState) {
        is UiState.Idle -> Unit
        is UiState.Loading -> Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
            CircularProgressIndicator()
        }
        is UiState.Success -> ProductList(products = state.data)
        is UiState.Error -> ErrorPanel(
            message = state.message,
            retryable = state.retryable,
            onRetry = { viewModel.retry(token) },
        )
    }
}

@Composable
private fun ProductList(products: List<Product>) {
    LazyColumn(contentPadding = PaddingValues(16.dp)) {
        items(products, key = { it.id }) { product ->
            ProductRow(product)
            HorizontalDivider()
        }
    }
}

@Composable
private fun ProductRow(product: Product) {
    Row(
        Modifier
            .fillMaxWidth()
            .padding(vertical = 12.dp),
        horizontalArrangement = Arrangement.SpaceBetween,
    ) {
        Text(product.name, style = MaterialTheme.typography.bodyLarge)
        Text("$${product.price}", style = MaterialTheme.typography.bodyMedium)
    }
}

@Composable
private fun ErrorPanel(message: String, retryable: Boolean, onRetry: () -> Unit) {
    Column(
        Modifier.fillMaxSize().padding(32.dp),
        horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.Center,
    ) {
        Text(message, style = MaterialTheme.typography.bodyMedium, color = MaterialTheme.colorScheme.error)
        if (retryable) {
            Spacer(Modifier.height(16.dp))
            Button(onClick = onRetry) { Text("Retry") }
        }
    }
}
```

## Anti-patterns

- **Calling the Workers API directly from a `@Composable`** — composables recompose frequently;
  network calls must live in the ViewModel inside `viewModelScope`.
- **Using `collectAsState()` instead of `collectAsStateWithLifecycle()`** — the former keeps
  collecting when the app is backgrounded, wasting battery and leaking coroutines.
- **Ignoring Workers error envelopes** — OkHttp does not throw on 4xx/5xx by default. Always
  check `response.isSuccessful` or Ktor's `response.status.isSuccess()` and decode the Workers
  error body.
- **Sharing a single mutable `List` across recompositions** — always call `.toList()` before
  emitting to `StateFlow` to create an immutable snapshot.
- **Not cancelling in-flight requests on ViewModel cleared** — Ktor and OkHttp calls launched in
  `viewModelScope` are automatically cancelled when the ViewModel is cleared; do not use
  `GlobalScope`.

## Gotchas

- `collectAsStateWithLifecycle` requires `androidx.lifecycle:lifecycle-runtime-compose` in your
  Gradle dependencies.
- Workers rate-limit headers (`cf-ratelimit-*`) are stripped by Cloudflare before reaching the
  client; back-off logic must be driven by 429 HTTP status, not headers.
- D1 REST errors return HTTP 200 with `{ "error": "..." }` in the body for query errors. Parse
  the D1 response envelope separately from the Ktor content negotiation layer.
- Hilt ViewModel injection in Compose requires the `hilt-navigation-compose` artifact in addition
  to `hilt-android`.

## Verification

```kotlin
// Test: verify error mapping
@Test
fun `WorkersApiException maps to Error state`() = runTest {
    val fakeApi = mockk<WorkersApiClient> {
        coEvery { get<ProductsResponse>(any(), any(), any()) } throws
            WorkersApiException(WorkersError("not found", 404), 404)
    }
    val vm = ProductsViewModel(fakeApi)
    vm.load("token")
    advanceUntilIdle()
    val state = vm.state.value
    assertTrue(state is UiState.Error)
    assertFalse((state as UiState.Error).retryable)
}
```

## Related

- `android-jetpack-compose.md`
- `android-workers-paging3-cursor-pagination.md`
- `android-workmanager-workers-sync.md`
- `android-retrofit-patterns.md`
- `mobile-network-resilience-cloudflare-workers.md`

## Sources

- https://developer.android.com/jetpack/compose/state
- https://developer.android.com/kotlin/coroutines/coroutines-best-practices
- https://ktor.io/docs/client-create-and-configure.html
- https://developers.cloudflare.com/workers/runtime-apis/fetch/
- https://developers.cloudflare.com/d1/platform/client-api/
