# react-native-accessibility

**Issue:** Making React Native apps usable with VoiceOver (iOS) and TalkBack (Android)
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Custom components without accessibility props are invisible to screen readers, leading to app store accessibility rejections and WCAG compliance failures.

## Pattern / Solution
```jsx
// Basic accessibility props
<TouchableOpacity
  accessible
  accessibilityRole="button"
  accessibilityLabel="Submit order"
  accessibilityHint="Confirms and places your order"
  accessibilityState={{ disabled: isLoading }}
  onPress={submit}
>
  <Text>Submit</Text>
</TouchableOpacity>

// Group elements for single focus
<View
  accessible
  accessibilityLabel="Product: Blue T-Shirt, $29.99, In stock"
>
  <Text>Blue T-Shirt</Text>
  <Text>$29.99</Text>
  <Text>In stock</Text>
</View>

// Live regions for dynamic updates
<Text
  accessibilityLiveRegion="polite"
  accessibilityRole="status"
>
  {statusMessage}
</Text>

// Programmatically set focus
import { AccessibilityInfo, findNodeHandle } from 'react-native';
const ref = useRef(null);
AccessibilityInfo.setAccessibilityFocus(findNodeHandle(ref.current));
```

## Gotchas
- `accessibilityLabel` overrides all child text for the screen reader — keep it concise
- `accessibilityRole="image"` without `accessibilityLabel` reads as "image, unlabelled"
- VoiceOver swipe order follows DOM order, not visual position — use `importantForAccessibility` to hide decorative elements
- Test with actual VoiceOver/TalkBack enabled; the Accessibility Inspector only approximates behavior

## Related
- `react-native-localization.md`
- `android-accessibility.md`
- `mobile-accessibility-a11y.md`
