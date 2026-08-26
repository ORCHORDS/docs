# xstate-finite-state-machines

**Issue:** Complex async workflows with multiple states and transitions are hard to manage with booleans
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
A multi-step form with isLoading, isError, isSuccess, canGoBack booleans leads to impossible states like isLoading && isSuccess.

## Pattern / Solution
```ts
import { createMachine, assign } from 'xstate';
import { useMachine } from '@xstate/react';

const formMachine = createMachine({
  id: 'form',
  initial: 'idle',
  context: { error: null },
  states: {
    idle:       { on: { SUBMIT: 'loading' } },
    loading: {
      invoke: { src: 'submitForm', onDone: 'success', onError: 'error' },
    },
    success:    { type: 'final' },
    error: {
      entry: assign({ error: ({ event }) => event.error }),
      on: { RETRY: 'loading' },
    },
  },
});

function Form() {
  const [state, send] = useMachine(formMachine, {
    actors: { submitForm: () => fetch('/api/submit') },
  });
  if (state.matches('loading')) return <Spinner />;
  return <button onClick={() => send({ type: 'SUBMIT' })}>Submit</button>;
}
```

## Gotchas
- States are exhaustive; impossible states become compile-time errors
- XState v5 uses actors instead of services; the API changed significantly
- Use the XState visualizer to inspect state diagrams

## Related
- `state-management-patterns.md`
- `redux-toolkit-patterns.md`
