# react-native-testing-patterns

**Issue:** Testing React Native components and logic effectively
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
React Native tests run in Node.js (Jest + JSDOM or RN's test environment), which mocks native modules. Without a clear strategy, tests become brittle mocks or miss real user interactions.

## Pattern / Solution
**Unit test setup (Jest + React Native Testing Library):**
```bash
npx expo install jest-expo @testing-library/react-native
```

```json
// package.json
{
  "jest": {
    "preset": "jest-expo",
    "setupFilesAfterFramework": ["@testing-library/react-native/extend-expect"]
  }
}
```

**Component test:**
```tsx
import { render, screen, fireEvent, waitFor } from '@testing-library/react-native';

describe('LoginForm', () => {
  it('shows error on empty submit', async () => {
    render(<LoginForm onSuccess={jest.fn()} />);
    fireEvent.press(screen.getByRole('button', { name: /sign in/i }));
    await waitFor(() => {
      expect(screen.getByText(/email is required/i)).toBeTruthy();
    });
  });

  it('calls onSuccess with token', async () => {
    const mockApi = jest.spyOn(api, 'login').mockResolvedValue({ token: 'abc' });
    const onSuccess = jest.fn();
    render(<LoginForm onSuccess={onSuccess} />);
    fireEvent.changeText(screen.getByLabelText(/email/i), 'test@example.com');
    fireEvent.changeText(screen.getByLabelText(/password/i), 'secret');
    fireEvent.press(screen.getByRole('button', { name: /sign in/i }));
    await waitFor(() => expect(onSuccess).toHaveBeenCalledWith('abc'));
  });
});
```

**Mock native modules:**
```ts
// __mocks__/expo-secure-store.ts
export const getItemAsync = jest.fn();
export const setItemAsync = jest.fn();
export const deleteItemAsync = jest.fn();
```

**E2E with Maestro:**
```yaml
# .maestro/login_flow.yaml
appId: com.example.myapp
---
- launchApp
- tapOn: "Email"
- inputText: "user@example.com"
- tapOn: "Password"
- inputText: "secret123"
- tapOn: "Sign In"
- assertVisible: "Welcome back"
```

## Gotchas
- `fireEvent` is synchronous; always use `waitFor` for async state updates
- Native modules that aren't mocked cause "native module not found" errors in Jest — add a `__mocks__` file
- `userEvent` from RTNAL is closer to real interactions than `fireEvent` but requires `@testing-library/react-native` >= 12
- Maestro requires a running simulator/emulator; integrate in CI with `maestro cloud` or a GitHub Actions runner with a connected device
- Snapshot tests on RN components are fragile — prefer interaction-based assertions

## Related
- `react-native-expo-setup.md`
- `mobile-crash-reporting.md`
