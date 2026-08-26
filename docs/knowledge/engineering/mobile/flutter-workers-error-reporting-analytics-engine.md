# Flutter Error Reporting via Cloudflare Workers + Analytics Engine

**Date:** 2026-08-23
**Author:** example.com
**Status:** production

---

## Symptom / Use-Case

Your Flutter app crashes or records unhandled exceptions and you want to pipe those error events to Cloudflare's Analytics Engine via a Workers endpoint rather than a third-party SDK like Sentry or Crashlytics. You need structured error blobs queryable via Workers Analytics Engine SQL API, plus the ability to add custom dimensions (user tier, app version, device model) without paying per-seat pricing.

---

## Context

Flutter exposes two global error hooks: `FlutterError.onError` for framework-level widget errors and `PlatformDispatcher.instance.onError` for uncaught asynchronous errors. Both fire on the UI isolate. A Dart HTTP client sends batched error blobs to a Cloudflare Worker, which writes them to Analytics Engine via `env.AE.writeDataPoint()`. Analytics Engine stores up to 20 blobs and 25 double indexes per data point; SQL queries run over the `workers_analytics_engine` dataset.

Error reporting is a write-heavy, low-latency-tolerance workload — fire-and-forget with local buffering is preferred over synchronous round-trips.

---

## 1. Dart Error Model

```dart
// lib/error_reporting/models.dart

class AppError {
  final String errorType;   // e.g. "FlutterError", "StateError"
  final String message;
  final String stackTrace;
  final String appVersion;
  final String platform;    // "android" | "ios"
  final String deviceModel;
  final DateTime occurredAt;
  final Map<String, String> extras;

  AppError({
    required this.errorType,
    required this.message,
    required this.stackTrace,
    required this.appVersion,
    required this.platform,
    required this.deviceModel,
    required this.occurredAt,
    this.extras = const {},
  });

  Map<String, dynamic> toJson() => {
    "errorType": errorType,
    "message": message,
    "stackTrace": stackTrace,
    "appVersion": appVersion,
    "platform": platform,
    "deviceModel": deviceModel,
    "occurredAt": occurredAt.toIso8601String(),
    "extras": extras,
  };
}
```

---

## 2. Dart Error Reporter with Local Buffer

```dart
// lib/error_reporting/reporter.dart
import "dart:async";
import "dart:convert";
import "package:http/http.dart" as http;
import "models.dart";

class ErrorReporter {
  static const _endpoint = "https://errors.example.workers.dev/report";
  static const _batchSize = 10;
  static const _flushInterval = Duration(seconds: 30);

  final List<AppError> _buffer = [];
  Timer? _flushTimer;

  ErrorReporter() {
    _flushTimer = Timer.periodic(_flushInterval, (_) => flush());
  }

  void capture(AppError error) {
    _buffer.add(error);
    if (_buffer.length >= _batchSize) {
      flush();
    }
  }

  Future<void> flush() async {
    if (_buffer.isEmpty) return;
    final batch = List<AppError>.from(_buffer);
    _buffer.clear();

    try {
      await http.post(
        Uri.parse(_endpoint),
        headers: {"Content-Type": "application/json"},
        body: jsonEncode({"errors": batch.map((e) => e.toJson()).toList()}),
      ).timeout(const Duration(seconds: 8));
    } catch (_) {
      // Silently drop — error reporting must never crash the app
    }
  }

  void dispose() {
    _flushTimer?.cancel();
    flush();
  }
}

final reporter = ErrorReporter();
```

---

## 3. Hook Flutter and Dart Error Handlers

```dart
// lib/main.dart
import "dart:ui";
import "package:flutter/foundation.dart";
import "package:flutter/material.dart";
import "package:device_info_plus/device_info_plus.dart";
import "package:package_info_plus/package_info_plus.dart";
import "error_reporting/reporter.dart";
import "error_reporting/models.dart";

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();

  final pkgInfo = await PackageInfo.fromPlatform();
  final devInfo = DeviceInfoPlugin();

  Future<AppError> buildError(Object err, StackTrace? st, String type) async {
    String model = "unknown";
    String platform = defaultTargetPlatform.name.toLowerCase();
    try {
      if (defaultTargetPlatform == TargetPlatform.android) {
        final a = await devInfo.androidInfo;
        model = "${a.manufacturer} ${a.model}";
      } else if (defaultTargetPlatform == TargetPlatform.iOS) {
        final i = await devInfo.iosInfo;
        model = i.utsname.machine;
      }
    } catch (_) {}

    return AppError(
      errorType: type,
      message: err.toString(),
      stackTrace: (st ?? StackTrace.current).toString(),
      appVersion: pkgInfo.version,
      platform: platform,
      deviceModel: model,
      occurredAt: DateTime.now().toUtc(),
    );
  }

  FlutterError.onError = (FlutterErrorDetails details) async {
    reporter.capture(await buildError(details.exception, details.stack, "FlutterError"));
    FlutterError.presentError(details); // still shows in debug overlay
  };

  PlatformDispatcher.instance.onError = (error, stack) {
    buildError(error, stack, "PlatformError").then(reporter.capture);
    return true; // return true to suppress re-throw
  };

  runApp(const MyApp());
}
```

---

## 4. Cloudflare Worker — Ingest to Analytics Engine

```typescript
// workers/error-ingest/src/index.ts
export interface Env {
  AE: AnalyticsEngineDataset;
}

interface AppErrorPayload {
  errorType: string;
  message: string;
  stackTrace: string;
  appVersion: string;
  platform: string;
  deviceModel: string;
  occurredAt: string;
  extras: Record<string, string>;
}

interface IngestBody {
  errors: AppErrorPayload[];
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    if (request.method !== "POST" || new URL(request.url).pathname !== "/report") {
      return new Response("Not found", { status: 404 });
    }

    let body: IngestBody;
    try {
      body = await request.json<IngestBody>();
    } catch {
      return Response.json({ error: "invalid JSON" }, { status: 400 });
    }

    const cf = request.cf as { country?: string } | undefined;

    for (const err of body.errors.slice(0, 20)) { // cap at 20 per request
      env.AE.writeDataPoint({
        // blobs: up to 20 string values, indexed as b1..b20
        blobs: [
          err.errorType,    // b1
          err.message.slice(0, 512), // b2 — truncate long messages
          err.platform,     // b3
          err.appVersion,   // b4
          err.deviceModel,  // b5
          cf?.country ?? "unknown", // b6
          err.stackTrace.slice(0, 1024), // b7 — first 1 KB of stack
        ],
        // doubles: numeric indexes
        doubles: [
          new Date(err.occurredAt).getTime(), // d1 — epoch ms
        ],
        indexes: [err.errorType], // partition key for queries
      });
    }

    return Response.json({ ok: true });
  },
};
```

---

## 5. Querying Errors via Analytics Engine SQL API

```bash
# Top error types in the last 24 hours
curl "https://api.cloudflare.com/client/v4/accounts/$ACCOUNT_ID/analytics_engine/sql" \
  -H "Authorization: Bearer $CF_API_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "SELECT blob1 AS error_type, count() AS hits FROM flutter_errors WHERE timestamp > now() - INTERVAL '\''1'\'' DAY GROUP BY blob1 ORDER BY hits DESC LIMIT 20"
  }'

# Error rate by app version
# SELECT blob4 AS version, count() AS total FROM flutter_errors
# WHERE timestamp > now() - INTERVAL '7' DAY GROUP BY blob4 ORDER BY total DESC
```

---

## Anti-Patterns

- **Sending errors synchronously in error handlers.** `FlutterError.onError` must return quickly; blocking it with an HTTP call can cause ANR-like freezes. Always buffer and flush asynchronously.
- **Including full stack traces in blob fields without truncation.** Analytics Engine blobs are limited to 1024 bytes per value. Overlong strings are silently truncated, losing the tail of the stack. Trim before sending.
- **Not deduplicating in the Worker.** A crash loop can send thousands of identical errors per minute. Apply a KV-based dedup key (`hash(errorType + message + version)`) in the Worker if volume is a concern.
- **Logging PII in error messages.** User emails or IDs that appear in `exception.toString()` end up in Analytics Engine blobs. Scrub known PII patterns before the `message` field is written.

---

## Gotchas

- **`PlatformDispatcher.instance.onError` requires Dart 2.18+ / Flutter 3.3+.** Older apps use `runZonedGuarded` as a substitute.
- **Analytics Engine SQL API has a 10-minute propagation delay.** Data points written now are not queryable for up to 10 minutes. This is expected; do not use it for real-time alerting.
- **`AnalyticsEngineDataset` is only available in Workers, not Pages Functions.** If you route through a Pages Function you must bind the dataset to a Worker and call it from there.
- **Device model strings vary wildly.** `utsname.machine` on iOS returns hardware identifiers like `iPhone14,2`; you need a mapping table to convert to marketing names for dashboards.

---

## Verification

```bash
# Deploy the Worker
wrangler deploy

# Send a synthetic error batch
curl -X POST "https://errors.example.workers.dev/report" \
  -H "Content-Type: application/json" \
  -d '{
    "errors": [{
      "errorType": "StateError",
      "message": "Bad state: stream closed",
      "stackTrace": "#0 main.dart:42",
      "appVersion": "2.1.0",
      "platform": "android",
      "deviceModel": "Google Pixel 9",
      "occurredAt": "2026-08-23T10:00:00Z",
      "extras": {}
    }]
  }'

# Query after ~10 min propagation delay
curl "https://api.cloudflare.com/client/v4/accounts/$ACCOUNT_ID/analytics_engine/sql" \
  -H "Authorization: Bearer $CF_API_TOKEN" \
  -d '{"query":"SELECT blob1,blob3,blob4,count() FROM flutter_errors GROUP BY blob1,blob3,blob4"}'
```

---

## Related

- `flutter-workers-dart-client.md`
- `flutter-workers-image-transform-cdn.md`
- `mobile-crash-reporting.md`
- `mobile-crash-symbolication.md`
- `mobile-analytics-patterns.md`

---

## Sources

- Flutter `FlutterError.onError` — https://api.flutter.dev/flutter/foundation/FlutterError/onError.html
- `PlatformDispatcher.onError` — https://api.flutter.dev/flutter/dart-ui/PlatformDispatcher/onError.html
- Cloudflare Analytics Engine — https://developers.cloudflare.com/analytics/analytics-engine/
- Analytics Engine SQL API — https://developers.cloudflare.com/analytics/analytics-engine/sql-api/
- `device_info_plus` — https://pub.dev/packages/device_info_plus
