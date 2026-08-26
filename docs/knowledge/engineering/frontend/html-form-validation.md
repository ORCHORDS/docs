# html-form-validation

**Issue:** Custom validation duplicates browser built-in validation; native API is underused
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Developers reimplement email format checks in JavaScript that the browser already handles natively.

## Pattern / Solution
```html
<form novalidate>
  <input
    type="email"
    required
    minlength="5"
    maxlength="100"
    pattern="[a-z0-9._%+\-]+@[a-z0-9.\-]+\.[a-z]{2,}$"
    autocomplete="email"
  >
  <input type="password" required minlength="8">
  <button type="submit">Submit</button>
</form>
```

```ts
// Constraint Validation API
input.addEventListener('invalid', () => {
  input.setCustomValidity('Please enter a valid email address');
});
input.addEventListener('input', () => input.setCustomValidity(''));

// Check programmatically
form.checkValidity(); // true/false
input.validity.valueMissing; // boolean
```

## Gotchas
- novalidate disables browser UI; you must call checkValidity() manually
- setCustomValidity('') clears the custom error; call it on input/change
- Safari has inconsistent support for some constraint patterns

## Related
- `react-form-handling-react-hook-form.md`
- `react-controlled-vs-uncontrolled.md`
