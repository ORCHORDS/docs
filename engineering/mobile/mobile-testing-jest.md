# mobile-testing-jest

**Issue:** Unit and integration testing React Native components and logic with Jest and React Native Testing Library
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Testing with Enzyme is deprecated and doesn't support hooks; React Native Testing Library (RNTL) mirrors user interactions and is the recommended approach.

## Pattern / Solution
```sh
npm install --save-dev @testing-library/react-native @testing-library/jest-native
```

`jest.config.js`:
```js
module.exports = {
  preset: 'react-native',
  setupFilesAfterFramework: ['@testing-library/jest-native/extend-expect'],
  transformIgnorePatterns: [
    'node_modules/(?!(react-native|@react-native|react-native-vector-icons)/)',
  ],
};
```

```tsx
// Component test
import { render, screen, fireEvent, waitFor } from '@testing-library/react-native';
import LoginScreen from '../src/screens/LoginScreen';

jest.mock('../src/api/auth', () => ({
  login: jest.fn().mockResolvedValue({ token: 'abc' }),
}));

it('calls login on submit', async () => {
  render(<LoginScreen />);
  fireEvent.changeText(screen.getByPlaceholderText('Email'), 'a@b.com');
  fireEvent.changeText(screen.getByPlaceholderText('Password'), 'pass');
  fireEvent.press(screen.getByText('Log In'));

  await waitFor(() => {
    expect(screen.getByText('Welcome!')).toBeOnTheScreen();
  });
});
```

## Gotchas
- Native modules must be mocked in `__mocks__/` or they throw in the Jest environment (no native bridge)
- `act()` wraps are required around state updates; RNTL's `waitFor` handles this automatically
- `fireEvent.press` does not simulate gestures — use Detox for gesture-based interaction tests
- `transformIgnorePatterns` must whitelist ESM-only packages or Jest fails to parse them

## Related
- `mobile-testing-detox.md`
- `mobile-snapshot-testing.md`
- `react-native-testing-patterns.md`
