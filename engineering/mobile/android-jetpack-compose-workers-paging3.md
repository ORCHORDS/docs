# Android Jetpack Compose + Paging 3 with Cloudflare Workers

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

You have a large, frequently updated dataset served from a Cloudflare Workers API backed by D1. Your Jetpack Compose UI must scroll infinitely through it with proper load states, offline caching via Room, and graceful error handling.

## Context

- Android (minSdk 26), Kotlin 2.0, Jetpack Compose BOM 2026.04
- Paging 3 (`androidx.paging:paging-compose:3.3.*`)
- Room for local caching (`androidx.room:room-runtime:2.7.*`)
- Retrofit 2.11 + kotlinx.serialization for network calls
- Cloudflare Workers endpoint returning cursor-paginated JSON from D1
- Keyset pagination with `WHERE id > ? ORDER BY id LIMIT 20` for stable cursors

## WorkersPagingSource

```kotlin
// data/paging/WorkersPagingSource.kt
package com.example.app.data.paging

import androidx.paging.PagingSource
import androidx.paging.PagingState
import com.example.app.data.api.WorkersApi
import com.example.app.data.model.Item
import retrofit2.HttpException
import java.io.IOException

class WorkersPagingSource(
    private val api: WorkersApi,
    private val query: String,
) : PagingSource<String, Item>() {

    override fun getRefreshKey(state: PagingState<String, Item>): String? = null

    override suspend fun load(params: LoadParams<String>): LoadResult<String, Item> {
        return try {
            val cursor = params.key // null on first load
            val response = api.getItems(
                query = query,
                cursor = cursor,
                limit = params.loadSize,
            )
            LoadResult.Page(
                data = response.items,
                prevKey = null, // only forward pagination
                nextKey = response.nextCursor,
            )
        } catch (e: HttpException) {
            // 4xx: stop pagination — do not retry
            if (e.code() in 400..499) LoadResult.Error(e)
            else LoadResult.Error(e)
        } catch (e: IOException) {
            LoadResult.Error(e)
        }
    }
}
```

## Cloudflare Workers Paginated Endpoint

```typescript
// worker/src/items.ts
import { D1Database } from '@cloudflare/workers-types';

export async function handleItems(req: Request, db: D1Database): Promise<Response> {
  const url = new URL(req.url);
  const cursor = url.searchParams.get('cursor'); // last seen id
  const limit = Math.min(parseInt(url.searchParams.get('limit') ?? '20', 10), 100);
  const query = url.searchParams.get('query') ?? '';

  const stmt = cursor
    ? db.prepare(
        `SELECT id, title, body, created_at FROM items
         WHERE id > ? AND title LIKE ?
         ORDER BY id
         LIMIT ?`
      ).bind(cursor, `%${query}%`, limit)
    : db.prepare(
        `SELECT id, title, body, created_at FROM items
         WHERE title LIKE ?
         ORDER BY id
         LIMIT ?`
      ).bind(`%${query}%`, limit);

  const { results } = await stmt.all();

  const nextCursor =
    results.length === limit ? String(results[results.length - 1].id) : null;

  return Response.json({ items: results, nextCursor });
}
```

## RemoteMediator (Network + Room Cache)

```kotlin
// data/paging/WorkersRemoteMediator.kt
package com.example.app.data.paging

import androidx.paging.*
import androidx.room.withTransaction
import com.example.app.data.api.WorkersApi
import com.example.app.data.db.AppDatabase
import com.example.app.data.db.RemoteKey
import com.example.app.data.model.Item
import retrofit2.HttpException
import java.io.IOException

@OptIn(ExperimentalPagingApi::class)
class WorkersRemoteMediator(
    private val api: WorkersApi,
    private val db: AppDatabase,
) : RemoteMediator<String, Item>() {

    override suspend fun load(
        loadType: LoadType,
        state: PagingState<String, Item>,
    ): MediatorResult {
        val cursor: String? = when (loadType) {
            LoadType.REFRESH -> null
            LoadType.PREPEND -> return MediatorResult.Success(endOfPaginationReached = true)
            LoadType.APPEND -> {
                val key = db.remoteKeyDao().getKey() ?: return MediatorResult.Success(true)
                key.nextCursor ?: return MediatorResult.Success(true)
            }
        }

        return try {
            val response = api.getItems(
                query = "",
                cursor = cursor,
                limit = state.config.pageSize,
            )
            db.withTransaction {
                if (loadType == LoadType.REFRESH) {
                    db.itemDao().clearAll()
                    db.remoteKeyDao().clearAll()
                }
                db.itemDao().insertAll(response.items)
                db.remoteKeyDao().insert(RemoteKey(nextCursor = response.nextCursor))
            }
            MediatorResult.Success(endOfPaginationReached = response.nextCursor == null)
        } catch (e: HttpException) {
            if (e.code() in 400..499) MediatorResult.Success(endOfPaginationReached = true)
            else MediatorResult.Error(e)
        } catch (e: IOException) {
            MediatorResult.Error(e)
        }
    }
}
```

## Jetpack Compose LazyColumn with Load States

```kotlin
// ui/ItemListScreen.kt
@Composable
fun ItemListScreen(viewModel: ItemListViewModel = hiltViewModel()) {
    val items = viewModel.items.collectAsLazyPagingItems()

    LazyColumn(modifier = Modifier.fillMaxSize()) {
        items(count = items.itemCount, key = items.itemKey { it.id }) { index ->
            val item = items[index]
            if (item != null) ItemCard(item)
        }

        when {
            items.loadState.refresh is LoadState.Loading -> item {
                Box(Modifier.fillParentMaxSize(), contentAlignment = Alignment.Center) {
                    CircularProgressIndicator()
                }
            }
            items.loadState.refresh is LoadState.Error -> item {
                val e = items.loadState.refresh as LoadState.Error
                ErrorCard(message = e.error.message ?: "Unknown error") {
                    items.retry()
                }
            }
            items.loadState.append is LoadState.Loading -> item {
                CircularProgressIndicator(Modifier.align(Alignment.CenterHorizontally))
            }
            items.loadState.append is LoadState.Error -> item {
                val e = items.loadState.append as LoadState.Error
                // 4xx = do not offer retry; 5xx = offer retry
                val is4xx = (e.error as? HttpException)?.code() in 400..499
                if (!is4xx) RetryButton { items.retry() }
            }
        }
    }
}
```

## Anti-patterns

- **Using offset-based pagination (`LIMIT ? OFFSET ?`)** — unstable under inserts; rows shift, causing duplicates or skipped items. Use keyset pagination.
- **Returning the full dataset and paginating client-side** — D1 rows can reach millions; always paginate at the database query level.
- **Not differentiating 4xx vs 5xx** — 404/400 errors indicate bad client state and retrying wastes quota; stop pagination on 4xx.
- **Calling `items.retry()` automatically on error** — respect the user's intent; surface an error UI and let the user trigger retry.

## Gotchas

- `PagingSource.getRefreshKey()` returning `null` causes a full reload from the start on config change — implement it to return the anchor position's `id` if you want to resume at the same scroll position.
- Room's `PagingSource` emits on every DB write; if your `RemoteMediator` inserts frequently, debounce your ViewModel flow to avoid excessive recompositions.
- D1 `LIKE` with a leading wildcard (`%term`) cannot use an index; add a full-text search index with `CREATE VIRTUAL TABLE items_fts USING fts5(title)` for large datasets.
- Paging 3's `pageSize` in `PagingConfig` and the `limit` sent to the Worker must be aligned; mismatches cause under/over-fetching.

## Verification

1. Scroll to the bottom of the list; verify a new network request fires with the last item's `id` as `cursor`.
2. Kill the network; observe cached Room items still display.
3. Simulate a 500 from the Worker; verify a retry button appears.
4. Simulate a 400 from the Worker; verify no retry button and pagination stops.
5. Run `adb shell dumpsys meminfo <package>` — heap should not grow unboundedly during long scroll sessions.

## Related

- `documentation/workers/d1-keyset-pagination.md`
- `documentation/categories/mobile/android-room-caching.md`
- `documentation/workers/error-codes.md`

## Sources

- https://developers.cloudflare.com/d1/
- https://developer.android.com/topic/libraries/architecture/paging/v3-overview
- https://developer.android.com/jetpack/compose/lists
