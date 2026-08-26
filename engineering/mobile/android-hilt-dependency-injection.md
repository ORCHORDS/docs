# Android Hilt Dependency Injection Patterns

Date: 2026-08-23 / Author: example.com / Status: production

## Symptom / Use-case

A growing Android codebase has repositories, Workers API clients, Room DAOs, and
WorkManager workers all manually wired together in `Application.onCreate()`. Tests require
large stubs, and any module swap breaks a chain of constructor calls. The team wants
compile-time verified DI with minimal boilerplate.

## Context

Hilt is the recommended DI framework for Android. It sits on top of Dagger 2 and generates
component and binding code at compile time. Hilt provides predefined component scopes that
match Android lifecycle objects (`SingletonComponent`, `ActivityComponent`,
`ViewModelComponent`, `ServiceComponent`) and integrates natively with WorkManager,
Navigation, and Jetpack Compose.

This article covers project setup, module organisation, ViewModel injection, WorkManager
injection, and testing conventions as used when the backend is a Cloudflare Workers API.

Stack: Kotlin, Hilt 2.52+, Room 2.6+, Retrofit 2 / OkHttp 5, WorkManager 2.9+,
`hilt-navigation-compose`.

## Project Setup

```kotlin
// build.gradle.kts (root)
plugins {
    id("com.google.dagger.hilt.android") version "2.52" apply false
}

// app/build.gradle.kts
plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
    id("com.google.dagger.hilt.android")
    id("com.google.devtools.ksp")          // preferred over kapt since Kotlin 2.0
}

dependencies {
    implementation("com.google.dagger:hilt-android:2.52")
    ksp("com.google.dagger:hilt-android-compiler:2.52")

    // WorkManager + Hilt integration
    implementation("androidx.hilt:hilt-work:1.2.0")
    ksp("androidx.hilt:hilt-compiler:1.2.0")

    // Navigation + Compose
    implementation("androidx.hilt:hilt-navigation-compose:1.2.0")
}
```

```kotlin
// MyApplication.kt
@HiltAndroidApp
class MyApplication : Application()
```

## Network Module

```kotlin
// di/NetworkModule.kt
@Module
@InstallIn(SingletonComponent::class)
object NetworkModule {

    @Provides
    @Singleton
    fun provideOkHttpClient(
        @ApplicationContext ctx: Context,
        tokenStore: TokenStore,
    ): OkHttpClient = OkHttpClient.Builder()
        .addInterceptor { chain ->
            val req = chain.request().newBuilder()
                .header("Authorization", "Bearer ${tokenStore.accessToken()}")
                .header("X-App-Version", BuildConfig.VERSION_NAME)
                .build()
            chain.proceed(req)
        }
        .connectTimeout(10, TimeUnit.SECONDS)
        .readTimeout(30, TimeUnit.SECONDS)
        .build()

    @Provides
    @Singleton
    fun provideRetrofit(client: OkHttpClient): Retrofit = Retrofit.Builder()
        .baseUrl("https://api.example.com/")
        .client(client)
        .addConverterFactory(Json.asConverterFactory("application/json".toMediaType()))
        .build()

    @Provides
    @Singleton
    fun provideApiService(retrofit: Retrofit): WorkersApiService =
        retrofit.create(WorkersApiService::class.java)
}
```

## Repository and ViewModel Injection

```kotlin
// data/MetricsRepository.kt
class MetricsRepository @Inject constructor(
    private val api: WorkersApiService,
    private val dao: MetricsDao,
) {
    suspend fun fetchLatest(): List<Metric> {
        val remote = api.getMetrics()
        dao.upsertAll(remote)
        return remote
    }

    fun observeMetrics(): Flow<List<Metric>> = dao.observeAll()
}

// ui/MetricsViewModel.kt
@HiltViewModel
class MetricsViewModel @Inject constructor(
    private val repo: MetricsRepository,
) : ViewModel() {

    val metrics: StateFlow<List<Metric>> = repo
        .observeMetrics()
        .stateIn(viewModelScope, SharingStarted.WhileSubscribed(5_000), emptyList())

    init {
        viewModelScope.launch {
            runCatching { repo.fetchLatest() }
                .onFailure { Timber.e(it, "Failed to fetch metrics") }
        }
    }
}

// ui/MetricsScreen.kt  (Compose entry-point)
@Composable
fun MetricsScreen(
    viewModel: MetricsViewModel = hiltViewModel(),
) {
    val metrics by viewModel.metrics.collectAsStateWithLifecycle()
    LazyColumn { items(metrics) { MetricRow(it) } }
}
```

## Database Module

```kotlin
// di/DatabaseModule.kt
@Module
@InstallIn(SingletonComponent::class)
object DatabaseModule {

    @Provides
    @Singleton
    fun provideDatabase(@ApplicationContext ctx: Context): AppDatabase =
        Room.databaseBuilder(ctx, AppDatabase::class.java, "app.db")
            .addMigrations(MIGRATION_1_2)
            .fallbackToDestructiveMigrationOnDowngrade()
            .build()

    @Provides
    fun provideMetricsDao(db: AppDatabase): MetricsDao = db.metricsDao()
}

// data/AppDatabase.kt
@Database(entities = [Metric::class], version = 2)
abstract class AppDatabase : RoomDatabase() {
    abstract fun metricsDao(): MetricsDao
}
```

## WorkManager Worker Injection

```kotlin
// work/SyncWorker.kt
@HiltWorker
class SyncWorker @AssistedInject constructor(
    @Assisted ctx: Context,
    @Assisted params: WorkerParameters,
    private val repo: MetricsRepository,
) : CoroutineWorker(ctx, params) {

    override suspend fun doWork(): Result {
        return try {
            repo.fetchLatest()
            Result.success()
        } catch (e: Exception) {
            if (runAttemptCount < 3) Result.retry() else Result.failure()
        }
    }
}

// MyApplication.kt  –  configure HiltWorkerFactory
@HiltAndroidApp
class MyApplication : Application(), Configuration.Provider {

    @Inject lateinit var workerFactory: HiltWorkerFactory

    override val workManagerConfiguration: Configuration
        get() = Configuration.Builder()
            .setWorkerFactory(workerFactory)
            .build()
}

// AndroidManifest.xml  –  remove default WorkManager initializer
// <provider android:name="androidx.startup.InitializationProvider" …>
//   <meta-data android:name="androidx.work.WorkManagerInitializer" tools:node="remove" />
// </provider>
```

## Testing with Hilt

```kotlin
// HiltTestRunner.kt
class HiltTestRunner : AndroidJUnitRunner() {
    override fun newApplication(cl: ClassLoader, name: String, ctx: Context): Application =
        super.newApplication(cl, name, HiltTestApplication::class.java.name, ctx)
}

// ExampleInstrumentedTest.kt
@HiltAndroidTest
@RunWith(AndroidJUnit4::class)
class MetricsViewModelTest {

    @get:Rule(order = 0) val hiltRule  = HiltAndroidRule(this)
    @get:Rule(order = 1) val composeRule = createAndroidComposeRule<MainActivity>()

    @Inject lateinit var repo: MetricsRepository

    @Before fun setUp() { hiltRule.inject() }

    @Test fun `sync populates metrics list`() = runTest {
        // Arrange: FakeNetworkModule replaces NetworkModule in test
        val initial = repo.observeMetrics().first()
        assertThat(initial).isEmpty()
    }
}

// di/FakeNetworkModule.kt  (in androidTest/)
@TestInstallIn(components = [SingletonComponent::class], replaces = [NetworkModule::class])
@Module
object FakeNetworkModule {
    @Provides @Singleton
    fun provideFakeApi(): WorkersApiService = FakeWorkersApiService()
}
```

## Anti-patterns

- **Injecting into plain classes with `@Inject` on every property** — Hilt only injects into
  Android framework classes (`Activity`, `Fragment`, `Service`, `ViewModel` via `@HiltViewModel`,
  `Worker` via `@HiltWorker`). For plain classes use constructor injection.
- **`@Singleton` on mutable state** — a singleton survives configuration changes but also
  memory pressure restarts; always back singleton state with a persistence layer (Room, DataStore).
- **Bypassing the factory for WorkManager** — if `Configuration.Provider` is not implemented and
  the default initializer not removed, Hilt-injected workers silently fall back to a no-op
  factory and crash at `doWork`.
- **Circular dependencies between modules** — break cycles with an `@Provides` method that
  supplies a lazy `Provider<T>` instead of `T` directly.

## Gotchas

- KSP and KAPT cannot coexist for Hilt in the same module. Pick KSP; it is significantly faster
  in incremental builds and is the path forward from Kotlin 2.0 onward.
- `@InstallIn(ActivityRetainedComponent::class)` shares the scope of the retained ViewModel
  store, not `SingletonComponent`. Use it only for objects that must survive configuration
  changes but not app restarts.
- When using Hilt with the Navigation component and `hiltViewModel()`, the ViewModel is scoped
  to the nav back-stack entry, not the `Activity`. Pass the `navBackStackEntry` explicitly when
  a parent route must own the state.
- Multi-module projects need `@HiltAndroidApp` only in the `:app` module. Library modules use
  `@Module @InstallIn(…)` only — never `@HiltAndroidApp`.

## Verification

```bash
# Check generated Hilt components in the build output
ls app/build/generated/ksp/debug/kotlin/com/example/app/

# Confirm no duplicate Dagger components at link time (a KSP incremental build artifact)
./gradlew :app:kspDebugKotlin --info 2>&1 | grep "Dagger"

# Run Hilt instrumented tests
./gradlew :app:connectedDebugAndroidTest --tests "*.MetricsViewModelTest"
```

## Related

- `android-workmanager-workers-sync.md`
- `android-room-database.md`
- `android-viewmodel-patterns.md`
- `android-coroutines.md`

## Sources

- Hilt documentation — developer.android.com/training/dependency-injection/hilt-android
- Hilt + WorkManager — developer.android.com/training/dependency-injection/hilt-jetpack#workmanager
- KSP migration guide — developer.android.com/build/migrate-to-ksp
