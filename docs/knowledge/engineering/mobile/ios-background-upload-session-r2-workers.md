# iOS Background Upload Sessions to Cloudflare R2 via Workers

- **Date:** 2026-08-23
- **Author:** example.com
- **Status:** production

## Symptom / Use-case
Large file uploads (audio recordings, video clips, document scans) fail or restart from zero when the user backgrounds the iOS app mid-upload, especially on cellular where connections drop frequently.

## Context
iOS URLSession background configurations hand upload tasks to the OS daemon, which continues the transfer even after the app is suspended or terminated. A Cloudflare Worker acts as an authentication and routing proxy, issuing presigned R2 upload URLs before the background task starts. The Worker validates JWTs, enforces size limits, and records upload metadata in D1.

## Cloudflare Worker — Presigned URL Endpoint
```typescript
// workers/upload-session.ts
import { Env } from './types';
import { AwsClient } from 'aws4fetch';  // bundled dep for R2 S3-compatible signing

export async function handleUploadSession(req: Request, env: Env): Promise<Response> {
  const auth = req.headers.get('Authorization') ?? '';
  const payload = await verifyJwt(auth.replace('Bearer ', ''), env.JWT_SECRET);
  if (!payload) return new Response('Unauthorized', { status: 401 });

  const { filename, contentType, byteSize } = await req.json<{
    filename: string; contentType: string; byteSize: number;
  }>();

  if (byteSize > 500 * 1024 * 1024) {
    return new Response('File too large', { status: 413 });
  }

  const key = `uploads/${payload.sub}/${Date.now()}-${filename}`;
  const r2 = new AwsClient({
    accessKeyId: env.R2_ACCESS_KEY_ID,
    secretAccessKey: env.R2_SECRET_ACCESS_KEY,
  });

  const presignedUrl = await r2.sign(
    new Request(`https://${env.R2_BUCKET}.${env.R2_ACCOUNT_ID}.r2.cloudflarestorage.com/${key}`, {
      method: 'PUT',
      headers: { 'Content-Type': contentType },
    }),
    { aws: { signQuery: true }, expiresIn: 3600 }
  );

  await env.DB.prepare(
    `INSERT INTO uploads (user_id, r2_key, filename, byte_size, status, created_at)
     VALUES (?, ?, ?, ?, 'pending', datetime('now'))`
  ).bind(payload.sub, key, filename, byteSize).run();

  return Response.json({ uploadUrl: presignedUrl.url, r2Key: key });
}

async function verifyJwt(token: string, secret: string): Promise<{ sub: string } | null> {
  try {
    const key = await crypto.subtle.importKey(
      'raw', new TextEncoder().encode(secret), { name: 'HMAC', hash: 'SHA-256' }, false, ['verify']
    );
    const [headerB64, payloadB64, sigB64] = token.split('.');
    const data = new TextEncoder().encode(`${headerB64}.${payloadB64}`);
    const sig = Uint8Array.from(atob(sigB64.replace(/-/g, '+').replace(/_/g, '/')), c => c.charCodeAt(0));
    const valid = await crypto.subtle.verify('HMAC', key, sig, data);
    return valid ? JSON.parse(atob(payloadB64)) : null;
  } catch { return null; }
}
```

## iOS — Background URLSession Configuration
```swift
// UploadSessionManager.swift
import Foundation

final class UploadSessionManager: NSObject {
    static let shared = UploadSessionManager()
    static let backgroundIdentifier = "com.yourapp.upload"

    private(set) lazy var session: URLSession = {
        let config = URLSessionConfiguration.background(
            withIdentifier: Self.backgroundIdentifier
        )
        config.isDiscretionary = false          // start immediately
        config.sessionSendsLaunchEvents = true  // wake app on completion
        config.allowsCellularAccess = true
        config.waitsForConnectivity = true      // retry when offline
        config.timeoutIntervalForResource = 7 * 24 * 3600  // 7 days max
        return URLSession(configuration: config, delegate: self, delegateQueue: nil)
    }()

    // Completion handler stored when OS wakes the app via application(_:handleEventsForBackgroundURLSession:)
    var backgroundCompletionHandler: (() -> Void)?

    func startUpload(localFileURL: URL, presignedURL: URL, contentType: String) {
        var request = URLRequest(url: presignedURL)
        request.httpMethod = "PUT"
        request.setValue(contentType, forHTTPHeaderField: "Content-Type")
        // For background uploads the body MUST come from a file, not httpBody
        let task = session.uploadTask(with: request, fromFile: localFileURL)
        task.taskDescription = localFileURL.lastPathComponent
        task.resume()
    }
}
```

## iOS — Upload Task Delegate
```swift
// UploadSessionManager+Delegate.swift
extension UploadSessionManager: URLSessionTaskDelegate, URLSessionDelegate {

    func urlSession(_ session: URLSession,
                    task: URLSessionTask,
                    didSendBodyData bytesSent: Int64,
                    totalBytesSent: Int64,
                    totalBytesExpectedToSend: Int64) {
        let progress = Double(totalBytesSent) / Double(totalBytesExpectedToSend)
        DispatchQueue.main.async {
            NotificationCenter.default.post(
                name: .uploadProgress,
                object: nil,
                userInfo: ["progress": progress, "taskId": task.taskIdentifier]
            )
        }
    }

    func urlSession(_ session: URLSession, task: URLSessionTask,
                    didCompleteWithError error: Error?) {
        guard let httpResponse = task.response as? HTTPURLResponse else {
            scheduleRetryNotification(task: task, error: error); return
        }
        let success = (200...299).contains(httpResponse.statusCode)
        DispatchQueue.main.async {
            NotificationCenter.default.post(
                name: success ? .uploadCompleted : .uploadFailed,
                object: nil,
                userInfo: ["taskId": task.taskIdentifier,
                           "statusCode": httpResponse.statusCode]
            )
        }
        if success { confirmUploadWithWorker(taskDescription: task.taskDescription) }
    }

    func urlSessionDidFinishEvents(forBackgroundURLSession session: URLSession) {
        DispatchQueue.main.async { [weak self] in
            self?.backgroundCompletionHandler?()
            self?.backgroundCompletionHandler = nil
        }
    }

    private func confirmUploadWithWorker(taskDescription: String?) {
        // PATCH /uploads/{key} status=complete on the Worker
    }

    private func scheduleRetryNotification(task: URLSessionTask, error: Error?) {
        // Surface UNUserNotificationCenter local notification to user
    }
}
```

## AppDelegate — Background Session Hook
```swift
// AppDelegate.swift
func application(_ application: UIApplication,
                 handleEventsForBackgroundURLSession identifier: String,
                 completionHandler: @escaping () -> Void) {
    guard identifier == UploadSessionManager.backgroundIdentifier else { return }
    // Reconnect the session so delegate callbacks fire, then call the handler
    UploadSessionManager.shared.backgroundCompletionHandler = completionHandler
    _ = UploadSessionManager.shared.session   // triggers lazy init if needed
}
```

## Requesting a Presigned URL Before Upload
```swift
// UploadCoordinator.swift
struct PresignedResponse: Decodable { let uploadUrl: URL; let r2Key: String }

func prepareAndUpload(fileURL: URL, jwt: String) async throws {
    let attrs = try FileManager.default.attributesOfItem(atPath: fileURL.path)
    let byteSize = attrs[.size] as? Int ?? 0
    let uti = UTType(filenameExtension: fileURL.pathExtension)
    let contentType = uti?.preferredMIMEType ?? "application/octet-stream"

    var req = URLRequest(url: URL(string: "https://api.example.com/upload-session")!)
    req.httpMethod = "POST"
    req.setValue("Bearer \(jwt)", forHTTPHeaderField: "Authorization")
    req.setValue("application/json", forHTTPHeaderField: "Content-Type")
    req.httpBody = try JSONEncoder().encode([
        "filename": fileURL.lastPathComponent,
        "contentType": contentType,
        "byteSize": byteSize,
    ])

    let (data, _) = try await URLSession.shared.data(for: req)  // foreground session for auth
    let presigned = try JSONDecoder().decode(PresignedResponse.self, from: data)
    UploadSessionManager.shared.startUpload(
        localFileURL: fileURL,
        presignedURL: presigned.uploadUrl,
        contentType: contentType
    )
}
```

## Anti-patterns
- Using `URLSession.shared` (non-background) for large uploads — the OS kills the task when the app is suspended.
- Providing `httpBody` instead of a file URL to `uploadTask(with:fromFile:)` — the OS cannot buffer in-memory data after suspension.
- Setting `isDiscretionary = true` for user-initiated uploads — the OS may defer them for hours.
- Re-fetching a presigned URL inside the background delegate — the URL expires; fetch it before the task starts.
- Forgetting to call `backgroundCompletionHandler()` in `urlSessionDidFinishEvents` — the OS penalizes apps that hold the background time budget.

## Gotchas
- Background sessions survive app termination; the OS relaunches the app when the upload finishes, triggering `handleEventsForBackgroundURLSession`.
- R2 presigned URLs expire (here: 1 hour); if the upload is large and the device is on cellular, it may still be uploading when the URL expires — R2 validates the signature at the start of the PUT, not continuously, so expiry mid-stream is safe.
- The `Content-Length` header must match the actual file size for the presigned PUT; R2 rejects mismatches with 400.
- Simulator does not fully emulate background URLSession behavior — always test on a physical device.

## Verification
1. Start an upload of a 50 MB file, then immediately home-screen the app.
2. Verify in Console.app that the `com.apple.nsurlsessiond` process continues the transfer.
3. Check the Cloudflare R2 dashboard — the object should appear within seconds of the expected transfer time.
4. Confirm the `uploads` D1 table row transitions from `pending` to `complete` after the Worker confirmation PATCH.
5. Re-open the app and assert the progress UI reflects 100%.

## Related
- [react-native-r2-multipart-upload-progress.md](react-native-r2-multipart-upload-progress.md)
- [cloudflare-r2-presigned-url-mobile-clock-drift.md](cloudflare-r2-presigned-url-mobile-clock-drift.md)
- [ios-background-fetch.md](ios-background-fetch.md)
- [ios-urlsession-patterns.md](ios-urlsession-patterns.md)
- [mobile-network-resilience-cloudflare-workers.md](mobile-network-resilience-cloudflare-workers.md)

## Sources
- Apple URLSession background transfers: https://developer.apple.com/documentation/foundation/url_loading_system/downloading_files_in_the_background
- Cloudflare R2 S3-compatible presigned URLs: https://developers.cloudflare.com/r2/api/s3/presigned-urls/
- aws4fetch library: https://github.com/mhart/aws4fetch
