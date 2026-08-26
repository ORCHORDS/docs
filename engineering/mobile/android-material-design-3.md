# android-material-design-3

**Issue:** Applying Material Design 3 (Material You) dynamic color and components in Jetpack Compose
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Material 2 themes do not support Android 12 dynamic color (wallpaper-derived palette); MD3 enables per-device personalization.

## Pattern / Solution
```kotlin
// build.gradle
implementation "androidx.compose.material3:material3:1.3.1"

// Theme setup with dynamic color
@Composable
fun AppTheme(darkTheme: Boolean = isSystemInDarkTheme(), content: @Composable () -> Unit) {
  val colorScheme = when {
    Build.VERSION.SDK_INT >= Build.VERSION_CODES.S -> {
      val context = LocalContext.current
      if (darkTheme) dynamicDarkColorScheme(context)
      else dynamicLightColorScheme(context)
    }
    darkTheme -> darkColorScheme(
      primary = Purple80, secondary = PurpleGrey80
    )
    else -> lightColorScheme(
      primary = Purple40, secondary = PurpleGrey40
    )
  }

  MaterialTheme(colorScheme = colorScheme, typography = AppTypography, content = content)
}

// MD3 components
@Composable
fun ActionButton(onClick: () -> Unit) {
  FilledTonalButton(onClick = onClick) {
    Icon(Icons.Default.Add, contentDescription = null)
    Spacer(Modifier.width(8.dp))
    Text("Add Item")
  }
}
```

## Gotchas
- Dynamic color is only available on Android 12 (API 31)+ — always provide a fallback color scheme
- MD3 `TopAppBar` is not the same as MD2 `TopAppBar` — imports conflict; use full qualifier
- `NavigationBar` (MD3) replaces `BottomNavigation` (MD2) — the two cannot be mixed in the same app without theming conflicts
- `OutlinedTextField` in MD3 has different padding than MD2 — account for this in layout measurements

## Related
- `android-jetpack-compose.md`
- `android-accessibility.md`
