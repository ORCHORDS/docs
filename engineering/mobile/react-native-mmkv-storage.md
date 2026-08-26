# react-native-mmkv-storage

**Issue:** High-performance synchronous key-value storage for React Native using MMKV
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
`AsyncStorage` is asynchronous and slow (~1 ms/op); MMKV reads are synchronous at ~0.01 ms/op — critical for app startup and Zustand/Redux state hydration.

## Pattern / Solution
```sh
npm install react-native-mmkv
npx pod-install
```

```ts
import { MMKV } from 'react-native-mmkv';

// Global instance (singleton)
export const storage = new MMKV();

// Typed helpers
storage.set('user.token', 'abc123');
const token = storage.getString('user.token'); // string | undefined

storage.set('settings.darkMode', true);
const darkMode = storage.getBoolean('settings.darkMode');

storage.set('cache.count', 42);
const count = storage.getNumber('cache.count');

storage.delete('user.token');
storage.clearAll();

// Encrypted instance
const secureStorage = new MMKV({
  id: 'secure-store',
  encryptionKey: 'my-32-char-secret-key-here!!!!',
});
```

Zustand persistence middleware integration:
```ts
import { StateStorage } from 'zustand/middleware';

const mmkvStorage: StateStorage = {
  getItem: (name) => storage.getString(name) ?? null,
  setItem: (name, value) => storage.set(name, value),
  removeItem: (name) => storage.delete(name),
};
```

## Gotchas
- MMKV is not supported in Expo Go — requires a bare workflow or custom dev client
- Multiple MMKV instances with the same `id` share the same file; use unique IDs per domain
- Encryption key is stored in-memory; combine with `react-native-keychain` for key storage
- On Android, MMKV uses `mmap`; ensure you don't exceed the 4 GB file size limit in embedded use cases

## Related
- `react-native-async-storage.md`
- `react-native-keychain.md`
- `react-native-secure-storage.md`
