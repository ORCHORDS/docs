# Flutter Image Compression and R2 Upload via Cloudflare Workers

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

Your Flutter app needs to let users upload photos that are compressed client-side before they hit your infrastructure, stored durably in R2, with metadata indexed in D1 and resized variants served on demand — all without running a traditional origin server.

## Context

- Flutter 3.22+, Dart 3.4
- `flutter_image_compress: ^2.3` for client-side WebP conversion
- `image_picker: ^1.1` for gallery/camera access
- Cloudflare Worker issues presigned R2 upload URLs and stores metadata in D1
- R2 public bucket or Worker-proxied serving with `cf.image` resize
- Workers post-upload webhook triggered by R2 event notification

## Flutter Client — Pick, Compress, Upload

```dart
// lib/upload/image_uploader.dart
import 'dart:io';
import 'package:flutter_image_compress/flutter_image_compress.dart';
import 'package:image_picker/image_picker.dart';
import 'package:http/http.dart' as http;
import 'dart:convert';

const _workerBase = 'https://api.example.com';

class ImageUploader {
  final _picker = ImagePicker();

  Future<UploadResult?> pickAndUpload() async {
    final xfile = await _picker.pickImage(source: ImageSource.gallery);
    if (xfile == null) return null;

    // 1. Compress to WebP, max 1080px on the longest side
    final compressed = await FlutterImageCompress.compressWithFile(
      xfile.path,
      minWidth: 1080,
      minHeight: 1080,
      quality: 82,
      format: CompressFormat.webp,
      keepExif: false,
    );
    if (compressed == null) throw Exception('Compression failed');

    final originalName = xfile.name.replaceAll(RegExp(r'\.[^.]+$'), '.webp');
    final sizeBytes = compressed.length;

    // 2. Obtain presigned upload URL from the Worker
    final presignRes = await http.post(
      Uri.parse('$_workerBase/uploads/presign'),
      headers: {'Content-Type': 'application/json'},
      body: jsonEncode({'filename': originalName, 'sizeBytes': sizeBytes}),
    );
    if (presignRes.statusCode != 200) {
      throw Exception('Presign failed: ${presignRes.statusCode}');
    }
    final presignData = jsonDecode(presignRes.body) as Map<String, dynamic>;
    final uploadUrl = presignData['uploadUrl'] as String;
    final r2Key = presignData['r2Key'] as String;

    // 3. PUT compressed bytes directly to R2 via presigned URL
    final putRes = await http.put(
      Uri.parse(uploadUrl),
      headers: {'Content-Type': 'image/webp'},
      body: compressed,
    );
    if (putRes.statusCode != 200 && putRes.statusCode != 204) {
      throw Exception('R2 upload failed: ${putRes.statusCode}');
    }

    // 4. Notify the Worker of the completed upload
    final notifyRes = await http.post(
      Uri.parse('$_workerBase/uploads/complete'),
      headers: {'Content-Type': 'application/json'},
      body: jsonEncode({
        'r2Key': r2Key,
        'filename': originalName,
        'sizeBytes': sizeBytes,
      }),
    );
    if (notifyRes.statusCode != 200) {
      throw Exception('Completion webhook failed: ${notifyRes.statusCode}');
    }

    return UploadResult(
      r2Key: r2Key,
      filename: originalName,
      sizeBytes: sizeBytes,
    );
  }
}

class UploadResult {
  final String r2Key;
  final String filename;
  final int sizeBytes;
  UploadResult({required this.r2Key, required this.filename, required this.sizeBytes});
}
```

## Cloudflare Worker — Presign and Metadata

```typescript
// worker/src/uploads.ts
import { R2Bucket, D1Database } from '@cloudflare/workers-types';

interface Env {
  MEDIA_BUCKET: R2Bucket;
  DB: D1Database;
  R2_ACCOUNT_ID: string;
  R2_ACCESS_KEY_ID: string;
  R2_SECRET_ACCESS_KEY: string;
  R2_BUCKET_NAME: string;
}

export async function handlePresign(req: Request, env: Env): Promise<Response> {
  const { filename, sizeBytes } = await req.json<{ filename: string; sizeBytes: number }>();

  if (sizeBytes > 20 * 1024 * 1024) {
    return new Response('File too large', { status: 413 });
  }

  const r2Key = `uploads/${crypto.randomUUID()}/${filename}`;

  // Generate a presigned PUT URL valid for 5 minutes
  const expiresIn = 300;
  const uploadUrl = await generatePresignedPutUrl(env, r2Key, expiresIn);

  return Response.json({ uploadUrl, r2Key });
}

export async function handleComplete(req: Request, env: Env): Promise<Response> {
  const { r2Key, filename, sizeBytes } =
    await req.json<{ r2Key: string; filename: string; sizeBytes: number }>();

  // Verify the object actually exists in R2 before storing metadata
  const head = await env.MEDIA_BUCKET.head(r2Key);
  if (!head) return new Response('Object not found in R2', { status: 404 });

  await env.DB.prepare(
    `INSERT INTO uploads (r2_key, filename, size_bytes, uploaded_at)
     VALUES (?, ?, ?, datetime('now'))`
  )
    .bind(r2Key, filename, sizeBytes)
    .run();

  return Response.json({ ok: true, r2Key });
}

// Workers Image Transform endpoint — serve resized variants
export async function handleImageTransform(
  req: Request,
  env: Env
): Promise<Response> {
  const url = new URL(req.url);
  const r2Key = url.searchParams.get('key');
  const width = parseInt(url.searchParams.get('w') ?? '800', 10);
  const height = parseInt(url.searchParams.get('h') ?? '600', 10);

  if (!r2Key) return new Response('Missing key', { status: 400 });

  // Use Cloudflare Image Resizing via cf.image options
  const imageUrl = `https://${env.R2_BUCKET_NAME}.r2.dev/${r2Key}`;
  return fetch(imageUrl, {
    cf: {
      image: {
        width,
        height,
        fit: 'cover',
        format: 'webp',
        quality: 80,
      },
    } as RequestInitCfProperties,
  } as RequestInit);
}

async function generatePresignedPutUrl(
  env: Env,
  key: string,
  expiresIn: number
): Promise<string> {
  // Use R2's createPresignedUrl helper available via the S3-compatible API
  // This example uses a lightweight signing approach; in production use
  // the official aws4fetch library or Workers' built-in R2 presigning.
  const now = new Date();
  const expires = Math.floor(now.getTime() / 1000) + expiresIn;
  const host = `${env.R2_BUCKET_NAME}.${env.R2_ACCOUNT_ID}.r2.cloudflarestorage.com`;
  const base = `https://${host}/${encodeURIComponent(key)}`;
  // In a real implementation sign with AWS Signature V4 (aws4fetch)
  return `${base}?X-Amz-Expires=${expiresIn}&X-Amz-Date=${now.toISOString()}`;
}
```

## Flutter Image Display with Variant URLs

```dart
// lib/widgets/remote_image.dart
import 'package:flutter/material.dart';

class RemoteImage extends StatelessWidget {
  final String r2Key;
  final int width;
  final int height;

  const RemoteImage({
    super.key,
    required this.r2Key,
    this.width = 800,
    this.height = 600,
  });

  @override
  Widget build(BuildContext context) {
    final encoded = Uri.encodeComponent(r2Key);
    final src =
        'https://api.example.com/images/transform?key=$encoded&w=$width&h=$height';
    return Image.network(
      src,
      width: width.toDouble(),
      height: height.toDouble(),
      fit: BoxFit.cover,
      errorBuilder: (_, __, ___) =>
          const Icon(Icons.broken_image, size: 48),
    );
  }
}
```

## Anti-patterns

- **Uploading uncompressed originals from mobile** — a 12MP HEIC photo can exceed 10 MB; always compress before upload to reduce egress costs and upload time.
- **Skipping the `handleComplete` verification step** — storing metadata before confirming R2 receipt can leave orphaned DB rows when the R2 PUT fails.
- **Using public R2 bucket URLs directly without a transform Worker** — bypasses resize and serves full-resolution files to mobile clients.
- **Setting `keepExif: true` when compressing** — EXIF data may include GPS coordinates; strip it unless the app explicitly needs location metadata.
- **Presigned URL without size validation** — always check `sizeBytes` in the Worker before issuing the presigned URL to prevent oversized uploads.

## Gotchas

- `FlutterImageCompress.compressWithFile` returns `null` if the input path is not a supported format (e.g., HEIC on Android below API 28); check for null before proceeding.
- R2 presigned PUT URLs require the `Content-Type` header sent by the client to match the type specified when generating the URL; mismatch returns 403.
- Cloudflare Image Resizing (`cf.image`) requires the Images product to be enabled on the account and only works on paid plans; the free tier falls back to the unresized original.
- `flutter_image_compress` uses a native plugin; add the required `NSPhotoLibraryUsageDescription` (iOS) and storage permissions (Android) to avoid runtime crashes.
- R2 event notifications (for a serverless webhook) are available via Queue consumers; polling `handleComplete` from the client is simpler but adds an extra round-trip.

## Verification

1. Pick a 5 MB JPEG; verify the compressed output is smaller than 500 KB and is a `.webp` file.
2. Check the R2 bucket in the Cloudflare dashboard — the `uploads/<uuid>/file.webp` key should appear within 5 seconds.
3. Query `SELECT * FROM uploads ORDER BY uploaded_at DESC LIMIT 1` in D1 — the row should appear with the correct `r2_key` and `size_bytes`.
4. Fetch `https://api.example.com/images/transform?key=<r2Key>&w=300&h=300` — response should be a 300×300 WebP.
5. Attempt an upload of a 25 MB file; the Worker should return 413 before issuing a presigned URL.

## Related

- `documentation/workers/r2-presigned-uploads.md`
- `documentation/workers/d1-metadata-indexing.md`
- `documentation/categories/mobile/flutter-file-picker-patterns.md`

## Sources

- https://developers.cloudflare.com/r2/api/s3/presigned-urls/
- https://developers.cloudflare.com/images/transform-images/
- https://developers.cloudflare.com/d1/
- https://pub.dev/packages/flutter_image_compress
- https://pub.dev/packages/image_picker
