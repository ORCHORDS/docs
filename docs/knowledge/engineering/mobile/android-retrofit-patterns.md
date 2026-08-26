# android-retrofit-patterns

**Issue:** Making type-safe HTTP requests on Android using Retrofit 2 with coroutines and OkHttp interceptors
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Manually constructing and parsing HTTP requests with `HttpURLConnection` is fragile; Retrofit generates boilerplate and integrates with Moshi/Gson for deserialization.

## Pattern / Solution
```kotlin
// build.gradle
implementation "com.squareup.retrofit2:retrofit:2.11.0"
implementation "com.squareup.retrofit2:converter-moshi:2.11.0"
implementation "com.squareup.okhttp3:logging-interceptor:4.12.0"

// API interface
interface UserApi {
  @GET("users/{id}")
  suspend fun getUser(@Path("id") id: String): User

  @POST("users")
  suspend fun createUser(@Body user: CreateUserRequest): User

  @GET("users")
  suspend fun listUsers(@Query("page") page: Int, @Query("limit") limit: Int): List<User>
}

// Retrofit instance with auth interceptor
val okhttp = OkHttpClient.Builder()
  .addInterceptor { chain ->
    val request = chain.request().newBuilder()
      .addHeader("Authorization", "Bearer ${TokenStore.get()}")
      .build()
    chain.proceed(request)
  }
  .addInterceptor(HttpLoggingInterceptor().apply { level = HttpLoggingInterceptor.Level.BODY })
  .build()

val retrofit = Retrofit.Builder()
  .baseUrl("https://api.example.com/")
  .client(okhttp)
  .addConverterFactory(MoshiConverterFactory.create())
  .build()

val api = retrofit.create(UserApi::class.java)
```

## Gotchas
- `suspend` functions in the interface return the deserialized body directly and throw `HttpException` on non-2xx — wrap in `runCatching`
- `@Url` parameter overrides `baseUrl` entirely — useful for pre-signed URLs but strips auth headers
- OkHttp interceptors run for every request including those to different hosts; check the host before adding auth headers
- `MoshiConverterFactory` requires Moshi adapters for Kotlin data classes; add `KotlinJsonAdapterFactory`

## Related
- `android-coroutines.md`
- `mobile-network-resilience.md`
- `certificate-pinning.md`
