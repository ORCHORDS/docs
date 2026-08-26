# Rich Media and Interactive Push Notifications

- **Date**: 2026-08-22
- **Author**: example.com
- **Status**: production

## Symptom / Use-case

You send a plain-text push notification and watch open rates stagnate around 3 %. You want
notification images, GIFs, or video thumbnails; action buttons that let users like, reply, or
snooze without opening the app; and category-based grouping in the notification tray. Delivery
goes through your Cloudflare Workers gateway, so the backend shape needs to stay provider-agnostic.

## Context

Both APNs (Apple Push Notification service) and FCM (Firebase Cloud Messaging / HTTP v1) support
rich media and interactive categories. The implementation differs significantly by platform and
requires native notification extension code on iOS that most JavaScript-only setups miss.

iOS rich notifications require a **Notification Service Extension** (to download media before
display) and optionally a **Notification Content Extension** (custom full UI). Android rich
notifications use `BigPictureStyle` or `MessagingStyle` directly in the FCM data payload; no
native extension is needed.

For Expo-managed workflow, `expo-notifications` covers interactive actions and basic image
support, but service extensions require the bare or config-plugin approach.

---

## 1. iOS Notification Service Extension

A Notification Service Extension runs as a separate process for up to 30 seconds when a
`mutable-content: 1` APNs payload arrives. Use it to download media and attach it to the
notification before display. It is also the only way to implement end-to-end encrypted
notification decryption on iOS.

### Adding the extension (bare workflow)

```
ios/
  YourApp/
  YourAppNotificationService/      ← new target
    NotificationService.swift
    Info.plist
```

`NotificationService.swift`:

```swift
import UserNotifications

class NotificationService: UNNotificationServiceExtension {

    var contentHandler: ((UNNotificationContent) -> Void)?
    var bestAttemptContent: UNMutableNotificationContent?

    override func didReceive(
        _ request: UNNotificationRequest,
        withContentHandler contentHandler: @escaping (UNNotificationContent) -> Void
    ) {
        self.contentHandler = contentHandler
        bestAttemptContent = (request.content.mutableCopy() as? UNMutableNotificationContent)

        guard
            let content = bestAttemptContent,
            let mediaURLString = content.userInfo["media_url"] as? String,
            let mediaURL = URL(string: mediaURLString)
        else {
            contentHandler(request.content)
            return
        }

        downloadMedia(from: mediaURL) { attachment in
            if let attachment {
                content.attachments = [attachment]
            }
            contentHandler(content)
        }
    }

    override func serviceExtensionTimeWillExpire() {
        // Deliver best attempt without media if download timed out
        if let contentHandler, let bestAttemptContent {
            contentHandler(bestAttemptContent)
        }
    }

    private func downloadMedia(
        from url: URL,
        completion: @escaping (UNNotificationAttachment?) -> Void
    ) {
        let task = URLSession.shared.downloadTask(with: url) { localURL, _, _ in
            guard let localURL else { completion(nil); return }
            // Move to a path with the correct extension
            let ext = url.pathExtension.isEmpty ? "jpg" : url.pathExtension
            let destURL = localURL.deletingLastPathComponent()
                .appendingPathComponent(UUID().uuidString)
                .appendingPathExtension(ext)
            try? FileManager.default.moveItem(at: localURL, to: destURL)
            let attachment = try? UNNotificationAttachment(
                identifier: UUID().uuidString,
                url: destURL
            )
            completion(attachment)
        }
        task.resume()
    }
}
```

Expo Config Plugin wrapper to add the extension automatically:

```ts
// plugins/withNotificationServiceExtension.ts
import { withXcodeProject, XcodeProject } from "@expo/config-plugins";

export default function withNotificationServiceExtension(config: any) {
    return withXcodeProject(config, async (mod) => {
        // Add target, embed, set Bundle ID, signing — omitted for brevity
        // See expo-notifications-service-extension plugin on npm
        return mod;
    });
}
```

---

## 2. APNs Payload for Rich Notifications

The APNs HTTP/2 JSON payload must include `mutable-content: 1` to trigger the extension.
Keep `content-available: 1` separate — it is for silent background updates, not rich display.

```json
{
  "aps": {
    "alert": {
      "title": "Sofia liked your track",
      "body": "\"Midnight Bloom\" — 🎵"
    },
    "badge": 1,
    "sound": "default",
    "mutable-content": 1,
    "category": "LIKE_REACTION",
    "thread-id": "likes-thread"
  },
  "media_url": "https://cdn.example.com/tracks/midnight-bloom-thumb.jpg",
  "track_id": "trk_abc123",
  "actor_id": "usr_xyz789"
}
```

`thread-id` groups notifications in the Notification Center by topic. `category` maps to a
registered `UNNotificationCategory` (see Section 3).

---

## 3. Interactive Action Buttons

iOS: register categories at app startup, then reference the category identifier in the APNs payload.

```swift
// AppDelegate.swift or Expo notification handler
import UserNotifications

func registerNotificationCategories() {
    let likeAction = UNNotificationAction(
        identifier: "LIKE_ACTION",
        title: "❤️ Like back",
        options: []
    )
    let openAction = UNNotificationAction(
        identifier: "OPEN_ACTION",
        title: "Open track",
        options: [.foreground]
    )
    let likeCategory = UNNotificationCategory(
        identifier: "LIKE_REACTION",
        actions: [likeAction, openAction],
        intentIdentifiers: [],
        options: []
    )
    UNUserNotificationCenter.current()
        .setNotificationCategories([likeCategory])
}
```

Handle the action in React Native via `expo-notifications`:

```ts
// app/_layout.tsx
import * as Notifications from "expo-notifications";
import { useEffect } from "react";
import { likeTrack } from "@/api/tracks";

export default function RootLayout() {
    useEffect(() => {
        const sub = Notifications.addNotificationResponseReceivedListener(
            async (response) => {
                const actionId = response.actionIdentifier;
                const data = response.notification.request.content.data as {
                    track_id: string;
                };

                if (actionId === "LIKE_ACTION") {
                    await likeTrack(data.track_id);
                } else if (
                    actionId === Notifications.DEFAULT_ACTION_IDENTIFIER
                ) {
                    // User tapped the notification body — navigate
                    router.push(`/tracks/${data.track_id}`);
                }
            }
        );
        return () => sub.remove();
    }, []);
}
```

Android: interactive buttons use `actions` in the FCM data payload processed by
`@notifee/react-native` or a custom native module:

```json
{
  "data": {
    "title": "Sofia liked your track",
    "body": "\"Midnight Bloom\"",
    "image": "https://cdn.example.com/tracks/midnight-bloom-thumb.jpg",
    "android_channel_id": "social",
    "actions": "[{\"title\":\"❤️ Like back\",\"pressAction\":{\"id\":\"LIKE_ACTION\"}},{\"title\":\"Open\",\"pressAction\":{\"id\":\"OPEN_ACTION\",\"launchActivity\":\"default\"}}]",
    "track_id": "trk_abc123"
  }
}
```

---

## 4. Backend Payload Dispatch via Cloudflare Workers

A single Worker normalises the orchords platform event into platform-specific payloads.

```ts
// workers/push-dispatcher/src/index.ts
import type { Env } from "./env";

interface PushJob {
    userId: string;
    event: "LIKE" | "COMMENT" | "FOLLOW";
    actorName: string;
    trackId?: string;
    mediaUrl?: string;
    tokens: { platform: "ios" | "android"; token: string }[];
}

export default {
    async queue(batch: MessageBatch<PushJob>, env: Env): Promise<void> {
        for (const msg of batch.messages) {
            const job = msg.body;
            const promises = job.tokens.map((t) => {
                if (t.platform === "ios") {
                    return sendAPNs(t.token, job, env);
                }
                return sendFCM(t.token, job, env);
            });
            await Promise.allSettled(promises);
            msg.ack();
        }
    },
};

async function sendAPNs(token: string, job: PushJob, env: Env) {
    const payload = {
        aps: {
            alert: { title: buildTitle(job), body: buildBody(job) },
            sound: "default",
            "mutable-content": job.mediaUrl ? 1 : 0,
            category: job.event + "_REACTION",
            "thread-id": job.event.toLowerCase() + "-thread",
        },
        media_url: job.mediaUrl,
        track_id: job.trackId,
    };

    // APNs HTTP/2 via fetched JWT (cached in KV)
    const jwt = await getAPNsJWT(env);
    return fetch(`https://api.push.apple.com/3/device/${token}`, {
        method: "POST",
        headers: {
            authorization: `bearer ${jwt}`,
            "apns-topic": env.APNS_BUNDLE_ID,
            "apns-push-type": "alert",
            "apns-priority": "10",
            "content-type": "application/json",
        },
        body: JSON.stringify(payload),
    });
}

function buildTitle(job: PushJob): string {
    const titles: Record<string, string> = {
        LIKE: `${job.actorName} liked your track`,
        COMMENT: `${job.actorName} commented`,
        FOLLOW: `${job.actorName} followed you`,
    };
    return titles[job.event] ?? "New activity";
}

function buildBody(job: PushJob): string {
    return ""; // Additional body text per event type
}
```

---

## Anti-patterns

- **Setting `mutable-content: 1` on every notification** — the extension process consumes
  memory and adds latency. Only set it when you actually have media to attach.
- **Using `content-available: 1` for media delivery** — silent pushes on iOS are heavily
  rate-limited (system delivers a best-effort subset) and will not reliably trigger media download.
- **Embedding large media in the payload** — APNs payload is capped at 4 KB; FCM at 4 KB
  for data payloads. Always send a URL and download in the extension.
- **Registering categories after every launch** — idempotent but wastes startup time. Call
  `setNotificationCategories` once at app start and cache the category list.
- **Not testing on real iOS hardware** — simulator push delivery requires Xcode's simulated
  push tool (`xcrun simctl push`) and service extensions do NOT run in the simulator.

---

## Gotchas

- **App Store Review** — notification action buttons that trigger network requests (like-back)
  without requiring the app to foreground must not charge users or post on their behalf without
  clear UI. Add confirmation alerts for destructive or monetised actions.
- **iOS 18 Live Activities** — `UNNotificationContent` `relevanceScore` was promoted to a
  first-class sort key in the Notification Center stack. Higher scores surface above others;
  default is 0.
- **FCM HTTP v1 vs. legacy** — FCM legacy (send to registration tokens directly) was removed
  in June 2024. All Android pushes must use the HTTP v1 API with OAuth 2.0 service account.
- **Notification grouping on Android** — `MessagingStyle` requires a summary notification plus
  individual message notifications. Without the summary, Android 7+ silently collapses them
  without showing the stack.
- **APNs JWT expiry** — APNs provider JWTs expire after one hour. Cache the signed token in
  KV and regenerate 5 minutes before expiry to avoid 403 `InvalidProviderToken` errors.

---

## Verification

```bash
# Simulate APNs push to a running iOS 17+ simulator
xcrun simctl push booted com.orchords.app \
  - <<'EOF'
{
  "aps": {
    "alert": { "title": "Test rich push", "body": "Body text" },
    "mutable-content": 1,
    "category": "LIKE_REACTION"
  },
  "media_url": "https://via.placeholder.com/400x200.jpg"
}
EOF

# Verify extension ran (check Console.app for logs from NotificationService process)
# Or add os_log in the extension and watch:
log stream --predicate 'subsystem == "com.orchords.app.NotificationService"'
```

Expected: thumbnail appears under the notification body in the lock screen.
Action buttons ("❤️ Like back", "Open track") appear on long-press.

---

## Related

- `ios-push-notifications-apns.md` — APNs authentication, device token registration
- `react-native-push-notifications.md` — expo-notifications setup, permission flow
- `mobile-push-notifications-cloudflare-queues.md` — fan-out architecture with Workers Queue
- `mobile-push-delivery-reliability.md` — retry, receipt validation, token cleanup

## Sources

- Apple UNNotificationServiceExtension docs: https://developer.apple.com/documentation/usernotifications/unnotificationserviceextension
- FCM HTTP v1 messages: https://firebase.google.com/docs/cloud-messaging/send-message
- expo-notifications categories: https://docs.expo.dev/versions/latest/sdk/notifications/#notificationcategoryinput
- Notifee Android rich notifications: https://notifee.app/react-native/docs/android/styles
