# android-room-database

**Issue:** Persisting structured data locally on Android using Room with Kotlin coroutines
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Direct SQLite queries without Room require manual cursor management and lack compile-time SQL validation.

## Pattern / Solution
```kotlin
// build.gradle
implementation "androidx.room:room-runtime:2.6.1"
implementation "androidx.room:room-ktx:2.6.1"
kapt "androidx.room:room-compiler:2.6.1"

// Entity
@Entity(tableName = "users")
data class User(
  @PrimaryKey val id: String,
  val name: String,
  val email: String,
  val createdAt: Long = System.currentTimeMillis()
)

// DAO
@Dao
interface UserDao {
  @Query("SELECT * FROM users ORDER BY createdAt DESC")
  fun observeAll(): Flow<List<User>>

  @Insert(onConflict = OnConflictStrategy.REPLACE)
  suspend fun upsert(user: User)

  @Delete
  suspend fun delete(user: User)

  @Query("SELECT * FROM users WHERE id = :id")
  suspend fun findById(id: String): User?
}

// Database
@Database(entities = [User::class], version = 1, exportSchema = true)
abstract class AppDatabase : RoomDatabase() {
  abstract fun userDao(): UserDao

  companion object {
    @Volatile private var INSTANCE: AppDatabase? = null
    fun getInstance(context: Context) = INSTANCE ?: synchronized(this) {
      Room.databaseBuilder(context, AppDatabase::class.java, "app.db")
        .addMigrations(MIGRATION_1_2)
        .build().also { INSTANCE = it }
    }
  }
}
```

## Gotchas
- `exportSchema = true` and committing the schema JSON file enables CI migration testing
- Room queries must run on a coroutine or background thread — calling from main thread throws `IllegalStateException`
- `Flow<>` return types automatically trigger recomposition when data changes; `suspend` functions are one-shot
- Database migrations without explicit `Migration` objects cause data loss on version bump

## Related
- `android-coroutines.md`
- `android-viewmodel-patterns.md`
- `ios-core-data-patterns.md`
