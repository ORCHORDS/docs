# prototype-pollution-prevention

**Issue:** Prototype pollution in JavaScript allows attackers to inject properties into Object.prototype, bypassing security checks
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Deep merge, clone, and path-setting utilities that process user-supplied keys can be tricked with `__proto__`, `constructor`, or `prototype` keys to inject properties into the global object prototype, affecting all objects in the process.

## Pattern / Solution
```javascript
// Attack payload
const payload = JSON.parse('{"__proto__": {"isAdmin": true}}');
merge({}, payload); // now ({}).isAdmin === true everywhere

// SECURE merge — skip dangerous keys
function safeMerge(target, source) {
  for (const key of Object.keys(source)) {
    if (key === '__proto__' || key === 'constructor' || key === 'prototype') continue;
    if (typeof source[key] === 'object' && source[key] !== null) {
      target[key] = target[key] || {};
      safeMerge(target[key], source[key]);
    } else {
      target[key] = source[key];
    }
  }
  return target;
}

// SECURE — use Object.create(null) for accumulator objects
const store = Object.create(null); // no prototype chain

// SECURE — use Map instead of plain objects for user-keyed data
const store = new Map();
```
```javascript
// Freeze Object.prototype in server entry point
Object.freeze(Object.prototype);
```

## Gotchas
- `lodash.merge` < 4.17.12 was vulnerable — update.
- `JSON.parse` itself is safe; the vulnerability is in how the parsed object is processed.
- Freezing Object.prototype can break third-party libraries that add polyfills to it.
- Check all `_.set`, `_.merge`, `deepmerge`, `extend` calls that handle user input.

## Related
- `insecure-deserialization-java.md`
- `xss-deep-2026.md`
