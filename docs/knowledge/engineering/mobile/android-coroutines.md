# android-coroutines

**Issue:** Managing asynchronous work on Android with Kotlin Coroutines and structured concurrency
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
`AsyncTask` and thread pools without structured concurrency leak work when the lifecycle ends; coroutines cancel automatically with scope.

## Pattern / Solution
```kotlin
// ViewModel scope (auto-cancelled on ViewModel.onCleared)
class MyViewModel : ViewModel() {
  fun loadData() {
    viewModelScope.launch {
      val result = withContext(Dispatchers.IO) {
        repository.fetchData()       // blocking I/O off main thread
      }
      _uiState.update { it.copy(data = result) }  // back on main
    }
  }

  // Concurrent fetches
  fun loadParallel() {
    viewModelScope.launch {
      val usersDeferred = async(Dispatchers.IO) { repository.getUsers() }
      val postsDeferred = async(Dispatchers.IO) { repository.getPosts() }
      val (users, posts) = Pair(usersDeferred.await(), postsDeferred.await())
      _uiState.update { it.copy(users = users, posts = posts) }
    }
  }
}

// Custom scope in non-ViewModel class
class DataSync(private val scope: CoroutineScope = CoroutineScope(SupervisorJob() + Dispatchers.Default)) {
  fun sync() {
    scope.launch { /* ... */ }
  }
  fun cancel() = scope.cancel()
}

// Flow with lifecycle awareness (Fragment)
lifecycleScope.launch {
  repeatOnLifecycle(Lifecycle.State.STARTED) {
    viewModel.uiState.collect { render(it) }
  }
}
```

## Gotchas
- Launching coroutines with `GlobalScope` bypasses structured concurrency — avoid it
- `Dispatchers.IO` is optimized for blocking I/O (default pool size 64); CPU-bound work goes on `Dispatchers.Default`
- Exceptions in `async` are not thrown until `.await()` is called; use `SupervisorJob` to prevent sibling cancellation
- `repeatOnLifecycle` is required for `Flow` collection in fragments — `launchWhenStarted` does not cancel on stop

## Related
- `android-viewmodel-patterns.md`
- `android-room-database.md`
- `android-retrofit-patterns.md`
