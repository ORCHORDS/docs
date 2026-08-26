# react-controlled-vs-uncontrolled

**Issue:** Mixing controlled and uncontrolled input modes causes React warnings and lost state
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
"A component is changing an uncontrolled input to be controlled" warning appears when value switches from undefined to a string.

## Pattern / Solution
```tsx
// Controlled: React owns state
const [value, setValue] = useState('');
<input value={value} onChange={e => setValue(e.target.value)} />

// Uncontrolled: DOM owns state
const ref = useRef(null);
<input defaultValue="initial" ref={ref} />
// Access: ref.current.value

// Never switch modes; initialize to '' not undefined
const [value, setValue] = useState(''); // not useState(undefined)
```

## Gotchas
- value={undefined} makes input uncontrolled; value={''} makes it controlled
- File inputs are always uncontrolled
- react-hook-form uses uncontrolled inputs for performance by default

## Related
- `react-form-handling-react-hook-form.md`
- `html-form-validation.md`
