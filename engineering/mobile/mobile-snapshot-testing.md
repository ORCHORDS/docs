# mobile-snapshot-testing

**Issue:** Catching unintended UI regressions with snapshot tests in React Native
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Snapshot tests fail on any visual change — intended or not — leading to reflexive `--updateSnapshot` usage that defeats the purpose.

## Pattern / Solution
Use inline snapshots for small, human-readable outputs:
```tsx
import { render } from '@testing-library/react-native';
import Badge from '../src/components/Badge';

it('renders error badge', () => {
  const { toJSON } = render(<Badge variant="error" label="3 errors" />);
  expect(toJSON()).toMatchInlineSnapshot(`
    <View style={{"backgroundColor": "#c62828", "borderRadius": 12, "paddingHorizontal": 8}}>
      <Text style={{"color": "white"}}>3 errors</Text>
    </View>
  `);
});
```

For larger components, use file snapshots but scope them to the diff-sensitive parts:
```tsx
it('product card snapshot', () => {
  const { getByTestId } = render(<ProductCard product={mockProduct} />);
  expect(getByTestId('product-card')).toMatchSnapshot();
});
```

## Gotchas
- Snapshot files should be committed to git — they are the baseline, not generated noise
- Dynamic values (timestamps, random IDs) in snapshots cause constant failures; mock `Date.now()` and `Math.random()`
- `--updateSnapshot` (`-u`) should only be run deliberately; add a CI check that fails if snapshot files are missing
- Snapshot tests do NOT replace accessibility or interaction tests — they only catch structural regressions

## Related
- `mobile-testing-jest.md`
- `mobile-e2e-testing.md`
