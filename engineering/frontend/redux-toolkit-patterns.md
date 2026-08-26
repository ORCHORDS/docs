# redux-toolkit-patterns

**Issue:** Legacy Redux boilerplate with action creators and reducers is verbose
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Every feature requires action types, action creators, and reducer switch cases — hundreds of lines for simple state.

## Pattern / Solution
```ts
import { createSlice, createAsyncThunk, configureStore } from '@reduxjs/toolkit';

const fetchPosts = createAsyncThunk('posts/fetch', async () => {
  const res = await fetch('/api/posts');
  return res.json();
});

const postsSlice = createSlice({
  name: 'posts',
  initialState: { items: [], status: 'idle' } as PostsState,
  reducers: {
    addPost: (state, action) => { state.items.push(action.payload); },
  },
  extraReducers: (builder) => {
    builder
      .addCase(fetchPosts.pending, (state) => { state.status = 'loading'; })
      .addCase(fetchPosts.fulfilled, (state, action) => {
        state.status = 'idle';
        state.items = action.payload;
      });
  },
});

const store = configureStore({ reducer: { posts: postsSlice.reducer } });
```

## Gotchas
- RTK uses Immer under the hood; mutate state directly in reducers
- createAsyncThunk handles pending/fulfilled/rejected lifecycle automatically
- RTK Query is a full data-fetching solution built into RTK; consider it over TanStack Query if already using Redux

## Related
- `state-management-patterns.md`
- `react-state-management-zustand.md`
