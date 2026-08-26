# android-viewmodel-patterns

**Issue:** Surviving configuration changes and managing UI state with Android ViewModel
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Activities and Fragments are destroyed on rotation; storing state in them loses data and causes redundant network calls.

## Pattern / Solution
```kotlin
// UI state sealed class
sealed interface HomeUiState {
  data object Loading : HomeUiState
  data class Success(val items: List<Item>) : HomeUiState
  data class Error(val message: String) : HomeUiState
}

// ViewModel
class HomeViewModel(private val repo: ItemRepository) : ViewModel() {
  private val _uiState = MutableStateFlow<HomeUiState>(HomeUiState.Loading)
  val uiState: StateFlow<HomeUiState> = _uiState.asStateFlow()

  init { loadItems() }

  fun loadItems() {
    viewModelScope.launch {
      _uiState.value = HomeUiState.Loading
      _uiState.value = runCatching { HomeUiState.Success(repo.getItems()) }
        .getOrElse { HomeUiState.Error(it.message ?: "Unknown error") }
    }
  }
}

// With Hilt injection
@HiltViewModel
class HomeViewModel @Inject constructor(
  private val repo: ItemRepository
) : ViewModel()

// Fragment
@AndroidEntryPoint
class HomeFragment : Fragment() {
  private val viewModel: HomeViewModel by viewModels()

  override fun onViewCreated(view: View, savedInstanceState: Bundle?) {
    viewLifecycleOwner.lifecycleScope.launch {
      repeatOnLifecycle(Lifecycle.State.STARTED) {
        viewModel.uiState.collect { state ->
          when (state) {
            is HomeUiState.Loading -> showLoading()
            is HomeUiState.Success -> showItems(state.items)
            is HomeUiState.Error -> showError(state.message)
          }
        }
      }
    }
  }
}
```

## Gotchas
- ViewModel survives rotation but **not** process death — use `SavedStateHandle` for data that must survive process kill
- Never hold a reference to Activity/Fragment/View inside ViewModel — use `Application` context if needed
- `viewModels()` delegate creates one instance per Fragment; `activityViewModels()` shares across the Activity
- `LiveData` is safe to observe from Activity/Fragment; prefer `StateFlow` in new code

## Related
- `android-coroutines.md`
- `android-jetpack-compose.md`
- `android-room-database.md`
