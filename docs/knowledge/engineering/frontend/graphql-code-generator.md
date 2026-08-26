# graphql-code-generator

**Issue:** GraphQL queries and mutations lack TypeScript types, leading to runtime errors
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Accessing response.data.user.profile.avatar crashes because the field name changed server-side with no compile-time warning.

## Pattern / Solution
```yaml
# codegen.ts
import type { CodegenConfig } from '@graphql-codegen/cli';
const config: CodegenConfig = {
  schema: 'http://localhost:4000/graphql',
  documents: ['src/**/*.tsx'],
  generates: {
    './src/gql/': {
      preset: 'client',
      plugins: [],
    },
  },
};
export default config;
```

```ts
// Use generated types
import { useQuery } from '@apollo/client';
import { graphql } from './gql';

const GET_USER = graphql(`
  query GetUser($id: ID!) {
    user(id: $id) { id name email }
  }
`);

const { data } = useQuery(GET_USER, { variables: { id: '1' } });
// data.user.name is string | undefined — fully typed
```

## Gotchas
- Run codegen in watch mode during development: `graphql-codegen --watch`
- The client preset generates per-operation types; no need for separate type files
- Fragment co-location improves performance by requesting only needed fields

## Related
- `apollo-client-patterns.md`
- `typescript-react-patterns.md`
