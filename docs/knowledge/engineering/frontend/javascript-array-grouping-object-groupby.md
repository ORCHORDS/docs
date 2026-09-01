# Javascript Array Grouping Object Groupby

## Scope

Replacing hand-rolled reduce-based grouping with the standardized static methods `Object.groupBy` and `Map.groupBy`. Covers the two methods' return types and key coercion rules, when `Map.groupBy` is required rather than `Object.groupBy`, null-prototype safety, and migration from the historical `_`/`lodash` `groupBy` utilities that many codebases still carry. Excludes the earlier `Array.prototype.groupBy` proposal history except where it explains the static-method shape, and excludes database-side `GROUP BY` alternatives.

## Workflow or implementation guidance

Grouping is one of the most frequently reimplemented loops in application code. The pre-standard pattern is a reduce with an accumulator branch, duplicated per project with subtly different null handling. The standardized pair expresses intent directly.

```js
const invoices = [
  { id: 1, status: 'open', amount: 120 },
  { id: 2, status: 'paid', amount: 80 },
  { id: 3, status: 'open', amount: 45 },
];

// Returns a null-prototype object: keys are strings
const byStatus = Object.groupBy(invoices, (inv) => inv.status);
// { open: [{...1}, {...3}], paid: [{...2}] }

// Returns a Map: keys keep their type
const byAmountBucket = Map.groupBy(invoices, (inv) =>
  inv.amount >= 100 ? 'large' : 'small'
);
```

Key coercion is the load-bearing difference. `Object.groupBy` coerces each callback result to a property key: the number `1` becomes `'1'`, and symbols are allowed as keys while anything else goes through `ToString`. `Map.groupBy` uses the value as a `Map` key with `SameValueZero` semantics, so `0` stays `0`, objects stay distinct, and `NaN` groups correctly (all `NaN` values share one group). Whenever the grouping key is not a string, number-like, or symbol — or when collisions across types are possible (`1` vs `'1'`) — use `Map.groupBy`.

```js
// Object.groupBy silently merges 1 and '1' into the same bucket
const mixed = [{ k: 1 }, { k: '1' }];
Object.groupBy(mixed, (x) => x.k);  // one bucket, key "1"
Map.groupBy(mixed, (x) => x.k);     // two distinct buckets
```

The object returned by `Object.groupBy` has no `Object.prototype`, so inherited members cannot collide with group names — `byStatus.toString` is `undefined` rather than the inherited function, and a group named `'constructor'` does not shadow anything. That property also means code doing `Object.keys(result).map(...)` is the safe iteration form, while `result.hasOwnProperty` fails because even `hasOwnProperty` is absent; use `Object.hasOwn(result, key)` instead.

Index access: the callback receives `(element, index)` like the other array iteration callbacks, enabling positional grouping (chunking by index) without a closure counter.

```js
const rows = [...Array(97).keys()];
const pages = Object.groupBy(rows, (_, i) => Math.floor(i / 10)); // page 0..9
```

Migration workflow: find `groupBy` imports from utility libraries, confirm each call site's key type, replace with the built-in, and delete the dependency. Two behavioral differences to check at each site. First, historical utility `groupBy` accepted a string shorthand (`_.groupBy(users, 'role')`) that the built-in does not — convert to `(u) => u.role`. Second, utility versions returned plain objects with prototype; downstream `for...in` loops over plain objects now see no inherited members, which is usually the fix for a latent bug but changes behavior for code relying on prototype members.

Typing in TypeScript: the result of `Object.groupBy` is `{ [key: string]: T[] }` and `Map.groupBy` is `Map<K, T[]>`; when the key space is a closed union, assert or map into a typed record at the boundary rather than casting throughout the codebase.

## Controls

- Key callback returns the group key; decide string-versus-arbitrary-type first, because that choice selects `Object.groupBy` versus `Map.groupBy`.
- Iterate `Object.groupBy` results with `Object.keys`/`Object.entries`/`Object.values`; test membership with `Object.hasOwn`.
- Preserve insertion order expectations: both results iterate groups in first-encounter order, which makes deterministic UI rendering (grouped lists) straightforward.
- Empty input yields an empty object or empty `Map`; no special-casing needed.
- Lint rule banning new `reduce`-based grouping implementations once the built-in is available in the support floor.

## Validation evidence

- Unit tests covering: empty array, single group, key type collisions (`1` vs `'1'`), `NaN` keys under `Map.groupBy`, and a group literally named `'constructor'` or `'toString'` to prove the null-prototype behavior.
- Snapshot the grouped output shape for a representative dataset to catch accidental key coercion changes during migration.
- Run the migration's before/after comparison against the utility-library output on the real production dataset once, in a script, and diff JSON serializations.
- Verify engine support in the browser support matrix (`Object.groupBy` and `Map.groupBy` are ES2024); confirm the build target transpiles or the support floor includes them.

## Failure modes and correction

- Group keys silently coerced to strings by `Object.groupBy`, merging distinct numeric and string keys: switch to `Map.groupBy` or normalize keys to one type upstream.
- `result.hasOwnProperty(...)` throws or is `undefined`: the result object has a null prototype. Use `Object.hasOwn(result, key)`.
- Grouping objects or arrays as keys with `Object.groupBy` produces `'[object Object]'` for every item — one giant bucket. Use `Map.groupBy` with the object keys, or group by a primitive field.
- Utility string-shorthand call sites (`groupBy(items, 'status')`) break because the built-in callback receives the item, not a path resolver. Rewrite as an explicit accessor.
- `for...in` over the grouped object no longer yields inherited members (previously it could yield nothing extra anyway, but utility objects did inherit): migrate to `Object.keys` for explicitness.
- Sparse arrays: the methods skip holes like other array iteration methods; if holes are meaningful in the data model, densify first.

## Limitations

- No transitive aggregation: the methods group only; sums, counts, and averages still need a follow-up pass over each bucket.
- The callback receives element and index but not the source array; the historical three-argument utility callbacks that also received the collection need a wrapper.
- `Object.groupBy` output keys are always strings (or symbols); numeric key fidelity requires `Map.groupBy`.
- No built-in multi-level grouping (group by A then by B); compose two calls or reduce over the first-level buckets.
- Requires a runtime with ES2024 static methods; on older targets, a small polyfill or the retained utility dependency must stay until the support floor moves.

## Canonical sources

- TC39, Array Grouping proposal: https://tc39.es/proposal-array-grouping/
- MDN, `Object.groupBy`: https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Global_Objects/Object/groupBy
- MDN, `Map.groupBy`: https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Global_Objects/Map/groupBy
