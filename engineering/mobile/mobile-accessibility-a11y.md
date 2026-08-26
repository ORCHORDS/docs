# mobile-accessibility-a11y

**Issue:** Making mobile apps accessible to users with disabilities
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Accessibility is required by law (ADA, EN 301 549) and expands your user base. VoiceOver (iOS) and TalkBack (Android) are screen readers that apps must support. Missing labels and incorrect roles make apps unusable for blind users.

## Pattern / Solution
**React Native accessibility props:**
```tsx
// Basic label
<TouchableOpacity
  accessible={true}
  accessibilityLabel="Submit form"
  accessibilityHint="Double tap to submit your order"
  accessibilityRole="button"
>
  <Text>Submit</Text>
</TouchableOpacity>

// Dynamic state
<Switch
  accessibilityLabel="Dark mode"
  accessibilityState={{ checked: isDarkMode }}
  onValueChange={toggleTheme}
/>

// Group elements
<View accessible={true} accessibilityLabel="Product card: Blue T-Shirt, $29.99">
  <Image ... />
  <Text>Blue T-Shirt</Text>
  <Text>$29.99</Text>
</View>
```

**Announcement for dynamic changes:**
```ts
import { AccessibilityInfo } from 'react-native';

AccessibilityInfo.announceForAccessibility('Item added to cart');
// iOS: uses UIAccessibilityPostNotification
// Android: uses AccessibilityManager.interrupt + announce
```

**Check if screen reader is active:**
```ts
const isScreenReaderEnabled = await AccessibilityInfo.isScreenReaderEnabled();
const subscription = AccessibilityInfo.addEventListener('screenReaderChanged', setIsEnabled);
```

**iOS SwiftUI:**
```swift
Button("Submit") { submitForm() }
  .accessibilityLabel("Submit order")
  .accessibilityHint("Charges your saved payment method")
  .accessibilityAddTraits(.isButton)
```

**Testing:**
```bash
# iOS: Enable VoiceOver in Simulator → Hardware → Toggle Software Keyboard → Accessibility Inspector
# Android: Enable TalkBack in emulator settings
# Automated: @testing-library/react-native uses accessibility labels in queries
screen.getByRole('button', { name: /submit/i })
```

## Gotchas
- `accessible={true}` on a `View` merges all child text into one announcement — don't use it on interactive children
- `accessibilityRole="none"` hides elements from assistive technology; use for decorative elements
- Color contrast ratio must be at least 4.5:1 for normal text (WCAG AA)
- Touch targets must be at least 44×44 pts (iOS) / 48×48 dp (Android); use `hitSlop` to expand without changing layout
- Avoid announcing loading spinners on every re-render; debounce or use `aria-live="polite"` equivalent

## Related
- `react-native-performance-optimization.md`
- `mobile-analytics-patterns.md`
