# iOS Share Extension Upload to Cloudflare Workers + R2

**Date:** 2026-08-23
**Author:** example.com
**Status:** production

---

## Symptom / Use-Case

You have an iOS Share Extension that receives images, URLs, or files from Safari and other apps. You want the extension to upload those assets directly to Cloudflare R2 via a Workers presigned-URL flow without requiring the host app to be open, without exceeding the Share Extension's 120 second time budget, and without storing the uploaded file on-device after the transfer completes.

---

## Context

iOS Share Extensions run in a separate process from the host app with a tightly restricted memory ceiling (~120 MB) and a hard kill after roughly 120 seconds. They cannot use background URL sessions created by the host app. The extension must create its own `URLSession` with a `background` configuration to survive suspension during upload. A presigned R2 URL is preferable to embedding credentials in the extension bundle — the extension calls a Workers endpoint to obtain a short-lived presigned URL, then streams the file directly to R2.

App Groups are required to share keychain tokens between the host app and the extension.

---

## 1. Cloudflare Worker — Issue Presigned Upload URL

```typescript
// workers/presign/src/index.ts
export interface Env {
  R2_BUCKET: R2Bucket;
  AUTH_SECRET: string; // shared secret validated from the extension
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    if (request.method !== "POST" || new URL(request.url).pathname !== "/presign") {
      return new Response("Not found", { status: 404 });
    }

    // Validate the shared secret header (replace with JWT in production)
    const secret = <redacted-secret>"X-Upload-Secret");
    if (secret !== env.AUTH_SECRET) {
      return Response.json({ error: "unauthorized" }, { status: 401 });
    }

    const { filename, contentType, byteLength } = await request.json<{
      filename: string;
      contentType: string;
      byteLength: number;
    }>();

    if (byteLength > 100 * 1024 * 1024) {
      return Response.json({ error: "file too large (100 MB max)" }, { status: 413 });
    }

    // Generate a unique R2 key with user-controlled filename
    const key = `shares/${Date.now()}-${crypto.randomUUID()}/${filename}`;

    const presignedUrl = await env.R2_BUCKET.createMultipartUpload(key);
    // R2 presigned URLs for PUT are available via the S3-compat API
    // Using R2 S3 API presigned URL instead:
    // (Shown here as a Workers binding approach via createPresignedUrl when using S3 compat)
    // For the native R2 binding, return the key and have the Worker proxy the upload.
    // Here we return key + signed Worker proxy URL instead:

    const proxyUrl = `https://presign.example.workers.dev/upload?key=<redacted-secret>&secret=<redacted-secret>

    return Response.json({ uploadUrl: proxyUrl, key });
  },
};
```

---

## 2. Worker — Proxy PUT to R2

```typescript
// workers/presign/src/upload-proxy.ts  (same Worker, different route)
export async function handleUpload(request: Request, env: Env): Promise<Response> {
  const url = new URL(request.url);
  const key = url.searchParams.get("key");
  const secret = <redacted-secret>"secret");

  if (!key || secret !== env.AUTH_SECRET) {
    return Response.json({ error: "unauthorized" }, { status: 401 });
  }

  if (request.method !== "PUT" || !request.body) {
    return new Response("Bad request", { status: 400 });
  }

  const contentType = request.headers.get("Content-Type") ?? "application/octet-stream";

  await env.R2_BUCKET.put(key, request.body, {
    httpMetadata: { contentType },
  });

  return Response.json({ ok: true, key });
}
```

---

## 3. iOS Extension — ShareViewController.swift

```swift
// ShareExtension/ShareViewController.swift
import UIKit
import Social
import UniformTypeIdentifiers

class ShareViewController: SLComposeServiceViewController {

  private let presignEndpoint = "https://presign.example.workers.dev/presign"
  private let uploadSecret    = "REPLACE_WITH_SECRET" // load from App Group shared UserDefaults in production

  override func isContentValid() -> Bool { true }

  override func didSelectPost() {
    guard let item = extensionContext?.inputItems.first as? NSExtensionItem,
          let provider = item.attachments?.first else {
      extensionContext?.completeRequest(returningItems: nil, completionHandler: nil)
      return
    }

    let imageType = UTType.image.identifier
    let urlType   = UTType.url.identifier

    if provider.hasItemConformingToTypeIdentifier(imageType) {
      provider.loadItem(forTypeIdentifier: imageType, options: nil) { [weak self] data, _ in
        guard let self = self else { return }
        if let url = data as? URL {
          self.uploadFile(at: url, contentType: "image/jpeg")
        } else if let image = data as? UIImage,
                  let jpeg = image.jpegData(compressionQuality: 0.85) {
          self.uploadData(jpeg, filename: "shared-image.jpg", contentType: "image/jpeg")
        }
      }
    } else if provider.hasItemConformingToTypeIdentifier(urlType) {
      provider.loadItem(forTypeIdentifier: urlType, options: nil) { [weak self] data, _ in
        guard let url = data as? URL else { return }
        let payload = Data(url.absoluteString.utf8)
        self?.uploadData(payload, filename: "shared-url.txt", contentType: "text/plain")
      }
    }
  }

  private func uploadFile(at fileURL: URL, contentType: String) {
    guard let data = try? Data(contentsOf: fileURL) else { return }
    uploadData(data, filename: fileURL.lastPathComponent, contentType: contentType)
  }

  private func uploadData(_ data: Data, filename: String, contentType: String) {
    Task {
      do {
        let uploadURL = try await requestPresignedURL(
          filename: filename,
          contentType: contentType,
          byteLength: data.count
        )
        try await performUpload(data: data, to: uploadURL, contentType: contentType)
        await MainActor.run { self.extensionContext?.completeRequest(returningItems: nil, completionHandler: nil) }
      } catch {
        await MainActor.run { self.cancel() }
      }
    }
  }

  private func requestPresignedURL(filename: String, contentType: String, byteLength: Int) async throws -> URL {
    var req = URLRequest(url: URL(string: presignEndpoint)!)
    req.httpMethod = "POST"
    req.setValue("application/json", forHTTPHeaderField: "Content-Type")
    req.setValue(uploadSecret, forHTTPHeaderField: "X-Upload-Secret")
    req.httpBody = try JSONSerialization.data(withJSONObject: [
      "filename": filename,
      "contentType": contentType,
      "byteLength": byteLength,
    ])

    let (data, _) = try await URLSession.shared.data(for: req)
    let json = try JSONDecoder().decode([String: String].self, from: data)
    guard let urlStr = json["uploadUrl"], let url = URL(string: urlStr) else {
      throw URLError(.badServerResponse)
    }
    return url
  }

  private func performUpload(data: Data, to url: URL, contentType: String) async throws {
    var req = URLRequest(url: url)
    req.httpMethod = "PUT"
    req.setValue(contentType, forHTTPHeaderField: "Content-Type")
    req.httpBody = data
    let (_, response) = try await URLSession.shared.data(for: req)
    guard (response as? HTTPURLResponse)?.statusCode == 200 else {
      throw URLError(.badServerResponse)
    }
  }

  override func configurationItems() -> [Any]! { [] }
}
```

---

## 4. App Groups Entitlement (Info.plist + Entitlements)

```xml
<!-- Both the host app and Share Extension targets need: -->
<!-- YourApp.entitlements and ShareExtension.entitlements -->
<key>com.apple.security.application-groups</key>
<array>
  <string>group.com.example.yourapp</string>
</array>
```

```swift
// Shared secret retrieval via App Group UserDefaults
let shared = UserDefaults(suiteName: "group.com.example.yourapp")
let secret = <redacted-secret> "uploadSecret") ?? ""
```

---

## Anti-Patterns

- **Embedding long-lived credentials in the extension binary.** The extension `.appex` is inspectable by anyone who has the IPA. Store only ephemeral tokens or shared secrets in App Group `UserDefaults`, rotated from the host app at launch.
- **Using `URLSession.shared` for large file uploads.** The shared session is not a background session; the OS will kill the upload if the extension is suspended mid-transfer. For files over ~5 MB use a `URLSession` with `background` configuration.
- **Reading the file into `Data` in memory for large uploads.** Loading a 50 MB video into memory hits the 120 MB extension limit. Stream directly from the `URL` using `URLSession.uploadTask(with:fromFile:)`.
- **Not calling `extensionContext?.completeRequest` on failure.** Failing to complete the context leaves the share sheet in a spinner state permanently until the system kills the extension.

---

## Gotchas

- **Share Extensions have a ~120 second hard time limit.** If the upload does not complete within this window iOS terminates the extension. For large files, hand off to a background `URLSession` and complete the extension context immediately.
- **`loadItem(forTypeIdentifier:)` can return `Data`, `URL`, or `UIImage` depending on the source app.** Always handle all three cases; Safari sends `URL`, Photos sends `UIImage` or a file `URL`.
- **`UTType` constants require iOS 14+.** For iOS 13 compatibility use the string `"public.image"` and `"public.url"` directly.
- **R2 presigned URLs expire.** Set an expiry of 60 seconds (sufficient for the extension) via the S3-compat API `Expires` parameter; stale URLs return 403.

---

## Verification

```bash
# 1. Deploy the Worker
wrangler deploy

# 2. Request a presigned URL
curl -X POST "https://presign.example.workers.dev/presign" \
  -H "Content-Type: application/json" \
  -H "X-Upload-Secret: <redacted-secret>" \
  -d '{"filename":"test.jpg","contentType":"image/jpeg","byteLength":12345}'

# 3. Upload a test file to the returned URL
curl -X PUT "<uploadUrl>" \
  -H "Content-Type: image/jpeg" \
  --data-binary @test.jpg

# 4. Verify the object is in R2
wrangler r2 object get shares/<key> --file /tmp/downloaded.jpg
```

---

## Related

- `react-native-share-extension.md`
- `ios-background-upload-session-r2-workers.md`
- `cloudflare-r2-presigned-url-mobile-clock-drift.md`
- `react-native-r2-multipart-upload-progress.md`
- `ios-app-groups-shared-container-boundaries.md` (see `apple-app-groups-shared-container-boundaries.md`)

---

## Sources

- Apple Share Extension guide — https://developer.apple.com/library/archive/documentation/General/Conceptual/ExtensibilityPG/Share.html
- `SLComposeServiceViewController` — https://developer.apple.com/documentation/social/slcomposeserviceviewcontroller
- Cloudflare R2 Workers binding — https://developers.cloudflare.com/r2/api/workers/workers-api-reference/
- App Groups entitlement — https://developer.apple.com/documentation/xcode/configuring-app-groups
- UniformTypeIdentifiers (UTType) — https://developer.apple.com/documentation/uniformtypeidentifiers
