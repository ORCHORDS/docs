# Flutter Camera R2 Multipart Upload Pipeline

Date: 2026-08-23 / Author: example.com / Status: production

## Symptom / Use-case

Flutter apps that capture photos or videos via `image_picker` or `camera` need a resilient
upload path to Cloudflare R2 that survives network interruptions, compresses media before
transmission, and surfaces per-chunk progress to the UI. Single-PUT uploads via Dart's `http`
package stall on cellular mid-transfer with no recovery path. Multipart upload brokered by a
Workers signing proxy is the correct solution.

## Context

Dart's `dio` package supports chunked streaming and progress callbacks. A Cloudflare Worker
brokers R2 multipart sessions — the client requests a session, PUTs each 5 MB chunk through
the Worker, then calls the complete endpoint. `flutter_image_compress` compresses JPEG/WebP
before the upload loop starts. Completed upload metadata is stored in D1 for audit and search.
A Riverpod `AsyncNotifier` manages upload state across the widget tree.

---

## 1. Camera Capture and Compression

```dart
// lib/capture.dart
import 'dart:io';
import 'package:image_picker/image_picker.dart';
import 'package:flutter_image_compress/flutter_image_compress.dart';

Future<File> captureAndCompress() async {
  final picker = ImagePicker();
  final xFile = await picker.pickImage(
    source: ImageSource.camera,
    imageQuality: 100,       // let compress handle quality
  );
  if (xFile == null) throw Exception('No image captured');

  final destPath = '${xFile.path}_c.jpg';
  final result = await FlutterImageCompress.compressAndGetFile(
    xFile.path,
    destPath,
    quality: 82,
    minWidth: 1920,
    minHeight: 1080,
    format: CompressFormat.jpeg,
  );
  if (result == null) throw Exception('Compression failed');
  return File(result.path);
}
```

---

## 2. Workers Multipart Signing Proxy

```typescript
// worker/src/r2-multipart.ts
export default {
  async fetch(req: Request, env: Env): Promise<Response> {
    const url = new URL(req.url);

    // --- initiate ---
    if (url.pathname === '/upload/init' && req.method === 'POST') {
      const { filename } = await req.json<{ filename: string }>();
      const key = `flutter/${crypto.randomUUID()}/${filename}`;
      const upload = await env.BUCKET.createMultipartUpload(key);
      return Response.json({ key, uploadId: upload.uploadId });
    }

    // --- upload part ---
    if (url.pathname === '/upload/part' && req.method === 'PUT') {
      const key = url.searchParams.get('key')!;
      const uploadId = url.searchParams.get('uploadId')!;
      const partNumber = parseInt(url.searchParams.get('part')!, 10);
      const mu = env.BUCKET.resumeMultipartUpload(key, uploadId);
      const part = await mu.uploadPart(partNumber, req.body!);
      return Response.json({ etag: part.etag, partNumber });
    }

    // --- complete ---
    if (url.pathname === '/upload/complete' && req.method === 'POST') {
      const { key, uploadId, parts } = await req.json<{
        key: string;
        uploadId: string;
        parts: Array<{ partNumber: number; etag: string }>;
      }>();
      const mu = env.BUCKET.resumeMultipartUpload(key, uploadId);
      await mu.complete(parts);
      await recordUpload(env, key, req.headers.get('x-user-id') ?? 'anon');
      return Response.json({ cdnUrl: `https://cdn.example.com/${key}` });
    }

    return new Response('Not found', { status: 404 });
  },
} satisfies ExportedHandler<Env>;

async function recordUpload(env: Env, key: string, userId: string) {
  await env.DB.prepare(
    'INSERT INTO flutter_uploads (id, user_id, r2_key, uploaded_at) VALUES (?, ?, ?, ?)'
  ).bind(crypto.randomUUID(), userId, key, new Date().toISOString()).run();
}
```

---

## 3. Dart Multipart Upload Client

```dart
// lib/r2_uploader.dart
import 'dart:io';
import 'package:dio/dio.dart';

const _partSize = 5 * 1024 * 1024; // 5 MB — R2 minimum per part

class R2Uploader {
  final Dio _dio;
  final String _workerBase;

  R2Uploader(this._workerBase)
      : _dio = Dio(BaseOptions(
          baseUrl: _workerBase,
          connectTimeout: const Duration(seconds: 10),
          receiveTimeout: const Duration(seconds: 60),
        ));

  Future<String> upload(
    File file,
    String userId, {
    void Function(double progress)? onProgress,
  }) async {
    final size = await file.length();
    final partCount = (size / _partSize).ceil();

    // 1 — initiate session
    final init = await _dio.post<Map<String, dynamic>>('/upload/init',
        data: {'filename': file.uri.pathSegments.last},
        options: Options(headers: {'x-user-id': userId}));
    final key = init.data!['key'] as String;
    final uploadId = init.data!['uploadId'] as String;

    // 2 — stream parts
    final parts = <Map<String, dynamic>>[];
    final raf = await file.open();
    try {
      for (int i = 0; i < partCount; i++) {
        final offset = i * _partSize;
        final length = (size - offset).clamp(0, _partSize).toInt();
        await raf.setPosition(offset);
        final chunk = await raf.read(length);

        final res = await _dio.put<Map<String, dynamic>>(
          '/upload/part?key=$key&uploadId=$uploadId&part=${i + 1}',
          data: Stream.value(chunk),
          options: Options(
            headers: {'Content-Length': length, 'x-user-id': userId},
          ),
        );
        parts.add({'partNumber': i + 1, 'etag': res.data!['etag'] as String});
        onProgress?.call((i + 1) / partCount);
      }
    } finally {
      await raf.close();
    }

    // 3 — complete
    final complete = await _dio.post<Map<String, dynamic>>(
      '/upload/complete',
      data: {'key': key, 'uploadId': uploadId, 'parts': parts},
      options: Options(headers: {'x-user-id': userId}),
    );
    return complete.data!['cdnUrl'] as String;
  }
}
```

---

## 4. Riverpod Upload State Notifier

```dart
// lib/upload_provider.dart
import 'dart:io';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'r2_uploader.dart';

class UploadState {
  final double progress;
  final String? cdnUrl;
  final Object? error;
  const UploadState({this.progress = 0, this.cdnUrl, this.error});
}

class UploadNotifier extends AsyncNotifier<UploadState> {
  final _uploader = R2Uploader('https://upload.example.com');

  @override
  Future<UploadState> build() async => const UploadState();

  Future<void> upload(File file, String userId) async {
    state = const AsyncValue.loading();
    try {
      double p = 0;
      final url = await _uploader.upload(
        file, userId,
        onProgress: (progress) {
          p = progress;
          state = AsyncValue.data(UploadState(progress: p));
        },
      );
      state = AsyncValue.data(UploadState(progress: 1, cdnUrl: url));
    } catch (e, st) {
      state = AsyncValue.error(e, st);
    }
  }
}

final uploadProvider = AsyncNotifierProvider<UploadNotifier, UploadState>(UploadNotifier.new);
```

---

## 5. Upload Progress UI Widget

```dart
// lib/upload_screen.dart
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'capture.dart';
import 'upload_provider.dart';

class UploadScreen extends ConsumerWidget {
  const UploadScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final state = ref.watch(uploadProvider);

    return Scaffold(
      appBar: AppBar(title: const Text('Camera Upload')),
      body: Center(
        child: state.when(
          loading: () => const CircularProgressIndicator(),
          error: (e, _) => Text('Error: $e'),
          data: (s) => Column(mainAxisSize: MainAxisSize.min, children: [
            if (s.progress > 0 && s.progress < 1)
              Padding(
                padding: const EdgeInsets.all(16),
                child: LinearProgressIndicator(value: s.progress),
              ),
            if (s.cdnUrl != null)
              Text('Uploaded: ${s.cdnUrl}', textAlign: TextAlign.center),
            ElevatedButton(
              onPressed: () async {
                final file = await captureAndCompress();
                ref.read(uploadProvider.notifier).upload(file, 'user-001');
              },
              child: const Text('Capture & Upload'),
            ),
          ]),
        ),
      ),
    );
  }
}
```

---

## Anti-patterns

- Using `http.MultipartRequest` for large files — it buffers the entire payload in memory; use `dio` with a `Stream` for chunked transfer.
- Skipping compression for "small" photos — modern flagship cameras produce 10–20 MB HEIF; always compress to JPEG before upload.
- Instantiating `R2Uploader` inside the widget `build` method — create it once via a Riverpod provider so the `Dio` instance is reused.
- Omitting `raf.close()` in error paths — use `try/finally`; missing closes exhaust file descriptors on Android after a few failed uploads.

## Gotchas

- `flutter_image_compress` requires `minSdkVersion 21` on Android; bump `android/app/build.gradle` if targeting older devices.
- `raf.read(length)` allocates a `Uint8List` of exactly `length` bytes; keep part size at 5 MB to avoid OOM on 1 GB devices.
- Dio needs an explicit `Content-Length` header when sending a `Stream`; omitting it causes R2 to return HTTP 411.
- `createMultipartUpload` does not auto-expire; add a Workers Cron Trigger to call `abortMultipartUpload` on sessions older than 24 h.

## Verification

```bash
# Confirm the init endpoint
curl -X POST https://upload.example.com/upload/init \
  -H "Content-Type: application/json" -d '{"filename":"test.jpg"}' | jq .

# List recent objects
wrangler r2 object list flutter-media --prefix flutter/

# Audit D1 table
wrangler d1 execute DB --command \
  "SELECT * FROM flutter_uploads ORDER BY uploaded_at DESC LIMIT 5;"
```

## Related

- `expo-camera-r2-upload-compression.md`
- `capacitor-workers-camera-r2-upload.md`
- `flutter-workers-image-transform-cdn.md`
- `react-native-r2-multipart-upload-progress.md`

## Sources

- https://developers.cloudflare.com/r2/api/workers/workers-multipart-usage/
- https://pub.dev/packages/dio
- https://pub.dev/packages/flutter_image_compress
- https://pub.dev/packages/flutter_riverpod
