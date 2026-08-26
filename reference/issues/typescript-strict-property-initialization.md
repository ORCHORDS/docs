# typescript-strict-property-initialization

**Issue:** With `strictPropertyInitialization` enabled, class properties not initialized in the constructor cause a compile error; using `!` (definite assignment assertion) silences it but hides real bugs
**Date:** 2026-08-11
**Status:** documented

## Symptom
`tsc` error: `Property 'db' has no initializer and is not definitely assigned in the constructor`. Developer adds `!` suffix (`db!: Database`) to silence it. At runtime, accessing `this.db` before async initialization is called throws "Cannot read properties of undefined".

## Root cause
`strictPropertyInitialization` ensures every declared property is assigned in the constructor. The `!` definite assignment assertion tells TypeScript "I guarantee this will be assigned" — but TypeScript doesn't verify the guarantee. It is commonly misused to skip proper initialization.

## Fix
Initialize in the constructor or use an optional type:
```ts
// Wrong — ! suppresses error without fixing root cause
class Service {
  db!: Database;
  async init() { this.db = await connect(); }
}

// Correct — use static factory or constructor injection
class Service {
  constructor(private db: Database) {}
  static async create(): Promise<Service> {
    return new Service(await connect());
  }
}
```

## Detection
```
grep -rn "!:" src/ --include="*.ts" | grep -v "// ok\|// intentional"
```

## Related
- `typescript-satisfies-vs-as.md`
