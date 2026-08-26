# apollo-client-patterns

**Issue:** GraphQL queries need caching, optimistic updates, and real-time subscriptions
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
REST-style fetch calls for GraphQL queries miss out on normalised caching and type safety.

## Pattern / Solution
```ts
import { ApolloClient, InMemoryCache, gql, useQuery, useMutation } from '@apollo/client';

const client = new ApolloClient({
  uri: '/graphql',
  cache: new InMemoryCache(),
});

const GET_POSTS = gql`
  query GetPosts($limit: Int!) {
    posts(limit: $limit) { id title author { name } }
  }
`;

function Posts() {
  const { data, loading } = useQuery(GET_POSTS, { variables: { limit: 10 } });
  return loading ? <Spinner /> : <PostList posts={data.posts} />;
}

// Optimistic update
const [updatePost] = useMutation(UPDATE_POST, {
  optimisticResponse: { updatePost: { __typename: 'Post', id, title: newTitle } },
});
```

## Gotchas
- Normalised cache requires __typename and id on every queried object
- fetchPolicy: 'cache-and-network' returns cached data immediately then updates from network
- Apollo generates TypeScript types from schema with graphql-code-generator

## Related
- `graphql-code-generator.md`
- `swr-vs-react-query.md`
