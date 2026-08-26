# React Native Share Extension and iOS Share Sheet

- **Date**: 2026-08-22
- **Author**: example.com
- **Status**: production

## Symptom / Use-case

Users want to share a song link, image, or URL from Safari, Spotify, or any other app directly
into Orchords — adding it to a playlist, reposting it, or saving it as a draft — without leaving
the source app. The standard React Native deep-link approach requires the app to be open; a Share
Extension runs as a lightweight extension process even when the app is closed. On Android the
equivalent is an `ACTION_SEND` intent handler.

## Context

An **iOS Share Extension** is a separate app extension target embedded in the main app bundle.
It runs in its own sandboxed process with access to a shared app group container (App Groups)
for passing data to the main app. The extension UI appears in the iOS Share Sheet when the user
taps the share icon.

On **Android**, registering an `ACTION_SEND` intent filter in the manifest makes the app appear
in the system share sheet. React Native handles the incoming intent via a native module; no
separate process is needed.

Neither platform's share entry point can run React Native directly in the extension process
itself (the JS bundle is too large and the share extension is RAM-constrained to ~120 MB on iOS).
The extension uses a lightweight native UI (SwiftUI / Kotlin Compose) and stores the shared data
in an App Group container or Android `SharedPreferences`/`ContentProvider` to be picked up when
the main app launches.

---

## 1. iOS Share Extension — Native Target

### 1.1 Create the extension target in Xcode

`File → New → Target → Share Extension`. Name it `OrchordShare`.

### 1.2 ShareViewController.swift

```swift
// OrchordShare/ShareViewController.swift
import UIKit
import Social
import UniformTypeIdentifiers

class ShareViewController: SLComposeServiceViewController {

    private let appGroupID = "group.com.orchords.app"

    override func isContentValid() -> Bool {
        return true
    }

    override func didSelectPost() {
        guard
            let item = extensionContext?.inputItems.first as? NSExtensionItem,
            let providers = item.attachments
        else {
            extensionContext?.completeRequest(returningItems: [], completionHandler: nil)
            return
        }

        // Handle URLs (links from Safari, Spotify, etc.)
        let urlType = UTType.url.identifier
        if let provider = providers.first(where: { $0.hasItemConformingToTypeIdentifier(urlType) }) {
            provider.loadItem(forTypeIdentifier: urlType, options: nil) { [weak self] item, _ in
                guard let self = self else { return }
                let urlString: String
                if let url = item as? URL {
                    urlString = url.absoluteString
                } else if let str = item as? String {
                    urlString = str
                } else {
                    self.extensionContext?.completeRequest(returningItems: [], completionHandler: nil)
                    return
                }
                self.storeSharedItem(["type": "url", "value": urlString, "note": self.contentText ?? ""])
            }
            return
        }

        // Handle images
        let imageType = UTType.image.identifier
        if let provider = providers.first(where: { $0.hasItemConformingToTypeIdentifier(imageType) }) {
            provider.loadItem(forTypeIdentifier: imageType, options: nil) { [weak self] item, _ in
                guard let self = self, let image = item as? UIImage else { return }
                let path = self.saveImageToGroupContainer(image)
                self.storeSharedItem(["type": "image", "path": path ?? "", "note": self.contentText ?? ""])
            }
        }
    }

    private func storeSharedItem(_ item: [String: String]) {
        let defaults = UserDefaults(suiteName: appGroupID)
        var queue = (defaults?.array(forKey: "shared_items") as? [[String: String]]) ?? []
        queue.append(item)
        defaults?.set(queue, forKey: "shared_items")
        defaults?.synchronize()
        openMainApp()
        extensionContext?.completeRequest(returningItems: [], completionHandler: nil)
    }

    private func saveImageToGroupContainer(_ image: UIImage) -> String? {
        guard
            let containerURL = FileManager.default.containerURL(forSecurityApplicationGroupIdentifier: appGroupID),
            let data = image.jpegData(compressionQuality: 0.8)
        else { return nil }
        let fileURL = containerURL.appendingPathComponent("\(UUID().uuidString).jpg")
        try? data.write(to: fileURL)
        return fileURL.path
    }

    private func openMainApp() {
        guard let url = URL(string: "orchords://shared-item") else { return }
        var responder: UIResponder? = self
        while let current = responder {
            if let application = current as? UIApplication {
                application.open(url, options: [:], completionHandler: nil)
                return
            }
            responder = current.next
        }
    }

    override func configurationItems() -> [Any]! {
        return []
    }
}
```

### 1.3 Info.plist for the extension

```xml
<!-- OrchordShare/Info.plist (key excerpt) -->
<key>NSExtension</key>
<dict>
    <key>NSExtensionAttributes</key>
    <dict>
        <key>NSExtensionActivationRule</key>
        <dict>
            <!-- Accept URLs and images, max 1 item each -->
            <key>NSExtensionActivationSupportsWebURLWithMaxCount</key>
            <integer>1</integer>
            <key>NSExtensionActivationSupportsImageWithMaxCount</key>
            <integer>1</integer>
        </dict>
    </dict>
    <key>NSExtensionPointIdentifier</key>
    <string>com.apple.share-services</string>
    <key>NSExtensionPrincipalClass</key>
    <string>$(PRODUCT_MODULE_NAME).ShareViewController</string>
</dict>
```

### 1.4 App Groups entitlement

Add the entitlement to **both** the main app target and the extension target:

```xml
<!-- Both *.entitlements files -->
<key>com.apple.security.application-groups</key>
<array>
    <string>group.com.orchords.app</string>
</array>
```

---

## 2. Reading Shared Items in React Native (iOS)

Create a native module that reads the App Group queue when the app launches.

```swift
// ios/SharedItemsBridge.swift
@objc(SharedItemsBridge)
class SharedItemsBridge: NSObject {

    private let appGroupID = "group.com.orchords.app"

    @objc(getSharedItems:reject:)
    func getSharedItems(resolve: RCTPromiseResolveBlock, reject: RCTPromiseRejectBlock) {
        let defaults = UserDefaults(suiteName: appGroupID)
        let items = defaults?.array(forKey: "shared_items") as? [[String: String]] ?? []
        defaults?.removeObject(forKey: "shared_items")
        defaults?.synchronize()
        resolve(items)
    }
}
```

In React Native:

```ts
// hooks/useSharedItems.ts
import { NativeModules } from "react-native";
import { useEffect } from "react";
import { useAppState } from "@react-native-community/hooks";

const { SharedItemsBridge } = NativeModules;

export function useSharedItems(onItem: (item: SharedItem) => void) {
    const appState = useAppState();

    useEffect(() => {
        if (appState !== "active") return;
        SharedItemsBridge?.getSharedItems?.().then(
            (items: SharedItem[]) => items.forEach(onItem)
        );
    }, [appState]);
}

// app/_layout.tsx
import { useSharedItems } from "@/hooks/useSharedItems";
import { router } from "expo-router";

export default function RootLayout() {
    useSharedItems((item) => {
        if (item.type === "url") {
            router.push({ pathname: "/import", params: { url: item.value } });
        }
    });
    // ...
}
```

---

## 3. Android ACTION_SEND Intent Handler

```xml
<!-- android/app/src/main/AndroidManifest.xml -->
<activity
    android:name=".MainActivity"
    android:exported="true">
    <!-- ... existing intent filters ... -->

    <!-- Share intent: text/url -->
    <intent-filter>
        <action android:name="android.intent.action.SEND" />
        <category android:name="android.intent.category.DEFAULT" />
        <data android:mimeType="text/plain" />
    </intent-filter>

    <!-- Share intent: image -->
    <intent-filter>
        <action android:name="android.intent.action.SEND" />
        <category android:name="android.intent.category.DEFAULT" />
        <data android:mimeType="image/*" />
    </intent-filter>
</activity>
```

Read the intent in a native module:

```kotlin
// android/app/src/main/java/com/example-org/example-repo
package com.orchords

import android.content.Intent
import com.facebook.react.bridge.*

class ShareModule(private val context: ReactApplicationContext) :
    ReactContextBaseJavaModule(context) {

    override fun getName() = "ShareModule"

    @ReactMethod
    fun getSharedIntent(promise: Promise) {
        val activity = currentActivity ?: run {
            promise.resolve(null)
            return
        }
        val intent = activity.intent ?: run {
            promise.resolve(null)
            return
        }

        if (intent.action != Intent.ACTION_SEND) {
            promise.resolve(null)
            return
        }

        val result = WritableNativeMap()
        when {
            intent.type?.startsWith("text/") == true -> {
                val text = intent.getStringExtra(Intent.EXTRA_TEXT) ?: ""
                result.putString("type", "url")
                result.putString("value", text)
            }
            intent.type?.startsWith("image/") == true -> {
                val uri = intent.getParcelableExtra<android.net.Uri>(Intent.EXTRA_STREAM)
                result.putString("type", "image")
                result.putString("value", uri?.toString() ?: "")
            }
            else -> {
                promise.resolve(null)
                return
            }
        }
        // Clear the intent so it doesn't re-fire on activity resume
        activity.intent = Intent()
        promise.resolve(result)
    }
}
```

---

## 4. Expo Config Plugin for the Share Extension

For Expo managed workflow, the extension must be added via a config plugin that runs during
`expo prebuild`:

```ts
// plugins/withShareExtension.ts
import {
    withXcodeProject,
    withEntitlementsPlist,
    withInfoPlist,
    IOSConfig,
} from "@expo/config-plugins";
import * as path from "path";
import * as fs from "fs";

function withAppGroup(config: any) {
    return withEntitlementsPlist(config, (mod) => {
        const groups: string[] = mod.modResults["com.apple.security.application-groups"] ?? [];
        const groupId = "group.com.orchords.app";
        if (!groups.includes(groupId)) groups.push(groupId);
        mod.modResults["com.apple.security.application-groups"] = groups;
        return mod;
    });
}

export default function withShareExtension(config: any) {
    config = withAppGroup(config);
    // Add Xcode target programmatically (complex; recommend using
    // @bacons/apple-targets plugin as a base):
    // https://github.com/EvanBacon/expo-apple-targets
    return config;
}
```

---

## Anti-patterns

- **Running heavy JS in the share extension process** — the extension is RAM-limited.
  Store the shared item in App Groups and process it in the main app.
- **Sharing data via Keychain instead of App Groups** — Keychain is for secrets; App Groups
  UserDefaults is the correct inter-process channel for transient shared content.
- **Not clearing the shared item queue after reading** — if the app crashes before clearing,
  it re-processes the item on next launch. Use a processed-id set in persistent storage to
  deduplicate.
- **Missing NSExtensionActivationRule** — without this, the extension appears in every share
  sheet context (files, contacts, etc.). Scope it to the types you actually handle.
- **Forgetting to handle the Android intent on `newIntent`** — if the app is already in the
  foreground and the user shares into it, `onCreate` is not called; override `onNewIntent` in
  `MainActivity`.

---

## Gotchas

- **App Store Review** — share extensions that upload user content must disclose this in the
  privacy manifest and require explicit user confirmation in the extension UI.
- **iOS 16+ UIKit restrictions** — `UIApplication.open` from an extension requires using
  `openURL` on a `NSExtensionContext`-provided `NSUserActivity`; direct `UIApplication` access
  is sandboxed. Use `extensionContext?.open(url)` instead of `UIApplication.shared.open`.
- **Android content URIs expire** — a `content://` URI from `Intent.EXTRA_STREAM` has a
  temporary grant that expires when `Activity.onStop` fires. Copy the file to internal storage
  immediately in the native module rather than passing the URI to JS.
- **App Group entitlement mismatch** — if the entitlement string differs between the main app
  and the extension (e.g. a typo), `UserDefaults(suiteName:)` returns `nil` silently. Always
  define the group ID as a constant in both targets.
- **Xcode automatic signing** — adding the App Groups entitlement requires Xcode to re-provision.
  Expo EAS handles this automatically; manual bare-workflow builds may require a manual
  provisioning profile regeneration on the Apple Developer portal.

---

## Verification

```bash
# iOS: test the extension from Safari on a simulator or device
# 1. Open Safari → navigate to any URL
# 2. Tap the share icon → scroll to "Orchords" (your extension)
# 3. Tap Post
# 4. Open the main Orchords app
# Expected: /import screen opens with the shared URL pre-filled

# Check App Group UserDefaults content (before the main app clears it)
# In the extension, add a breakpoint after storeSharedItem and inspect:
# po UserDefaults(suiteName: "group.com.orchords.app")?.array(forKey: "shared_items")

# Android: send a share intent via adb
adb shell am start \
  -a android.intent.action.SEND \
  -t "text/plain" \
  --es android.intent.extra.TEXT "https://open.spotify.com/track/abc123" \
  com.orchords.app/.MainActivity
```

---

## Related

- `ios-app-clips.md` — lightweight app entry points without extension sandboxing
- `mobile-deep-link-hijacking.md` — security implications of intent handling
- `deep-linking-universal-app-links.md` — URL scheme and universal link routing
- `expo-modules-api-router.md` — Expo config plugin authoring

## Sources

- Apple Share Extension guide: https://developer.apple.com/library/archive/documentation/General/Conceptual/ExtensibilityPG/Share.html
- Apple App Groups: https://developer.apple.com/documentation/bundleresources/entitlements/com_apple_security_application-groups
- Android ACTION_SEND: https://developer.android.com/training/sharing/receive
- expo-apple-targets: https://github.com/EvanBacon/expo-apple-targets
