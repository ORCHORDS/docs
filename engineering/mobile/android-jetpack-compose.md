# android-jetpack-compose

**Issue:** Building declarative Android UIs with Jetpack Compose and managing recomposition
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Unnecessary recompositions degrade performance; understanding Compose state stability prevents wasted renders.

## Pattern / Solution
```kotlin
// Composable with stable state
@Composable
fun UserCard(
  user: User,
  onEdit: () -> Unit, // lambda — stable
  modifier: Modifier = Modifier
) {
  Card(modifier = modifier.clickable(onClick = onEdit)) {
    Column(Modifier.padding(16.dp)) {
      Text(text = user.name, style = MaterialTheme.typography.titleMedium)
      Text(text = user.email, style = MaterialTheme.typography.bodySmall)
    }
  }
}

// ViewModel with StateFlow
class UserViewModel : ViewModel() {
  private val _uiState = MutableStateFlow(UserUiState())
  val uiState: StateFlow<UserUiState> = _uiState.asStateFlow()

  fun loadUser(id: String) {
    viewModelScope.launch {
      _uiState.update { it.copy(isLoading = true) }
      val user = repository.getUser(id)
      _uiState.update { it.copy(user = user, isLoading = false) }
    }
  }
}

// Collect in Compose
@Composable
fun UserScreen(vm: UserViewModel = viewModel()) {
  val state by vm.uiState.collectAsStateWithLifecycle()
  if (state.isLoading) CircularProgressIndicator()
  else state.user?.let { UserCard(it, onEdit = { /* navigate */ }) }
}
```

## Gotchas
- `collectAsState()` does not respect lifecycle; prefer `collectAsStateWithLifecycle()` from `lifecycle-runtime-compose`
- Lambdas passed to composables must be stable (captured in `remember {}` or use `@Stable` data classes) to avoid recomposition
- `LazyColumn` with items that have complex `key` parameters can cause incorrect item animations — always provide unique stable keys
- Compose Preview requires `@PreviewParameter` for complex data; avoid hardcoding preview data in production composables

## Related
- `android-viewmodel-patterns.md`
- `android-material-design-3.md`
- `android-accessibility.md`
