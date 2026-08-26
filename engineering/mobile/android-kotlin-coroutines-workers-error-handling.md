# Android Kotlin Coroutines Cloudflare Workers API Error Handling

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

The example project Android app calls Cloudflare Workers APIs from Kotlin coroutines. In production you observe:

- Unhandled `CancellationException` propagating to Crashlytics as crashes when the user navigates away mid-request
- Coroutine scope leaks when the ViewModel is cleared mid-flight
- 429 rate-limit errors from Workers silently swallowed, causing blank screens
- Retries hammering the Worker during Cloudflare incidents, worsening the outage
- `NetworkOnMainThreadException` from misconfigured dispatcher
- D1 query timeouts (`524`) not distinguished from application-level 4xx errors

---

## Context

Stack: Kotlin 2.x, Coroutines 1.9+, Retrofit 2 + OkHttp, Hilt, ViewModel + StateFlow, Android 12+.

Workers API design: All endpoints return `application/json`. Error envelope:

```json
{ "error": "rate_limited", "retryAfter": 2 }
```

HTTP status codes:
- `200` success
- `400` bad request (client bug)
- `401` auth expired
- `429` rate limited (Cloudflare rule or Worker limit)
- `500` Worker unhandled exception
- `524` Cloudflare origin timeout (D1 slow query)
- `530` Cloudflare 1xxx errors (Worker boot failure, script error)

The goal is a typed, structured error hierarchy that the UI layer can switch on without parsing strings.

---

## Sealed Error Hierarchy

```kotlin
// core/network/WorkersError.kt
sealed class WorkersError : Exception() {
    data class HttpError(val code: Int, val errorKey: String?) : WorkersError()
    data class RateLimited(val retryAfterSeconds: Int) : WorkersError()
    data class Unauthorized(val reason: String?) : WorkersError()
    data class CloudflareGateway(val code: Int) : WorkersError() // 524, 530
    data class NetworkFailure(val cause: Throwable) : WorkersError()
    data object Cancelled : WorkersError()
}
```

---

## Retrofit Error Adapter

```kotlin
// core/network/WorkersErrorAdapter.kt
import com.squareup.moshi.Moshi
import com.squareup.moshi.kotlin.reflect.KotlinJsonAdapterFactory
import kotlinx.coroutines.CancellationException
import retrofit2.HttpException
import java.io.IOException
import java.net.SocketTimeoutException

private val moshi = Moshi.Builder().add(KotlinJsonAdapterFactory()).build()

data class WorkersErrorBody(val error: String?, val retryAfter: Int?)

suspend fun <T> safeWorkerCall(block: suspend () -> T): Result<T> {
    return try {
        Result.success(block())
    } catch (e: CancellationException) {
        // Always re-throw CancellationException — coroutine machinery depends on it
        throw e
    } catch (e: HttpException) {
        val mapped = mapHttpException(e)
        Result.failure(mapped)
    } catch (e: SocketTimeoutException) {
        // OkHttp read timeout — likely a slow D1 query
        Result.failure(WorkersError.NetworkFailure(e))
    } catch (e: IOException) {
        Result.failure(WorkersError.NetworkFailure(e))
    } catch (e: Exception) {
        Result.failure(WorkersError.NetworkFailure(e))
    }
}

private fun mapHttpException(e: HttpException): WorkersError {
    val code = e.code()
    // Parse JSON error body if present
    val body = runCatching {
        val source = e.response()?.errorBody()?.source() ?: return@runCatching null
        moshi.adapter(WorkersErrorBody::class.java).fromJson(source)
    }.getOrNull()

    return when (code) {
        401 -> WorkersError.Unauthorized(body?.error)
        429 -> WorkersError.RateLimited(body?.retryAfter ?: 1)
        in 524..530 -> WorkersError.CloudflareGateway(code)
        else -> WorkersError.HttpError(code, body?.error)
    }
}
```

---

## ViewModel Integration with StateFlow

```kotlin
// feature/feed/FeedViewModel.kt
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import javax.inject.Inject

sealed interface FeedUiState {
    data object Loading : FeedUiState
    data class Success(val posts: List<Post>) : FeedUiState
    data class Error(val error: WorkersError) : FeedUiState
    data object RateLimited : FeedUiState
}

@HiltViewModel
class FeedViewModel @Inject constructor(
    private val feedRepository: FeedRepository
) : ViewModel() {

    private val _uiState = MutableStateFlow<FeedUiState>(FeedUiState.Loading)
    val uiState = _uiState.asStateFlow()

    fun loadFeed(cursor: String? = null) {
        viewModelScope.launch {
            _uiState.value = FeedUiState.Loading

            safeWorkerCall { feedRepository.getFeed(cursor) }
                .fold(
                    onSuccess = { page ->
                        _uiState.value = FeedUiState.Success(page.posts)
                    },
                    onFailure = { error ->
                        when (error) {
                            is WorkersError.RateLimited -> {
                                _uiState.value = FeedUiState.RateLimited
                                // Schedule automatic retry after backoff
                                scheduleRetry(cursor, error.retryAfterSeconds.toLong())
                            }
                            is WorkersError.Unauthorized -> {
                                // Delegate to auth handler — don't show error UI here
                                authEventBus.emit(AuthEvent.SessionExpired)
                            }
                            else -> _uiState.value = FeedUiState.Error(error as WorkersError)
                        }
                    }
                )
        }
    }

    private fun scheduleRetry(cursor: String?, delaySecs: Long) {
        viewModelScope.launch {
            kotlinx.coroutines.delay(delaySecs * 1_000)
            loadFeed(cursor)
        }
    }
}
```

---

## Exponential Backoff for 5xx / Gateway Errors

```kotlin
// core/network/RetryPolicy.kt
import kotlinx.coroutines.delay
import kotlin.math.min
import kotlin.math.pow

/**
 * Retries [block] up to [maxAttempts] times on retriable errors.
 * Uses truncated exponential backoff with jitter.
 */
suspend fun <T> withRetry(
    maxAttempts: Int = 3,
    initialDelayMs: Long = 300,
    maxDelayMs: Long = 8_000,
    block: suspend () -> Result<T>
): Result<T> {
    var attempt = 0
    while (attempt < maxAttempts) {
        val result = block()
        if (result.isSuccess) return result

        val error = result.exceptionOrNull()
        val isRetriable = when (error) {
            is WorkersError.CloudflareGateway -> true
            is WorkersError.NetworkFailure -> true
            is WorkersError.HttpError -> error.code >= 500
            else -> false
        }

        if (!isRetriable || attempt == maxAttempts - 1) return result

        val backoff = min(
            (initialDelayMs * 2.0.pow(attempt)).toLong(),
            maxDelayMs
        )
        // Add ±20% jitter to prevent thundering herd
        val jitter = (backoff * 0.2 * (Math.random() - 0.5)).toLong()
        delay(backoff + jitter)
        attempt++
    }
    return block() // final attempt
}
```

Usage in repository:

```kotlin
// feature/feed/FeedRepository.kt
import javax.inject.Inject

class FeedRepository @Inject constructor(
    private val feedApi: FeedApi,
    @IoDispatcher private val ioDispatcher: CoroutineDispatcher
) {
    suspend fun getFeed(cursor: String?): FeedPage = withContext(ioDispatcher) {
        withRetry(maxAttempts = 3) {
            safeWorkerCall { feedApi.getFeed(cursor = cursor) }
        }.getOrThrow()
    }
}
```

---

## Dispatcher Qualifiers (Hilt)

```kotlin
// core/di/DispatcherModule.kt
import dagger.Module
import dagger.Provides
import dagger.hilt.InstallIn
import dagger.hilt.components.SingletonComponent
import kotlinx.coroutines.CoroutineDispatcher
import kotlinx.coroutines.Dispatchers
import javax.inject.Qualifier

@Qualifier
@Retention(AnnotationRetention.BINARY)
annotation class IoDispatcher

@Qualifier
@Retention(AnnotationRetention.BINARY)
annotation class MainDispatcher

@Module
@InstallIn(SingletonComponent::class)
object DispatcherModule {
    @Provides
    @IoDispatcher
    fun provideIoDispatcher(): CoroutineDispatcher = Dispatchers.IO

    @Provides
    @MainDispatcher
    fun provideMainDispatcher(): CoroutineDispatcher = Dispatchers.Main.immediate
}
```

---

## Compose UI Error Handling

```kotlin
// feature/feed/FeedScreen.kt
@Composable
fun FeedScreen(viewModel: FeedViewModel = hiltViewModel()) {
    val uiState by viewModel.uiState.collectAsStateWithLifecycle()

    when (val state = uiState) {
        FeedUiState.Loading -> CircularProgressIndicator()
        is FeedUiState.Success -> FeedList(posts = state.posts)
        FeedUiState.RateLimited -> RateLimitedBanner()
        is FeedUiState.Error -> ErrorView(
            error = state.error,
            onRetry = { viewModel.loadFeed() }
        )
    }
}

@Composable
private fun ErrorView(error: WorkersError, onRetry: () -> Unit) {
    val message = when (error) {
        is WorkersError.CloudflareGateway ->
            "Service temporarily unavailable (${error.code})"
        is WorkersError.NetworkFailure ->
            "Network error — check your connection"
        is WorkersError.HttpError ->
            "Unexpected error: ${error.errorKey ?: error.code}"
        else -> "Something went wrong"
    }

    Column(horizontalAlignment = Alignment.CenterHorizontally) {
        Text(message)
        Spacer(Modifier.height(8.dp))
        Button(onClick = onRetry) { Text("Retry") }
    }
}
```

---

## Anti-patterns

- **Catching `CancellationException` and not re-throwing it**: This breaks cooperative cancellation. The coroutine framework uses `CancellationException` internally; swallowing it leaves coroutines in an uncancellable zombie state. Always re-throw it as shown in `safeWorkerCall`.
- **Using `GlobalScope` for API calls**: `GlobalScope` outlives Activities and ViewModels. All Worker API calls must be in `viewModelScope` or a Hilt-scoped `CoroutineScope`.
- **Blocking `Dispatchers.Main` with network calls**: Even with coroutines, blocking reads on the main dispatcher cause ANRs. Always dispatch to `Dispatchers.IO`.
- **Not distinguishing 524 from 500**: Cloudflare 524 means a D1 query took too long; it is a transient infrastructure issue, not an app bug. Retrying with backoff is correct. Logging it as a `500` masks D1 performance issues.
- **Retrying on 401 without refreshing the token first**: Retrying an expired-token request without refreshing will always fail. 401 should route to the auth refresh flow, not the generic retry policy.
- **Hardcoded retry counts with no circuit breaker**: During a Cloudflare outage, every user retrying aggressively amplifies the incident. Implement a simple circuit breaker or honour the `Retry-After` header.

---

## Gotchas

- **`HttpException` body can only be read once**: OkHttp's `ResponseBody` is a stream. Call `errorBody()?.string()` once and cache it; calling it a second time returns empty string. Use `source()` with Moshi or copy to a string first.
- **Moshi's `KotlinJsonAdapterFactory` and R8**: Add the Moshi R8 rules from `moshi-kotlin-codegen` if you use code generation, or use `@Keep` on your JSON DTOs.
- **`viewModelScope` vs. `lifecycleScope`**: Use `viewModelScope` for data fetching; use `lifecycleScope` only for UI-driven effects. Mixing them means data fetching can outlive the ViewModel if tied to lifecycle.
- **`collectAsStateWithLifecycle` requires `lifecycle-runtime-compose`**: Add `androidx.lifecycle:lifecycle-runtime-compose` to your Gradle dependencies, not just `lifecycle-viewmodel-compose`.
- **Coroutine cancellation during `delay`**: If the ViewModel is cleared while `scheduleRetry`'s `delay` is running, the `delay` is cancelled cleanly (it checks for cancellation). No need for manual cleanup.

---

## Verification

```bash
# Unit test the error mapping
./gradlew :core:network:test --tests "*.WorkersErrorAdapterTest"

# Integration test with MockWebServer
# Enqueue a 429 response with Retry-After: 2, assert UI shows RateLimitedBanner
# Enqueue a 524 response, assert retry fires after backoff

# Verify no CancellationException in Crashlytics:
# Navigate away during an active request — check that no crash is recorded
```

```kotlin
// test: WorkersErrorAdapterTest.kt (excerpt)
@Test
fun `maps 429 to RateLimited with retryAfter`() = runTest {
    val server = MockWebServer()
    server.enqueue(MockResponse().setResponseCode(429)
        .setBody("""{"error":"rate_limited","retryAfter":5}"""))

    val api = buildRetrofit(server.url("/")).create(FeedApi::class.java)
    val result = safeWorkerCall { api.getFeed(null) }

    assertIs<WorkersError.RateLimited>(result.exceptionOrNull())
    assertEquals(5, (result.exceptionOrNull() as WorkersError.RateLimited).retryAfterSeconds)
}
```

---

## Related

- `android-coroutines.md`
- `android-retrofit-patterns.md`
- `android-hilt-dependency-injection.md`
- `android-jetpack-compose-workers-api-state.md`
- `react-native-anonymous-session-refresh-workers-jwt.md`
- `mobile-network-resilience-cloudflare-workers.md`

---

## Sources

- Kotlin Coroutines structured concurrency guide: https://kotlinlang.org/docs/coroutines-guide.html
- Android `viewModelScope` docs: https://developer.android.com/topic/libraries/architecture/coroutines
- Cloudflare error codes 5xx reference: https://developers.cloudflare.com/support/troubleshooting/cloudflare-errors/
- OkHttp `MockWebServer` testing: https://square.github.io/okhttp/features/mock_web_server/
- Moshi Kotlin adapter: https://github.com/square/moshi#kotlin
