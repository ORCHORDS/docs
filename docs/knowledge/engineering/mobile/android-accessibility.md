# android-accessibility

**Issue:** Making Android apps usable with TalkBack and other accessibility services
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Custom views and Compose layouts without content descriptions are inaccessible to the 1 billion+ people using assistive technology.

## Pattern / Solution
XML Views:
```xml
<ImageButton
  android:contentDescription="@string/submit_order"
  android:importantForAccessibility="yes" />

<!-- Decorative image — hide from TalkBack -->
<ImageView
  android:contentDescription="@null"
  android:importantForAccessibility="no" />
```

Jetpack Compose:
```kotlin
// Merge semantics for grouped content
Row(
  modifier = Modifier.semantics(mergeDescendants = true) {}
) {
  Icon(Icons.Default.Star, contentDescription = null) // decorative inside merged group
  Text("4.5 (1,200 ratings)")
}

// Custom action label
Box(
  modifier = Modifier.clickable(
    onClick = { delete(item) },
    onClickLabel = "Delete ${item.name}"
  )
)

// Live region for dynamic updates
Text(
  text = statusMessage,
  modifier = Modifier.semantics { liveRegion = LiveRegionMode.Polite }
)
```

## Gotchas
- TalkBack reads elements in layout order (XML) or composition order (Compose), not visual order
- `contentDescription` on a `Button` that already has text causes double-reading — set it to `null` or use `clearAndSetSemantics`
- Font scaling: use `sp` units only for text, not layout dimensions; test with system font size at 200%
- Touch target minimum size is 48×48 dp per Material guidelines; smaller targets fail accessibility audits

## Related
- `android-jetpack-compose.md`
- `mobile-accessibility-a11y.md`
- `react-native-accessibility.md`
