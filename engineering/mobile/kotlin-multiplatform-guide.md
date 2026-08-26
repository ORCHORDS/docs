# Kotlin Multiplatform with Modern Build Tooling

## Overview

Kotlin Multiplatform Mobile (KMP) enables sharing business logic across iOS and Android platforms. Modern build tooling has evolved significantly, requiring developers to adapt their workflows for optimal performance and compatibility.

## Shared Logic Implementation

KMP allows you to write shared code that compiles to both platforms:

```kotlin
// commonMain/src/main/kotlin/com/example/shared/Calculator.kt
expect class Calculator {
    fun add(a: Int, b: Int): Int
    fun divide(a: Int, b: Int): Double
}

// androidMain/src/main/kotlin/com/example/shared/Calculator.android.kt
actual class Calculator {
    actual fun add(a: Int, b: Int): Int = a + b
    actual fun divide(a: Int, b: Int): Double = a.toDouble() / b
}

// iosMain/src/main/kotlin/com/example/shared/Calculator.ios.kt
actual class Calculator {
    actual fun add(a: Int, b: Int): Int = a + b
    actual fun divide(a: Int, b: Int): Double = a.toDouble() / b
}
```

## Swift Package Manager Migration

Migrating from CocoaPods to Swift Package Manager requires updating your build configuration:

```swift
// Package.swift
import PackageDescription

let package = Package(
    name: "SharedLibrary",
    platforms: [
        .iOS(.v13),
        .macOS(.v10_15)
    ],
    products: [
        .library(name: "SharedLibrary", targets: ["SharedLibrary"])
    ],
    dependencies: [
        .package(url: "https://github.com/Kotlin/kotlinx.coroutines.git", from: "1.6.0")
    ],
    targets: [
        .target(
            name: "SharedLibrary",
            dependencies: [],
            path: "shared"
        )
    ]
)
```

## Gradle Version Catalogs

Version catalogs simplify dependency management in modern Gradle projects:

```toml
# gradle/libs.versions.toml
[versions]
kotlin = "1.9.0"
coroutines = "1.6.4"
kmpNative = "0.14.0"

[libraries]
kotlin-stdlib = { group = "org.jetbrains.kotlin", name = "kotlin-stdlib", version.ref = "kotlin" }
cor
