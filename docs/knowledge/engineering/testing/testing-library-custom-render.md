# testing-library-custom-render

**Issue:** Wrapping components with providers (Redux, Router, Theme) in every test
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Every test has boilerplate wrapping the component in `<Provider>`, `<Router>`, `<ThemeProvider>`. This gets unmaintainable across hundreds of tests.

## Pattern / Solution
```ts
// src/test/render.tsx
import { render, RenderOptions } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import { ThemeProvider } from "../theme";

function AllProviders({ children }: { children: React.ReactNode }) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return (
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <ThemeProvider>{children}</ThemeProvider>
      </MemoryRouter>
    </QueryClientProvider>
  );
}

function customRender(ui: React.ReactElement, options?: RenderOptions) {
  return render(ui, { wrapper: AllProviders, ...options });
}

export * from "@testing-library/react";
export { customRender as render };
```

Import from your custom render in tests:
```ts
import { render, screen } from "../test/render";
```

## Gotchas
- Create a fresh `QueryClient` per test to avoid state leak
- `retry: false` prevents silent 3x retry delays in tests
- Override wrapper per-test for special cases via `options.wrapper`

## Related
- `testing-library-queries.md`
- `react-testing-patterns.md`
