# react-native-async-storage

**Issue:** Persisting simple key-value data asynchronously in React Native
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
The built-in `AsyncStorage` was removed from the RN core in 0.60; apps must use `@react-native-async-storage/async-storage` with size limits in mind.

## Pattern / Solution
```sh
npm install @react-native-async-storage/async-storage
npx pod-install
```

```ts
import AsyncStorage from '@react-native-async-storage/async-storage';

// Single item
await AsyncStorage.setItem('theme', 'dark');
const theme = await AsyncStorage.getItem('theme'); // string | null

// Object — must stringify
await AsyncStorage.setItem('user', JSON.stringify({ id: 1, name: 'Alice' }));
const raw = await AsyncStorage.getItem('user');
const user = raw ? JSON.parse(raw) : null;

// Batch operations (atomic)
await AsyncStorage.multiSet([
  ['key1', 'value1'],
  ['key2', 'value2'],
]);
const pairs = await AsyncStorage.multiGet(['key1', 'key2']);

// Remove
await AsyncStorage.removeItem('theme');
await AsyncStorage.clear(); // wipes everything
```

## Gotchas
- Default Android limit is 6 MB; increase via `AsyncStorage.setMaxSize()` or use SQLite for larger datasets
- `getItem` returns `null` (not `undefined`) when a key does not exist
- Storing large JSON blobs blocks the bridge; prefer MMKV or SQLite for high-frequency writes
- `clear()` deletes **all** AsyncStorage data including keys set by third-party libraries

## Related
- `react-native-mmkv-storage.md`
- `mobile-data-storage.md`
