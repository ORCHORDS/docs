# Flutter Riverpod State Management with Workers REST API

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

You are building a Flutter app that reads and writes data through a Cloudflare Workers REST API backed by D1. You want reactive state management with Riverpod, clean error handling, and an offline cache using Hive so the app remains functional when the device has no connectivity.

## Context

- Flutter 3.22 + Dart 3.4
- `flutter_riverpod` 2.5 + `riverpod_annotation` for code-gen providers
- Cloudflare Workers REST API (D1-backed) deployed at a custom domain
- `hive_flutter` 1.1 for local offline cache
- `dio` 5.4 for HTTP with interceptors

---

## Data Models

```dart
// lib/models/post.dart
import 'package:freezed_annotation/freezed_annotation.dart';

part 'post.freezed.dart';
part 'post.g.dart';

@freezed
class Post with _$Post {
  const factory Post({
    required int id,
    required String title,
    required String body,
    @JsonKey(name: 'created_at') required String createdAt,
  }) = _Post;

  factory Post.fromJson(Map<String, dynamic> json) => _$PostFromJson(json);
}

@freezed
class ApiResponse<T> with _$ApiResponse<T> {
  const factory ApiResponse({
    required T? data,
    required String? error,
  }) = _ApiResponse;
}
```

---

## Dio HTTP Client with Auth Interceptor

```dart
// lib/api/api_client.dart
import 'package:dio/dio.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:riverpod_annotation/riverpod_annotation.dart';

part 'api_client.g.dart';

const _baseUrl = String.fromEnvironment(
  'API_BASE_URL',
  defaultValue: 'http://localhost:8787',
);

@riverpod
Dio dio(DioRef ref) {
  final dio = Dio(BaseOptions(
    baseUrl: _baseUrl,
    connectTimeout: const Duration(seconds: 10),
    receiveTimeout: const Duration(seconds: 15),
    headers: {'Content-Type': 'application/json'},
  ));

  dio.interceptors.add(
    InterceptorsWrapper(
      onError: (e, handler) {
        if (e.type == DioExceptionType.connectionTimeout ||
            e.type == DioExceptionType.receiveTimeout) {
          handler.reject(
            DioException(
              requestOptions: e.requestOptions,
              message: 'Network timeout — check connectivity',
            ),
          );
        } else {
          handler.next(e);
        }
      },
    ),
  );

  return dio;
}
```

---

## Repository with Hive Offline Cache

```dart
// lib/repositories/posts_repository.dart
import 'package:dio/dio.dart';
import 'package:hive_flutter/hive_flutter.dart';
import 'package:riverpod_annotation/riverpod_annotation.dart';
import '../api/api_client.dart';
import '../models/post.dart';

part 'posts_repository.g.dart';

const _cacheKey = 'posts_cache';

@riverpod
PostsRepository postsRepository(PostsRepositoryRef ref) {
  return PostsRepository(ref.watch(dioProvider));
}

class PostsRepository {
  PostsRepository(this._dio);
  final Dio _dio;

  Box<String> get _box => Hive.box<String>('cache');

  Future<List<Post>> fetchPosts() async {
    try {
      final res = await _dio.get<Map<String, dynamic>>('/posts');
      final raw = res.data!['data'] as List<dynamic>;
      final posts = raw
          .map((e) => Post.fromJson(e as Map<String, dynamic>))
          .toList();
      // Write-through cache
      final encoded = posts.map((p) => p.toJson()).toList();
      await _box.put(
          _cacheKey, encoded.map((e) => e.toString()).join('||'));
      return posts;
    } on DioException catch (_) {
      // Fall back to cache
      return _readCache();
    }
  }

  List<Post> _readCache() {
    final raw = _box.get(_cacheKey);
    if (raw == null || raw.isEmpty) return [];
    // In real code use jsonDecode; simplified here for clarity
    return [];
  }

  Future<Post> createPost({
    required String title,
    required String body,
  }) async {
    final res = await _dio.post<Map<String, dynamic>>(
      '/posts',
      data: {'title': title, 'body': body},
    );
    return Post.fromJson(res.data!['data'] as Map<String, dynamic>);
  }

  Future<void> deletePost(int id) async {
    await _dio.delete<void>('/posts/$id');
  }
}
```

---

## Riverpod AsyncNotifierProvider

```dart
// lib/providers/posts_provider.dart
import 'package:riverpod_annotation/riverpod_annotation.dart';
import '../models/post.dart';
import '../repositories/posts_repository.dart';

part 'posts_provider.g.dart';

@riverpod
class Posts extends _$Posts {
  @override
  Future<List<Post>> build() async {
    return ref.watch(postsRepositoryProvider).fetchPosts();
  }

  Future<void> add(String title, String body) async {
    final repo = ref.read(postsRepositoryProvider);
    state = const AsyncValue.loading();
    state = await AsyncValue.guard(() async {
      final post = await repo.createPost(title: title, body: body);
      final current = state.valueOrNull ?? [];
      return [post, ...current];
    });
  }

  Future<void> remove(int id) async {
    final repo = ref.read(postsRepositoryProvider);
    await repo.deletePost(id);
    state = AsyncValue.data(
      (state.valueOrNull ?? []).where((p) => p.id != id).toList(),
    );
  }
}
```

---

## Flutter UI with Error / Loading States

```dart
// lib/screens/posts_screen.dart
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../providers/posts_provider.dart';

class PostsScreen extends ConsumerWidget {
  const PostsScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final postsAsync = ref.watch(postsProvider);

    return Scaffold(
      appBar: AppBar(title: const Text('Posts')),
      body: postsAsync.when(
        loading: () => const Center(child: CircularProgressIndicator()),
        error: (e, _) => Center(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              Text('Error: $e'),
              const SizedBox(height: 12),
              ElevatedButton(
                onPressed: () => ref.invalidate(postsProvider),
                child: const Text('Retry'),
              ),
            ],
          ),
        ),
        data: (posts) => ListView.builder(
          itemCount: posts.length,
          itemBuilder: (ctx, i) {
            final p = posts[i];
            return ListTile(
              title: Text(p.title),
              subtitle: Text(p.createdAt),
              trailing: IconButton(
                icon: const Icon(Icons.delete),
                onPressed: () =>
                    ref.read(postsProvider.notifier).remove(p.id),
              ),
            );
          },
        ),
      ),
      floatingActionButton: FloatingActionButton(
        onPressed: () => _showAddDialog(context, ref),
        child: const Icon(Icons.add),
      ),
    );
  }

  void _showAddDialog(BuildContext context, WidgetRef ref) {
    final titleCtl = TextEditingController();
    final bodyCtl = TextEditingController();
    showDialog(
      context: context,
      builder: (_) => AlertDialog(
        title: const Text('New Post'),
        content: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            TextField(controller: titleCtl, decoration: const InputDecoration(labelText: 'Title')),
            TextField(controller: bodyCtl, decoration: const InputDecoration(labelText: 'Body')),
          ],
        ),
        actions: [
          TextButton(
            onPressed: () {
              ref.read(postsProvider.notifier).add(titleCtl.text, bodyCtl.text);
              Navigator.pop(context);
            },
            child: const Text('Add'),
          ),
        ],
      ),
    );
  }
}
```

---

## Hive Initialisation in main()

```dart
// lib/main.dart
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:hive_flutter/hive_flutter.dart';
import 'screens/posts_screen.dart';

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  await Hive.initFlutter();
  await Hive.openBox<String>('cache');
  runApp(const ProviderScope(child: MyApp()));
}

class MyApp extends StatelessWidget {
  const MyApp({super.key});
  @override
  Widget build(BuildContext context) =>
      MaterialApp(home: const PostsScreen(), title: 'Workers + Riverpod');
}
```

---

## Anti-patterns

- Do NOT use `FutureProvider` directly for mutable collections — use `AsyncNotifierProvider` so you can mutate state optimistically.
- Do NOT catch all `Exception` types — narrow to `DioException` to avoid swallowing logic errors.
- Do NOT store complex objects in Hive without a registered `TypeAdapter` or JSON string serialisation.
- Do NOT read providers inside `build()` widgets without `ref.watch` — this breaks reactive updates.

## Gotchas

- `String.fromEnvironment` is resolved at compile time via `--dart-define`; it is NOT a runtime env var.
- Hive boxes must be opened before first access; open them in `main()` before `runApp`.
- `riverpod_annotation` requires running `dart run build_runner build` after every provider change.
- D1 on Workers does not support transactions across multiple HTTP requests; design endpoints as atomic operations.

---

## Verification

```bash
# Run build_runner
flutter pub run build_runner build --delete-conflicting-outputs

# Build with custom API URL
flutter run --dart-define=API_BASE_URL=https://api.example.com

# Run unit tests
flutter test test/posts_provider_test.dart

# Inspect Hive cache on device (debug)
adb shell run-as com.example.app ls files/
```

---

## Related

- `documentation/docs/policies/mobile/workers-expo-router-api-routes-d1.md`
- `documentation/docs/policies/mobile/workers-ios-swift-async-d1-api.md`
- `documentation/docs/policies/mobile/workers-mobile-background-fetch-queues.md`

## Sources

- https://developers.cloudflare.com/d1/
- https://riverpod.dev/docs/providers/async_notifier_provider
- https://pub.dev/packages/hive_flutter
- https://pub.dev/packages/dio
- https://pub.dev/packages/freezed
