# typescript-generic-components

**Issue:** Components that work with multiple data shapes require proper generics to avoid type casting
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
A data table component casts row data to any to access columns, losing type safety.

## Pattern / Solution
```tsx
interface Column<T> {
  key: keyof T;
  header: string;
  render?: (value: T[keyof T], row: T) => React.ReactNode;
}

function DataTable<T extends { id: string | number }>({
  data,
  columns,
}: {
  data: T[];
  columns: Column<T>[];
}) {
  return (
    <table>
      <thead>
        <tr>{columns.map(c => <th key={String(c.key)}>{c.header}</th>)}</tr>
      </thead>
      <tbody>
        {data.map(row => (
          <tr key={row.id}>
            {columns.map(c => (
              <td key={String(c.key)}>
                {c.render ? c.render(row[c.key], row) : String(row[c.key])}
              </td>
            ))}
          </tr>
        ))}
      </tbody>
    </table>
  );
}
```

## Gotchas
- T extends object prevents primitives from being passed
- Use keyof T for type-safe property access
- JSX with generics requires the trailing comma: <T,>() => {} in .tsx files

## Related
- `typescript-react-patterns.md`
- `typescript-discriminated-unions-ui.md`
