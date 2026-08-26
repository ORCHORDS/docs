# TypeScript Strict Mode Guide

## What is Strict Mode?

TypeScript's strict mode enables a set of compiler options that catch common programming errors and help write more robust code. When enabled, these checks prevent undefined behavior and make your codebase more predictable.

## Key Strict Mode Options

### strictNullChecks
Enables strict null checking, preventing `null` and `undefined` from being assigned to variables without explicit handling.

```typescript
// Without strictNullChecks - this compiles fine
let name: string = null; // ❌ Would error with strictNullChecks enabled

// With proper handling
let name: string | null = null;
if (name !== null) {
  console.log(name.toUpperCase()); // ✅ Safe
}
```

### noImplicitAny
Prevents TypeScript from inferring `any` type when it cannot infer the type.

```typescript
// Without noImplicitAny - this compiles
function greet(user) { // 'user' implicitly has 'any' type
  return `Hello ${user}`;
}

// With explicit typing
function greet(user: string) {
  return `Hello ${user}`;
}
```

### Exhaustive Checks
Ensures all cases are handled in union types and switch statements.

```typescript
type Status = 'pending' | 'resolved' | 'rejected';

// Without exhaustive check - this compiles
function handleStatus(status: Status) {
  switch (status) {
    case 'pending': return 'Loading...';
    case 'resolved': return 'Success!';
    // Missing 'rejected' case
  }
}

// With exhaustive check using never type
function handleStatus(status: Status): string {
  switch (status) {
    case 'pending': return 'Loading...';
    case 'resolved': return 'Success!';
    case 'rejected': return 'Error!';
    default:
      const _exhaustiveCheck: never = status; // ✅ Error if missing cases
      return _exhaustiveCheck;
  }
}
```

### Branded Types
Create type-safe wrappers to prevent accidental mixing of similar types.

```typescript
// Branded types for type safety
type UserId = string & { __brand: 'userId' };
type ProductId = string & { __brand: 'productId' };

function getUserById(id: UserId) { /* ... */ }
function getProductById(id: ProductId) { /* ... */ }

const userId: UserId = 'user123'
