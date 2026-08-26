# Android ProfileInstaller Workers Baseline Profile

Date: 2026-08-23
Author: example.com
Status: production

## Symptom / Use-case

A production Android app that makes frequent calls to Cloudflare Workers endpoints suffers from
slow startup (cold start > 1 s) and janky first scroll, because the JIT compiler has not yet
optimised the networking and JSON parsing hot paths. The team wants to use Baseline Profiles to
pre-compile critical code paths — including the Workers API client, OkHttp internals, and
Kotlinx Serialization — and verify the improvement in CI using Macrobenchmark.

## Context

Android's `ProfileInstaller` library installs a pre-compiled profile (`.prof` file) at app install
time, allowing ART to AOT-compile the profiled classes before the user first launches the app.
Baseline Profiles target the "critical user journey" (CUJ): startup → authenticate → first
Workers API response rendered. The profile must be generated with Macrobenchmark, stored in
`src/main/baseline-prof.txt`, and bundled in the app AAR.

For Workers-heavy apps, the most impactful classes to profile are:
- OkHttp / Ktor HTTP engine internals
- Kotlinx Serialization JSON codec for Workers response types
- The app's ViewModel and Repository init paths
- Compose runtime (if the first screen is a Compose screen)

Stack:
- Android Gradle Plugin 8.5+
- `androidx.profileinstaller:profileinstaller` 1.4+
- `androidx.benchmark:benchmark-macro-junit4` 1.3+
- Kotlin 2.x + Ktor 3.x (Workers API client)
- Cloudflare Workers (staging endpoint for benchmark)

## Gradle Configuration

```kotlin
// app/build.gradle.kts
plugins {
    alias(libs.plugins.android.application)
    alias(libs.plugins.kotlin.android)
    alias(libs.plugins.baseline.profile) // com.android.tools.build:gradle plugin
}

android {
    defaultConfig {
        // ...
    }
    buildTypes {
        release {
            isMinifyEnabled = true
            isShrinkResources = true
            proguardFiles(getDefaultProguardFile("proguard-android-optimize.txt"), "proguard-rules.pro")
        }
        // Benchmark build type inherits release settings but is NOT minified
        create("benchmark") {
            initWith(getByName("release"))
            isMinifyEnabled = false
            isShrinkResources = false
            signingConfig = signingConfigs.getByName("debug")
            matchingFallbacks += listOf("release")
        }
    }
}

dependencies {
    implementation(libs.androidx.profileinstaller)
    // Workers API client
    implementation(libs.ktor.client.okhttp)
    implementation(libs.kotlinx.serialization.json)
    // Benchmark dependency (macrobenchmark module pulls this in)
    "baselineProfile"(project(":macrobenchmark"))
}
```

```kotlin
// macrobenchmark/build.gradle.kts
plugins {
    alias(libs.plugins.android.test)
    alias(libs.plugins.kotlin.android)
}

android {
    targetProjectPath = ":app"
    experimentalProperties["android.experimental.self-instrumenting"] = true

    defaultConfig {
        testInstrumentationRunner = "androidx.test.runner.AndroidJUnitRunner"
        testInstrumentationRunnerArguments["androidx.benchmark.suppressErrors"] = "EMULATOR"
    }

    buildTypes {
        create("benchmark") {
            isDebuggable = true
            signingConfig = signingConfigs.getByName("debug")
            matchingFallbacks += listOf("release")
        }
    }
}

dependencies {
    implementation(libs.androidx.benchmark.macro.junit4)
    implementation(libs.androidx.test.ext.junit)
    implementation(libs.androidx.test.uiautomator)
}
```

## Macrobenchmark Test: Workers CUJ

```kotlin
// macrobenchmark/src/androidTest/kotlin/com/example/app/WorkersCujBenchmark.kt
package com.example.app

import androidx.benchmark.macro.*
import androidx.benchmark.macro.junit4.MacrobenchmarkRule
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.uiautomator.By
import androidx.test.uiautomator.Until
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith

private const val PACKAGE = "com.example.app"
private const val STARTUP_TIMEOUT_MS = 10_000L
private const val WORKERS_RESPONSE_TIMEOUT_MS = 8_000L

@RunWith(AndroidJUnit4::class)
class WorkersCujBenchmark {

    @get:Rule
    val rule = MacrobenchmarkRule()

    /**
     * Generates a Baseline Profile for the Workers API cold start CUJ.
     * Run with: ./gradlew :macrobenchmark:connectedBenchmarkAndroidTest
     *   -Pandroid.testInstrumentationRunnerArguments.class=com.example.app.WorkersCujBenchmark
     */
    @Test
    fun generateBaselineProfile() = rule.collectBaselineProfile(
        packageName = PACKAGE,
        profileBlock = {
            startActivity()
            device.waitForIdle()
            // Wait for the Workers API response to render
            device.wait(Until.hasObject(By.res(PACKAGE, "products_list")), WORKERS_RESPONSE_TIMEOUT_MS)
            device.waitForIdle()
        },
    )

    @Test
    fun benchmarkColdStartWithProfile() = rule.measureRepeated(
        packageName = PACKAGE,
        metrics = listOf(StartupTimingMetric(), FrameTimingMetric()),
        compilationMode = CompilationMode.Partial(
            baselineProfileMode = BaselineProfileMode.Require,
            warmupIterations = 1,
        ),
        startupMode = StartupMode.COLD,
        iterations = 10,
        measureBlock = {
            startActivity()
            device.wait(Until.hasObject(By.res(PACKAGE, "products_list")), STARTUP_TIMEOUT_MS)
        },
    )

    @Test
    fun benchmarkColdStartWithoutProfile() = rule.measureRepeated(
        packageName = PACKAGE,
        metrics = listOf(StartupTimingMetric()),
        compilationMode = CompilationMode.None(),
        startupMode = StartupMode.COLD,
        iterations = 10,
        measureBlock = {
            startActivity()
            device.wait(Until.hasObject(By.res(PACKAGE, "products_list")), STARTUP_TIMEOUT_MS)
        },
    )
}
```

## Baseline Profile Generation Workflow

```bash
# 1. Connect a physical device (NOT emulator — profiles require hardware ART)
adb devices

# 2. Build and install the benchmark APK
./gradlew :macrobenchmark:connectedBenchmarkAndroidTest \
  -Pandroid.testInstrumentationRunnerArguments.class=com.example.app.WorkersCujBenchmark#generateBaselineProfile

# 3. The generated profile appears in:
#    app/src/main/baseline-prof.txt  (auto-copied by AGP 8.x baseline profile plugin)
# If using AGP 8.4 or older, copy manually:
adb pull /sdcard/Android/media/com.example.app.benchmark/additional_test_output/BaselineProfile.txt \
  app/src/main/baseline-prof.txt

# 4. Inspect the profile — look for Workers/OkHttp classes
grep -E "(okhttp|ktor|serialization|WorkersApi)" app/src/main/baseline-prof.txt | head -20

# 5. Build a release APK and verify the profile is bundled
./gradlew :app:assembleRelease
unzip -p app/build/outputs/apk/release/app-release.apk assets/dexopt/baseline.prof | file -
```

## Manual Profile Supplement for Workers Classes

If the macrobenchmark does not exercise all Workers hot paths (e.g., error handling branches),
add classes manually to `baseline-prof.txt`:

```
# Cloudflare Workers OkHttp client hot paths
Lokhttp3/OkHttpClient;
Lokhttp3/Request;
Lokhttp3/Response;
Lokhttp3/internal/connection/RealConnection;
Lokhttp3/internal/http/CallServerInterceptor;
# Kotlinx Serialization Workers response types
Lkotlinx/serialization/json/internal/JsonLexer;
Lkotlinx/serialization/json/internal/StreamingJsonDecoder;
# App-specific Workers API classes
Lcom/example/app/data/remote/WorkersApiClient;
Lcom/example/app/data/remote/WorkersApiClient$get$1;
Lcom/example/app/ui/viewmodel/ProductsViewModel;
```

## ProfileInstaller Initialisation in Application

```kotlin
// MyApplication.kt
import androidx.profileinstaller.ProfileInstallerInitializer
import androidx.startup.AppInitializer

class MyApplication : Application() {
    override fun onCreate() {
        super.onCreate()
        // ProfileInstaller is initialized via Jetpack Startup automatically.
        // Call manually only if you use InitializationProvider with manual control:
        AppInitializer.getInstance(this)
            .initializeComponent(ProfileInstallerInitializer::class.java)
    }
}
```

Add to `AndroidManifest.xml` if not already present (required for Jetpack Startup):
```xml
<provider
    android:name="androidx.startup.InitializationProvider"
    android:authorities="${applicationId}.androidx-startup"
    android:exported="false">
    <meta-data
        android:name="androidx.profileinstaller.ProfileInstallerInitializer"
        android:value="@string/androidx_startup" />
</provider>
```

## Anti-patterns

- **Running Macrobenchmark on an emulator** — ART profile generation is disabled on emulators;
  always use a physical device with a non-rooted production-grade OS build.
- **Generating the profile against a debug build** — Debug builds disable ProGuard, so the profiled
  class names differ from release. Always use the `benchmark` build type.
- **Not exercising the Workers API call in the CUJ** — A profile that captures only startup
  without the first network call misses OkHttp's connection pool initialisation, missing 30-50 %
  of potential improvement.
- **Committing generated `.prof` binary files** — Commit only `baseline-prof.txt` (text format).
  The `.prof` binary is generated by AGP at build time from the text file.
- **Forgetting to add `matchingFallbacks`** — Without it, the `benchmark` build type cannot
  resolve release-only dependencies and the benchmark module fails to compile.

## Gotchas

- AGP 8.3+ runs Baseline Profile generation as part of `assembleRelease` if the
  `:macrobenchmark` module is present and a connected device is available. This can surprise CI
  pipelines; add `-Pandroid.experimental.testOptions.unitTestsEnabled=false` to disable.
- `CompilationMode.Partial` with `BaselineProfileMode.Require` throws if `baseline-prof.txt` is
  missing from the APK. Use `BaselineProfileMode.UseIfAvailable` in early development.
- Workers responses compressed with Brotli (`br`) are not decoded by OkHttp by default in Android
  < 12. Add `okhttp3-brotli` or disable Brotli in the Worker for Android clients.
- Profile classes must be in the main dex split; classes loaded only by feature modules after
  install are not eligible for AOT compilation via Baseline Profiles.

## Verification

```bash
# Compare cold start times with/without profile using Macrobenchmark output
./gradlew :macrobenchmark:connectedBenchmarkAndroidTest \
  -Pandroid.testInstrumentationRunnerArguments.class=com.example.app.WorkersCujBenchmark

# Results appear in:
# macrobenchmark/build/outputs/connected_android_test_additional_output/
# Look for: timeToInitialDisplayMs — target < 500 ms for Workers-first screens

# Verify profile was installed on device
adb shell cmd package art get-app-profiles com.example.app
```

## Related

- `android-workmanager-workers-sync.md`
- `android-profilingmanager-system-triggered-profiles.md`
- `android-workers-paging3-cursor-pagination.md`
- `android-jetpack-compose.md`
- `mobile-app-startup-time-optimization.md`

## Sources

- https://developer.android.com/topic/performance/baselineprofiles/overview
- https://developer.android.com/topic/libraries/support-library/androidx-rn
- https://developer.android.com/reference/androidx/profileinstaller/ProfileInstaller
- https://developer.android.com/topic/performance/benchmarking/macrobenchmark-overview
- https://developers.cloudflare.com/workers/
