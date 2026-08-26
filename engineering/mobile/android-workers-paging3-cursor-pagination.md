# Android Paging 3 with Cloudflare Workers Cursor-Based Pagination

- **Date:** 2026-08-23
- **Author:** example.com
- **Status:** production

## Symptom / Use-case
Infinite-scroll lists in Android apps backed by Cloudflare Workers + D1 APIs stall or duplicate items when users scroll quickly, because naive offset pagination drifts as new rows are inserted server-side.

## Context
Cloudflare Workers expose a cursor-encoded pagination API (opaque base64 token wrapping a row ID or timestamp). Android Paging 3's `RemoteMediator` bridges the network boundary, persists pages into Room, and drives `LazyColumn` via a `PagingData` flow. Cursor tokens eliminate the offset-drift problem and are safe to pass through Cloudflare's edge cache.

## Cloudflare Worker — Cursor API
```typescript
// workers/api/items.ts
import { Env } from './types';

interface CursorPayload { id: number; ts: number }

function encodeCursor(p: CursorPayload): string {
  return btoa(JSON.stringify(p));
}
function decodeCursor(token: string): CursorPayload {
  return JSON.parse(atob(token));
}

export async function handleItems(req: Request, env: Env): Promise<Response> {
  const url = new URL(req.url);
  const limit = Math.min(Number(url.searchParams.get('limit') ?? '25'), 100);
  const cursorToken = url.searchParams.get('cursor');

  let query: string;
  let params: (string | number)[];

  if (cursorToken) {
    const { id } = decodeCursor(cursorToken);
    query = `SELECT id, title, created_at FROM items WHERE id < ? ORDER BY id DESC LIMIT ?`;
    params = [id, limit + 1];
  } else {
    query = `SELECT id, title, created_at FROM items ORDER BY id DESC LIMIT ?`;
    params = [limit + 1];
  }

  const { results } = await env.DB.prepare(query).bind(...params).all<{
    id: number; title: string; created_at: string
  }>();

  const hasMore = results.length > limit;
  const items = hasMore ? results.slice(0, limit) : results;
  const nextCursor = hasMore
    ? encodeCursor({ id: items[items.length - 1].id, ts: Date.now() })
    : null;

  return Response.json({ items, nextCursor }, {
    headers: { 'Cache-Control': 'private, max-age=0' },
  });
}
```

## Room Entity and DAO
```kotlin
// data/local/ItemEntity.kt
@Entity(tableName = "items")
data class ItemEntity(
    @PrimaryKey val id: Long,
    val title: String,
    val createdAt: String,
)

@Entity(tableName = "remote_keys")
data class RemoteKey(
    @PrimaryKey val itemId: Long,
    val prevCursor: String?,
    val nextCursor: String?,
)

@Dao
interface ItemDao {
    @Query("SELECT * FROM items ORDER BY id DESC")
    fun pagingSource(): PagingSource<Int, ItemEntity>

    @Insert(onConflict = OnConflictStrategy.REPLACE)
    suspend fun insertAll(items: List<ItemEntity>)

    @Query("DELETE FROM items")
    suspend fun clearAll()
}

@Dao
interface RemoteKeyDao {
    @Insert(onConflict = OnConflictStrategy.REPLACE)
    suspend fun insertAll(keys: List<RemoteKey>)

    @Query("SELECT * FROM remote_keys WHERE itemId = :itemId")
    suspend fun keyForItem(itemId: Long): RemoteKey?

    @Query("DELETE FROM remote_keys")
    suspend fun clearAll()
}
```

## RemoteMediator Implementation
```kotlin
// data/paging/ItemRemoteMediator.kt
@OptIn(ExperimentalPagingApi::class)
class ItemRemoteMediator(
    private val api: WorkersApiService,
    private val db: AppDatabase,
) : RemoteMediator<Int, ItemEntity>() {

    override suspend fun initialize() = InitializeAction.LAUNCH_INITIAL_REFRESH

    override suspend fun load(
        loadType: LoadType,
        state: PagingState<Int, ItemEntity>,
    ): MediatorResult = withContext(Dispatchers.IO) {
        val cursor: String? = when (loadType) {
            LoadType.REFRESH -> null
            LoadType.PREPEND -> return@withContext MediatorResult.Success(endOfPaginationReached = true)
            LoadType.APPEND -> {
                val lastItem = state.lastItemOrNull()
                    ?: return@withContext MediatorResult.Success(endOfPaginationReached = true)
                db.remoteKeyDao().keyForItem(lastItem.id)?.nextCursor
                    ?: return@withContext MediatorResult.Success(endOfPaginationReached = true)
            }
        }

        runCatching {
            val response = api.getItems(
                limit = state.config.pageSize,
                cursor = cursor,
            )
            db.withTransaction {
                if (loadType == LoadType.REFRESH) {
                    db.itemDao().clearAll()
                    db.remoteKeyDao().clearAll()
                }
                db.itemDao().insertAll(response.items.map { it.toEntity() })
                db.remoteKeyDao().insertAll(response.items.map { item ->
                    RemoteKey(
                        itemId = item.id,
                        prevCursor = cursor,
                        nextCursor = response.nextCursor,
                    )
                })
            }
            MediatorResult.Success(endOfPaginationReached = response.nextCursor == null)
        }.getOrElse { MediatorResult.Error(it) }
    }
}
```

## ViewModel and UI Wiring
```kotlin
// ui/ItemsViewModel.kt
@HiltViewModel
class ItemsViewModel @Inject constructor(repo: ItemRepository) : ViewModel() {
    val items: Flow<PagingData<ItemUiModel>> = repo.itemPager()
        .map { pagingData -> pagingData.map(ItemEntity::toUiModel) }
        .cachedIn(viewModelScope)
}

// ui/ItemsScreen.kt  (Compose)
@Composable
fun ItemsScreen(vm: ItemsViewModel = hiltViewModel()) {
    val lazyItems = vm.items.collectAsLazyPagingItems()
    LazyColumn {
        items(lazyItems.itemCount, key = lazyItems.itemKey { it.id }) { index ->
            lazyItems[index]?.let { ItemRow(it) }
        }
        lazyItems.apply {
            when (loadState.append) {
                is LoadState.Loading -> item { CircularProgressIndicator() }
                is LoadState.Error   -> item { RetryButton(::retry) }
                else -> Unit
            }
        }
    }
}
```

## Anti-patterns
- Using `offset`/`limit` for large datasets — rows shift as new content is inserted, causing duplicates or gaps.
- Decoding and incrementing the cursor client-side — treat the token as opaque; only the Worker knows its structure.
- Caching the cursor-paginated response at Cloudflare's edge — page tokens are session-specific; always set `Cache-Control: private`.
- Clearing Room on every `APPEND` load type — only clear on `REFRESH` to preserve the local cache.
- Not handling `LoadType.PREPEND` — Paging 3 calls it for certain configurations; returning `endOfPaginationReached = true` prevents infinite loops.

## Gotchas
- `cachedIn(viewModelScope)` is mandatory — without it, the `PagingData` stream is re-collected on every recomposition.
- `state.lastItemOrNull()` can return null even on `APPEND` when the initial page was empty; guard accordingly.
- D1's row ordering must match the cursor sort key exactly; mixed `ORDER BY` directions cause the cursor to skip rows.
- Large `pageSize` in `PagingConfig` increases Worker D1 query time; keep it ≤ 50 for sub-100 ms p95.

## Verification
1. Open the app on a slow network profile (Android Emulator → Network throttle: Regular 3G).
2. Scroll to the bottom of the list and confirm the next page loads without duplicates.
3. Insert a new row server-side while the list is visible; pull-to-refresh should prepend it without reordering existing items.
4. Kill the process and re-open — Room should serve the cached first page instantly before the network refresh completes.
5. Assert `RemoteKey` rows via `adb shell` + Room's test helpers that `nextCursor` is non-null after page 1.

## Related
- [mobile-offline-first-sync-cloudflare-queues.md](mobile-offline-first-sync-cloudflare-queues.md)
- [android-room-database.md](android-room-database.md)
- [android-coroutines.md](android-coroutines.md)
- [android-retrofit-patterns.md](android-retrofit-patterns.md)
- [cloudflare-kv-read-latency-mobile-highlatency-vs-desktop.md](cloudflare-kv-read-latency-mobile-highlatency-vs-desktop.md)

## Sources
- Android Paging 3 RemoteMediator docs: https://developer.android.com/topic/libraries/architecture/paging/v3-network-db
- Cloudflare D1 pagination best practices: https://developers.cloudflare.com/d1/
- Jetpack Paging 3 codelab: https://developer.android.com/codelabs/android-paging
