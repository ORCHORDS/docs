# faker-js-test-data

**Issue:** Generating realistic, varied test data with Faker.js
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Hardcoded test data like `"Alice"`, `"test@test.com"`, `"123"` makes it harder to spot assumptions in code that only work for specific values.

## Pattern / Solution
```bash
npm install -D @faker-js/faker
```

```ts
import { faker } from "@faker-js/faker";

// Seed for deterministic output in specific tests
faker.seed(12345);

const user = {
  id: faker.string.uuid(),
  name: faker.person.fullName(),
  email: faker.internet.email(),
  phone: faker.phone.number(),
  address: {
    street: faker.location.streetAddress(),
    city: faker.location.city(),
    country: faker.location.countryCode(),
  },
  bio: faker.lorem.paragraph(),
  avatar: faker.image.avatar(),
};

// Locale-specific data
faker.locale = "de";
const germanName = faker.person.fullName();
```

Common generators:
- `faker.string.uuid()`, `faker.string.alphanumeric(8)`
- `faker.date.between({ from, to })`, `faker.date.recent()`
- `faker.number.int({ min, max })`, `faker.number.float()`

## Gotchas
- Faker v8+ uses `@faker-js/faker` — not `faker` package
- Without seed, output changes each run — good for general tests
- With seed, output is deterministic — good for snapshot tests

## Related
- `factory-pattern-tests.md`
- `test-data-builders.md`
